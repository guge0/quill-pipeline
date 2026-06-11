"""Observer 步骤 — 每章生成后自动更新真相文件。

用 V4(deepseek-chat)读正文+当前真相文件,输出更新后的三件套。
失败时 warning 但不阻塞 pipeline。
"""
from __future__ import annotations

import asyncio
import io
import re
import sys
from pathlib import Path

from biyu.truth_files import (
    TRUTH_FILE_NAMES,
    init_truth_files,
    parse_observer_output,
    read_all_truth_files,
    read_truth_file,
    snapshot_truth_files,
    write_truth_file,
)


def _ensure_utf8_stdout() -> None:
    """确保 stdout/stderr 使用 UTF-8 编码(Windows GBK 环境)。"""
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "buffer") and hasattr(stream, "reconfigure"):
                try:
                    stream.reconfigure(encoding="utf-8", errors="replace")
                except (AttributeError, io.UnsupportedOperation):
                    pass


def build_observer_prompt(
    chapter_num: int,
    chapter_text: str,
    truth_data: dict[str, str],
) -> str:
    """构造 Observer prompt。"""
    current_state = truth_data.get("current_state.md", "")
    ledger = truth_data.get("particle_ledger.md", "")
    hooks = truth_data.get("pending_hooks.md", "")

    return f"""\
你是小说连载的设定管理员。刚生成了第{chapter_num}章,请更新三个真相文件。

当前真相文件：
{current_state}

{ledger}

{hooks}

本章正文：
{chapter_text}

规则：
1. current_state：更新所有发生变化的字段,未变化的保持原值
2. particle_ledger：新增本章的属性变化行,不删旧行
3. pending_hooks 伏笔三态状态机(严格遵守,不可跳步):
   状态定义:
   - open: 新伏笔,尚未被推进
   - advancing: 已有推进但未闭合(被提及/有新线索/角色有新认知,但答案未揭示、冲突未解决)
   - closed: 完整闭合(答案被揭示/角色明确解决冲突/故事线自然完结)

   转换规则:
   - 新伏笔 → open
   - 本章有提及或推进但未闭合 → advancing(从open或advancing均可进入)
   - 本章完整闭合(答案揭示/冲突解决) → closed
   - 本章无推进 → 保持原状态
   - 含糊提及(仅再次提及但无实质性推进) → 保持原状态,不推进到advancing

   ⚠️ 关键: "推进"≠"闭合"! 伏笔被再次提及或出现新线索 → advancing,不是closed!
   只有伏笔的答案被明确揭示、冲突被角色明确解决,才能标closed。

4. 严格基于正文事实,不推测、不编造
5. 输出完整的三个 markdown 表格,用 === 分隔

输出格式：
=== current_state ===
（完整表格）
=== particle_ledger ===
（完整表格）
=== pending_hooks ===
（完整表格）
"""


async def update_truth_files(
    book_dir: Path,
    chapter_num: int,
    chapter_text: str,
    adapter,  # LLMAdapter instance
) -> bool:
    """Observer: 读正文,更新真相文件。

    Args:
        book_dir: 书目录
        chapter_num: 章节号
        chapter_text: 本章正文
        adapter: V4 LLMAdapter (deepseek-chat)

    Returns:
        True if update succeeded, False otherwise.
    """
    try:
        _ensure_utf8_stdout()
        # 确保 truth_files 目录存在
        init_truth_files(book_dir)

        # 读取当前真相文件
        truth_data = read_all_truth_files(book_dir)

        # 构造 prompt
        prompt = build_observer_prompt(chapter_num, chapter_text, truth_data)
        messages = [{"role": "user", "content": prompt}]

        # 调用 V4
        resp = await adapter.generate(messages)

        if not resp.text or not resp.text.strip():
            print(f"  [Observer] V4 返回空文本,跳过真相文件更新")
            return False

        # 解析输出
        parsed = parse_observer_output(resp.text)

        # 快照当前 truth_files 到历史目录
        snapshot_truth_files(book_dir, chapter_num)

        # 写回文件
        updated = 0
        for name in TRUTH_FILE_NAMES:
            content = parsed.get(name, "")
            if content:
                write_truth_file(book_dir, name, content)
                updated += 1

        if updated == 0:
            print(f"  [Observer] 解析失败:未能从输出中提取任何真相文件")
            return False

        print(f"  [Observer] 真相文件已更新({updated}/3), ¥{resp.cost:.4f}")

        # 同步死亡角色到 characters.yaml
        _sync_dead_characters(book_dir)

        # 更新角色出场记录
        update_character_appearances(book_dir, chapter_num, chapter_text)

        return True

    except Exception as e:
        print(f"  [Observer] 更新失败(warning,不阻塞): {e}")
        return False


# ---------------------------------------------------------------------------
# 死亡角色同步 — 从 current_state.md 检测死亡事件,更新 characters.yaml
# ---------------------------------------------------------------------------

# 匹配死亡相关模式: 角色名 + 死亡关键词
_DEATH_PATTERNS = re.compile(
    r"([\u4e00-\u9fff]{2,6})"  # 2-6个汉字的角色名
    r"(?:已死|被杀|死亡|阵亡|身亡|殒命|陨落|战死|击杀|斩杀|击毙)",
)
_DEATH_PATTERNS_REVERSE = re.compile(
    r"(?:击杀|斩杀|击毙|杀死|杀害|杀死)"
    r"([\u4e00-\u9fff]{2,6})",
)


def _sync_dead_characters(book_dir: Path) -> int:
    """从 current_state.md 检测死亡事件,更新 characters.yaml 中对应角色 status → dead。

    Returns:
        Number of characters newly marked as dead.
    """
    import yaml
    from biyu.db import sync_characters_from_yaml

    current_state = read_truth_file(book_dir, "current_state.md")
    if not current_state:
        return 0

    # 提取死亡角色名
    dead_names: set[str] = set()
    for m in _DEATH_PATTERNS.finditer(current_state):
        dead_names.add(m.group(1))
    for m in _DEATH_PATTERNS_REVERSE.finditer(current_state):
        dead_names.add(m.group(1))

    if not dead_names:
        return 0

    # 加载 characters.yaml
    yaml_path = book_dir / "characters.yaml"
    if not yaml_path.exists():
        return 0

    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    characters = data.get("characters", [])
    changed = 0
    for char in characters:
        name = char.get("name", "")
        # 主角永远不会被自动标为 dead（防止"主角击杀XXX"等误匹配）
        if char.get("role") == "protagonist":
            continue
        if name in dead_names and char.get("status") != "dead":
            char["status"] = "dead"
            changed += 1
            print(f"  [Observer] 角色状态更新: {name} → dead")

    if changed > 0:
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        # 重新同步到 SQLite
        sync_characters_from_yaml(book_dir)

    return changed


# ---------------------------------------------------------------------------
# 角色出场记录 — 每章生成后自动更新 character_appearances.yaml
# ---------------------------------------------------------------------------

def update_character_appearances(
    book_dir: Path,
    chapter_num: int,
    chapter_text: str,
) -> int:
    """扫描章节正文，更新 character_appearances.yaml。

    Args:
        book_dir: 书目录
        chapter_num: 章节号
        chapter_text: 本章正文

    Returns:
        Number of character appearance records added.
    """
    import yaml

    yaml_path = book_dir / "characters.yaml"
    if not yaml_path.exists():
        return 0

    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    chars = data.get("characters", [])

    # 构建搜索词
    char_search = _build_appearance_search_terms(chars)

    # 分段
    paragraphs = _split_paragraphs(chapter_text)

    # 检测出场
    added = 0
    appearances_to_add: dict[str, dict] = {}

    for char_name, search_terms in char_search.items():
        if not search_terms:
            continue

        mention_count = 0
        matching_chars = 0

        for para in paragraphs:
            found = False
            for term in search_terms:
                if term in para:
                    found = True
                    mention_count += para.count(term)
                    break
            if found:
                matching_chars += len(para)

        if mention_count == 0:
            continue

        type_ = _judge_appearance_type(matching_chars)
        summary = _extract_appearance_summary(chapter_text, search_terms, char_name)

        appearances_to_add[char_name] = {
            "chapter": chapter_num,
            "type": type_,
            "summary": summary,
        }

    if not appearances_to_add:
        return 0

    # 读取/创建 character_appearances.yaml
    truth_dir = book_dir / "truth_files"
    truth_dir.mkdir(parents=True, exist_ok=True)
    appearances_path = truth_dir / "character_appearances.yaml"

    if appearances_path.exists():
        with open(appearances_path, encoding="utf-8") as f:
            appearances_data = yaml.safe_load(f) or {}
    else:
        appearances_data = {}

    for char_name, record in appearances_to_add.items():
        if char_name not in appearances_data:
            appearances_data[char_name] = {"appearances": []}

        # 移除该章节的旧记录（如果有，防止重复）
        appearances_data[char_name]["appearances"] = [
            a for a in appearances_data[char_name]["appearances"]
            if a.get("chapter") != chapter_num
        ]
        appearances_data[char_name]["appearances"].append(record)
        added += 1

    with open(appearances_path, "w", encoding="utf-8") as f:
        yaml.dump(appearances_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    if added > 0:
        print(f"  [Observer] 角色出场记录已更新: {added} 个角色")

    return added


def _build_appearance_search_terms(chars: list[dict]) -> dict[str, set[str]]:
    """为每个角色构建搜索词集合。"""
    char_search: dict[str, set[str]] = {}
    for char in chars:
        name = char.get("name", "")
        terms: set[str] = set()
        terms.add(name)

        aliases = char.get("aliases", {})
        if isinstance(aliases, dict):
            nd = aliases.get("narrator_default", "")
            if nd and nd != name:
                terms.add(nd)

        # 只保留 >= 3 字符的词以减少误报
        terms = {t for t in terms if len(t) >= 3 or t == name}
        char_search[name] = terms

    return char_search


def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs."""
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _judge_appearance_type(char_count: int) -> str:
    """按字数判断出场类型。"""
    if char_count > 1500:
        return "focus"
    elif char_count >= 300:
        return "scene"
    else:
        return "brief"


def _extract_appearance_summary(text: str, search_terms: set[str], char_name: str) -> str:
    """提取出场摘要（取首次提及段落的第一句）。"""
    paragraphs = _split_paragraphs(text)
    for para in paragraphs:
        for term in search_terms:
            if term in para:
                sentence_end = re.search(r"[。！？…]", para)
                if sentence_end:
                    s = para[:sentence_end.end()]
                else:
                    s = para[:60]
                if len(s) > 80:
                    s = s[:77] + "..."
                return s
    return f"{char_name}出场"


# ---------------------------------------------------------------------------
# 伏笔三态重分类 — 将 partially_closed 修正为 advancing
# ---------------------------------------------------------------------------

# 伏笔状态映射: 旧状态 → 新状态
_HOOK_STATUS_MAP = {
    "partially_closed": "advancing",
    "partial_closed": "advancing",
    "partially-resolved": "advancing",
}


def reclassify_hooks(hooks_md: str) -> tuple[str, list[dict]]:
    """对 pending_hooks.md 内容做状态重分类。

    规则:
    - partially_closed / partial_closed → advancing
    - open / advancing / closed → 保持不变

    Args:
        hooks_md: pending_hooks.md 的原始内容。

    Returns:
        (reclassified_content, changes) — 重分类后的内容和变更列表。
        changes 中每项: {"hook_id": str, "old": str, "new": str}
    """
    lines = hooks_md.split("\n")
    result_lines: list[str] = []
    changes: list[dict] = []

    # 找到表头行和分隔行,确定"状态"列的位置
    header_idx = None
    status_col_idx = None
    hook_id_col_idx = None

    for i, line in enumerate(lines):
        if "hook_id" in line and "状态" in line:
            header_idx = i
            cols = [c.strip() for c in line.split("|")]
            for j, col in enumerate(cols):
                if col == "hook_id":
                    hook_id_col_idx = j
                if col == "状态":
                    status_col_idx = j
            break

    if header_idx is None or status_col_idx is None:
        return hooks_md, []

    for i, line in enumerate(lines):
        if i <= header_idx:
            result_lines.append(line)
            continue

        # 跳过分隔行
        stripped = line.strip()
        if stripped.startswith("|") and all(
            c in "|-:" for c in stripped.replace(" ", "")
        ):
            result_lines.append(line)
            continue

        # 跳过空行
        if not stripped:
            result_lines.append(line)
            continue

        # 解析数据行
        cells = line.split("|")
        if status_col_idx >= len(cells):
            result_lines.append(line)
            continue

        old_status = cells[status_col_idx].strip()
        new_status = _HOOK_STATUS_MAP.get(old_status, old_status)

        if new_status != old_status:
            cells[status_col_idx] = f" {new_status} "
            result_lines.append("|".join(cells))
            hook_id = ""
            if hook_id_col_idx is not None and hook_id_col_idx < len(cells):
                hook_id = cells[hook_id_col_idx].strip()
            changes.append({"hook_id": hook_id, "old": old_status, "new": new_status})
        else:
            result_lines.append(line)

    return "\n".join(result_lines), changes


def reclassify_pending_hooks_file(book_dir: Path) -> list[dict]:
    """对 book 目录下的 pending_hooks.md 做就地重分类。

    Returns:
        变更列表。
    """
    from biyu.truth_files import read_truth_file, write_truth_file

    hooks_md = read_truth_file(book_dir, "pending_hooks.md")
    if not hooks_md:
        return []

    new_content, changes = reclassify_hooks(hooks_md)
    if changes:
        write_truth_file(book_dir, "pending_hooks.md", new_content)
        for c in changes:
            print(f"  [reclassify] {c['hook_id']}: {c['old']} → {c['new']}")
    else:
        print("  [reclassify] 无需修改")

    return changes


async def rebuild_hooks(book_dir: Path, adapter) -> dict:
    """重跑所有章节的 Observer 重建 pending_hooks。

    遍历 chapters/ 下的所有 chN.md,逐章调用 Observer 重建真相文件。
    每章会快照当前 truth_files 到 history/ 再覆盖更新。

    ⚠️ 本函数会产生 LLM 调用成本,请确认预算后再运行。

    Args:
        book_dir: 书目录。
        adapter: V4 LLMAdapter。

    Returns:
        {"chapters_processed": int, "errors": list[str]}
    """
    chapters_dir = book_dir / "chapters"
    if not chapters_dir.exists():
        return {"chapters_processed": 0, "errors": ["chapters/ 目录不存在"]}

    # 收集所有 chN.md(不含 _pending)
    chapter_files = sorted(
        chapters_dir.glob("ch*.md"),
        key=lambda p: int(re.search(r"ch(\d+)", p.name).group(1)),
    )
    chapter_files = [
        f for f in chapter_files
        if not f.parent.name.startswith("_")
    ]

    processed = 0
    errors: list[str] = []

    for ch_path in chapter_files:
        m = re.search(r"ch(\d+)", ch_path.name)
        if not m:
            continue
        ch_num = int(m.group(1))
        chapter_text = ch_path.read_text(encoding="utf-8")

        print(f"  [rebuild_hooks] 处理第 {ch_num} 章...")
        ok = await update_truth_files(book_dir, ch_num, chapter_text, adapter)
        if ok:
            processed += 1
        else:
            errors.append(f"ch{ch_num}: Observer 更新失败")

    # 最后做一次 reclassify 确保状态干净
    reclassify_pending_hooks_file(book_dir)

    print(f"  [rebuild_hooks] 完成: {processed}/{len(chapter_files)} 章处理成功")
    return {"chapters_processed": processed, "errors": errors}
