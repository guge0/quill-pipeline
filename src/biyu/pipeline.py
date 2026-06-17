"""主管线: Architect(R1) → Writer(V4) → WordGuard → postproc → Editor → Observer → Auditor"""
from __future__ import annotations

import asyncio
import csv
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Coroutine

from biyu.auditor import run_audit, save_audit_report
from biyu.auditor.base import AuditResult, Severity
from biyu.anchor_check import run_check_text
from biyu.truth_inject import build_truth_injection_block
from biyu.config import BookConfig, get_registry, load_characters_yaml
from biyu.context_retriever import get_retriever
from biyu.db import init_db, record_chapter, sync_characters_from_yaml
from biyu.observer import update_truth_files
from biyu.polish import PolishResult, polish_chapter
from biyu.prompts.v3_opening import build_planning_prompt, build_writer_user_prompt
from biyu.truth_files import read_all_truth_files, read_truth_file
from biyu.wordguard import WordGuardResult, count_cjk_chars, enforce_floor
from biyu.worldbook import load_worldbook, build_worldbook_prompt


@dataclass
class ChapterResult:
    chapter_num: int
    final_text: str
    word_count: int          # CJK 字数
    cost_cny: float
    latency_seconds: float
    stage_latencies: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    planning_text: str = ""
    skeleton_text: str = ""
    polished_text: str = ""
    audit_warnings: list = field(default_factory=list)


async def _call_with_retry(adapter, messages: list[dict], max_retries: int = 2, **kwargs):
    """Call adapter.generate with retry."""
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            return await adapter.generate(messages, **kwargs)
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                await asyncio.sleep(5.0)
    raise last_err


def _log_cost(
    book: BookConfig,
    chapter_num: int,
    stage: str,
    cost_cny: float,
    latency_s: float,
) -> None:
    """Append a cost row to the book's cost_log.csv."""
    book.logs_dir.mkdir(parents=True, exist_ok=True)
    cost_path = book.cost_log_path
    is_new = not cost_path.exists()
    with open(cost_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["timestamp", "chapter", "stage", "cost_cny", "latency_s"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            chapter_num,
            stage,
            f"{cost_cny:.4f}",
            f"{latency_s:.1f}",
        ])


def _write_long_run_csv(
    book_dir: Path,
    chapter_num: int,
    model: str,
    planning_resp,
    writer_resp,
    total_cost: float,
    audit_results: list,
    dash_result,
    final_count: int,
    context_block: str,
    final_text: str,
) -> None:
    """Append a row to the book's long_run_metrics.csv (Phase 4 轻量统计)."""
    csv_path = book_dir / "logs" / "long_run_metrics.csv"
    if not csv_path.exists():
        return

    # Token accumulation
    input_tokens = planning_resp.prompt_tokens + writer_resp.prompt_tokens
    output_tokens = planning_resp.completion_tokens + writer_resp.completion_tokens

    # Cache data (DeepSeek prompt caching)
    cached_tokens = 0
    cache_hit_ratio = 0.0
    raw_usage = (writer_resp.raw or {}).get("usage", {})
    if "prompt_cache_hit_tokens" in raw_usage:
        cached_tokens = raw_usage["prompt_cache_hit_tokens"]
        cache_hit_ratio = cached_tokens / input_tokens if input_tokens > 0 else 0.0

    # Auditor results: map checker name → severity string
    audit_map: dict[str, str] = {}
    for ar in audit_results:
        audit_map[ar.checker] = (
            ar.severity.value if isinstance(ar.severity, Severity) else str(ar.severity)
        )

    # Dash fixer
    dash_count = dash_result.original_count if dash_result else 0
    dash_density = dash_count / (final_count / 1000) if final_count > 0 else 0.0

    # Dialogue ratio (CJK quotation marks)
    dialogue_chars = sum(1 for c in final_text if c in "\u300c\u300d\u300e\u300f\u201c\u201d")
    dialogue_ratio = dialogue_chars / len(final_text) if final_text else 0.0

    # Context block info
    ctx_chars = len(context_block) if context_block else 0
    ctx_chapters = context_block.count("=== \u7b2c") if context_block else 0  # === 第

    # Truth files
    truth_data = read_all_truth_files(book_dir)
    truth_lines = sum(len(v.split("\n")) for v in truth_data.values())
    pending_hooks = sum(
        1 for v in truth_data.values()
        for line in v.split("\n")
        if "pending" in line.lower() or "\u4f0f\u7b14" in line  # 伏笔
    )

    row = [
        chapter_num,
        datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        model,
        input_tokens,
        cached_tokens,
        f"{cache_hit_ratio:.3f}",
        output_tokens,
        f"{total_cost:.4f}",
        audit_map.get("dedup", ""),
        audit_map.get("worldbook_check", ""),
        audit_map.get("character_presence", ""),
        audit_map.get("transition", ""),
        audit_map.get("style_repeat", ""),
        audit_map.get("punctuation_density", ""),
        audit_map.get("meta_vocab", ""),
        audit_map.get("chapter_ending", ""),
        audit_map.get("dialogue_ratio", ""),
        audit_map.get("character_naming", ""),
        dash_count,
        f"{dash_density:.2f}",
        final_count,
        f"{dialogue_ratio:.3f}",
        ctx_chars,
        ctx_chapters,
        truth_lines,
        pending_hooks,
    ]

    with open(csv_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(row)

    print(f"  [long_run_csv] \u5df2\u5199\u5165\u7b2c {chapter_num} \u7ae0\u6307\u6807")


def _build_context_block(
    book_dir: Path, chapter_num: int, context_mode: str = "long_context",
) -> str:
    """构造历史 context 块: 真相文件 + 历史章节。"""
    parts: list[str] = []

    # 1. 真相文件(设定锁,最重要)
    truth_data = read_all_truth_files(book_dir)
    for name, content in truth_data.items():
        if content.strip():
            parts.append(f"=== {name} ===\n{content}")

    # 2. 历史章节(通过 retriever 获取)
    retriever = get_retriever(book_dir, context_mode)
    history = retriever.retrieve(chapter_num)
    for i, ch_text in enumerate(history, start=1):
        parts.append(f"=== 第{i}章 ===\n{ch_text}")

    return "\n\n".join(parts), retriever


def _extract_info_boundary(outline: str) -> str:
    """从大纲中提取'信息边界'段落(如果有)。

    大纲格式:
    ## 信息边界（可选）
    本章可揭示：
    - ...
    本章不可揭示：
    - ...
    """
    # 查找 "信息边界" 段落
    marker = "信息边界"
    idx = outline.find(marker)
    if idx == -1:
        return ""

    # 从标记位置开始,截取到下一个 ## 标题或文件末尾
    start = idx
    # 找到包含标记的那一行的开头
    while start > 0 and outline[start - 1] != "\n":
        start -= 1

    rest = outline[start:]
    # 找到下一个 ## 标题
    import re as _re
    next_heading = _re.search(r"\n##\s+", rest[1:])  # skip first char to avoid matching current
    if next_heading:
        return rest[:next_heading.start() + 1].strip()
    return rest.strip()


def _load_prev_chapter_tail(book_dir: Path, chapter_num: int) -> str:
    """从 ch{N-1}.md 取末尾 500 字（按字符算），用于衔接锚点。

    ch1 不注入。文件不存在不报错，跳过。
    """
    if chapter_num <= 1:
        return ""
    prev_path = book_dir / "chapters" / f"ch{chapter_num - 1}.md"
    if not prev_path.exists():
        return ""
    prev_text = prev_path.read_text(encoding="utf-8")
    return prev_text[-500:] if len(prev_text) > 500 else prev_text


def _detect_secret_realm(outline: str) -> bool:
    """启发式检测大纲是否涉及秘境内场景。

    简单实现:检查大纲中是否包含常见秘境关键词。
    """
    keywords = ["秘境", "白色空间", "异能兽", "铠甲勇士", "曹操", "关羽", "赤壁"]
    lower_outline = outline.lower()
    return any(kw in lower_outline for kw in keywords)


def _parse_present_characters(outline: str, book_dir: Path) -> list[str]:
    """从大纲 yaml frontmatter 解析 present_characters 字段。

    解析失败或字段缺失时，用 truth_files/current_state.md 里的"当前在场"兜底。
    """
    # 尝试解析 yaml frontmatter
    if outline.startswith("---"):
        end = outline.find("---", 3)
        if end != -1:
            frontmatter = outline[3:end].strip()
            try:
                import yaml
                fm = yaml.safe_load(frontmatter)
                if isinstance(fm, dict) and "present_characters" in fm:
                    chars = fm["present_characters"]
                    if isinstance(chars, list):
                        return [str(c) for c in chars]
            except Exception:
                pass

    # 兜底: 从 truth_files/current_state.md 读取"当前在场"
    truth_path = book_dir / "truth_files" / "current_state.md"
    if truth_path.exists():
        content = truth_path.read_text(encoding="utf-8")
        # 查找"在场"或"友"行
        for line in content.split("\n"):
            if "在场" in line or "友：" in line or "友:" in line:
                # 提取冒号后的内容
                parts = line.split("：", 1) if "：" in line else line.split(":", 1)
                if len(parts) > 1:
                    raw_names = [n.strip() for n in parts[1].replace("、", ",").split(",") if n.strip()]
                    if raw_names:
                        # 只取角色名: 遇到括号、破折号、句号、逗号或空格立即停止
                        cleaned = []
                        for name in raw_names:
                            clean = re.split(r'[（(——\-。，,、\s]', name)[0].strip()
                            if clean:
                                cleaned.append(clean)
                        if cleaned:
                            return cleaned
    return []


def _fix_chapter_number(text: str, chapter_num: int) -> str:
    """扫描正文首行，如果章节号与 chapter_num 不符则修正。

    无章节号则不动。
    """
    lines = text.split("\n")
    if not lines:
        return text

    first_line = lines[0]
    # 匹配 "第N章" 或 "Chapter N" 等模式
    pattern = re.compile(r"(第\s*)(\d+)(\s*章|章)")
    match = pattern.search(first_line)
    if match:
        found_num = int(match.group(2))
        if found_num != chapter_num:
            lines[0] = pattern.sub(rf"第{chapter_num}章", first_line)
            return "\n".join(lines)

    # 匹配英文 "Chapter N"
    pattern_en = re.compile(r"(Chapter\s*)(\d+)", re.IGNORECASE)
    match_en = pattern_en.search(first_line)
    if match_en:
        found_num = int(match_en.group(2))
        if found_num != chapter_num:
            lines[0] = pattern_en.sub(f"Chapter {chapter_num}", first_line)
            return "\n".join(lines)

    return text


async def generate_chapter(
    book_dir: Path,
    chapter_num: int,
    chapter_outline_path: Path | None = None,
    model_overrides: dict[str, str] | None = None,
    prompt_version: str = "v4",
    truth_filter_enabled: bool = False,
) -> ChapterResult:
    """Generate a single chapter through the three-stage pipeline.

    Args:
        book_dir: Path to the book directory (containing book.json).
        chapter_num: Chapter number to generate.
        chapter_outline_path: Path to outline file. Defaults to outlines/ch{N}.md.
        model_overrides: Optional dict of pipeline stage → model alias overrides.
                         e.g. {"writer": "r1", "polisher": "v3"}.
                         Only affects this call, does not modify yaml.
        prompt_version: "v4" for new 3-layer prompt, "v3" for legacy prompt.
        truth_filter_enabled: P6-A1 实体过滤注入开关。False(默认)= 全量 truth
                         拼接(改造前基线, D-45 钉死); True = 按 outline 出场实体
                         只注入相关真值(改造后)。

    Returns:
        ChapterResult with all outputs and metadata.
    """
    book = BookConfig(book_dir)
    meta = book.load_meta()
    registry = get_registry()

    overrides = model_overrides or {}

    genre = meta.get("genre", "xuanhuan")
    target_words = meta.get("chapter_target_words", 5000)
    min_words = meta.get("chapter_min_words", 4250)
    context_mode = meta.get("context_mode", "long_context")

    # Resolve outline
    if chapter_outline_path is None:
        chapter_outline_path = book.outline_path(chapter_num)
    if not chapter_outline_path.exists():
        raise FileNotFoundError(f"Outline not found: {chapter_outline_path}")
    outline = chapter_outline_path.read_text(encoding="utf-8")

    # ---- Extract info boundary from outline ----
    info_boundary = _extract_info_boundary(outline)

    # ---- Load worldbook (T-P3-A) ----
    wb = load_worldbook(book_dir)
    worldbook_prompt = build_worldbook_prompt(wb)
    if worldbook_prompt:
        print(f"  worldbook 已加载，注入 prompt")
    else:
        print(f"  worldbook 未找到，跳过注入(warning)")

    # ---- Load prev chapter tail for transition anchor (T-P3-A) ----
    prev_tail = _load_prev_chapter_tail(book_dir, chapter_num)
    if prev_tail:
        print(f"  衔接锚点: 上一章末尾 {len(prev_tail)} 字")

    # ---- Parse present characters from outline (T-P3-A) ----
    present_characters = _parse_present_characters(outline, book_dir)
    if present_characters:
        print(f"  在场角色锁: {', '.join(present_characters)}")
    else:
        print(f"  在场角色锁: 无(无 frontmatter 且兜底为空)")

    # ---- Sync characters to SQLite ----
    init_db(book_dir)
    sync_result = sync_characters_from_yaml(book_dir)
    print(f"  角色同步: yaml {sync_result[0]} 条 → SQLite {sync_result[1]} 条")
    characters = load_characters_yaml(book_dir)

    # ---- Build context block (truth files + history chapters) ----
    print(f"  构建上下文 (模式: {context_mode})...")
    context_block, retriever = _build_context_block(book_dir, chapter_num, context_mode)
    if context_block:
        ctx_chars = len(context_block)
        print(f"  上下文: {ctx_chars} 字符")
    else:
        print(f"  上下文: 无(第一章或无历史数据)")

    total_cost = 0.0
    total_start = time.time()
    stage_latencies: dict[str, float] = {}
    warnings: list[str] = []
    write_to_pending = False

    # ---- 读取 truth_files (Architect + Writer 共用) ----
    truth_files_block = ""
    truth_data = read_all_truth_files(book_dir)
    if truth_filter_enabled:
        # P6-A1: 按 outline 出场实体过滤(改造后); 复用 alias 预注册
        truth_files_block = build_truth_injection_block(
            truth_data, characters, outline, filter_enabled=True,
        )
    else:
        # D-45 钉死: 改造前基线 = 全量拼接(逐字不变)
        for name, content in truth_data.items():
            if content.strip():
                truth_files_block += f"=== {name} ===\n{content}\n\n"

    # ---- Stage 1: Architect (planner) ----
    planning_text = ""
    planner_alias = overrides.get("planner") or registry.get_pipeline_config().get("planner", "r1")
    console_output = f"  [1/4] Architect ({planner_alias} 规划)..."
    print(console_output)
    t0 = time.time()
    planner_adapter = registry.get_adapter_for_stage("planner", override=overrides.get("planner"))
    planning_content = build_planning_prompt(
        outline=outline,
        characters=characters,
        truth_files_block=truth_files_block,
        worldbook_prompt=worldbook_prompt,
        chapter_num=chapter_num,
    )
    planning_messages = [{"role": "user", "content": planning_content}]
    planning_resp = await _call_with_retry(planner_adapter, planning_messages)
    planning_text = planning_resp.text
    stage_latencies["architect"] = time.time() - t0
    total_cost += planning_resp.cost
    _log_cost(book, chapter_num, "architect", planning_resp.cost, stage_latencies["architect"])
    print(f"  [1/4] OK - {stage_latencies['architect']:.1f}s, ¥{planning_resp.cost:.4f}")

    # ---- 细纲层 anchor 早闸(非阻塞, P6-A2)----
    # 零 LLM: 纯子串 value-match。anchors.yaml 不存在则静默跳过。
    skeleton_anchor_report = None
    try:
        anchors_yaml = book_dir / "anchors.yaml"
        if anchors_yaml.exists():
            skel_report = run_check_text(str(anchors_yaml), planning_text, f"T{chapter_num}")
            sk = skel_report["stats"]["atomic"]
            print(
                f"  [1/4] 细纲锚点: 在 {sk['hit']} / 值错 {sk['value_mismatch']} "
                f"/ 缺 {sk['miss']} (共 {sk['total']})"
            )
            skeleton_anchor_report = skel_report
    except Exception as e:
        print(f"  [1/4] 细纲锚点检查跳过: {e}")

    # ---- Stage 2: Writer ----
    skeleton_text = ""
    writer_alias = overrides.get("writer") or registry.get_pipeline_config().get("writer", "v3")
    print(f"  [2/4] Writer ({writer_alias}, prompt={prompt_version})...")
    t0 = time.time()
    writer_adapter = registry.get_adapter_for_stage("writer", override=overrides.get("writer"))

    if prompt_version == "v4":
        from biyu.prompts.chapter_writer import build_writer_prompt_v4, build_layer2_context

        system_prompt, user_prompt = build_writer_prompt_v4(
            chapter_num=chapter_num,
            worldbook=wb,
            worldbook_prompt=worldbook_prompt,
            characters=characters,
            truth_files_block=truth_files_block,
            prev_tail=prev_tail,
            context_block=context_block,
            outline=planning_text,     # P6-1A: Architect 细纲作为 outline 传入
            planning="",                # P6-1A: 不再有独立 planning,细纲已在 outline 中
            target_words=target_words,
            present_characters=present_characters,
        )

        # 拆分 cacheable_prefix 和 dynamic_messages
        # 稳定段: system + worldbook + characters (跨章不变)
        stable_layer2 = build_layer2_context(
            worldbook_prompt=worldbook_prompt,
            characters=characters,
            truth_files_block="",  # truth_files 每章变化
            prev_tail="",
            context_block="",
            outline="",
            planning="",
        )

        cacheable_prefix = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": stable_layer2},
            {"role": "assistant", "content": "已加载世界观和角色卡。"},
        ]

        # 变化段: Layer 1 + 变化的 Layer 2 部分 + Layer 3
        from biyu.prompts.chapter_writer import (
            build_layer1_hard_rules, build_layer3_constraints,
            LAYER1_BEGIN, LAYER1_END, LAYER3_BEGIN, LAYER3_END,
        )
        layer1 = build_layer1_hard_rules(chapter_num, wb)
        variable_layer2 = build_layer2_context(
            worldbook_prompt="",  # 已在 prefix 中
            characters=[],  # 已在 prefix 中
            truth_files_block=truth_files_block,
            prev_tail=prev_tail,
            context_block=context_block,
            outline=planning_text,     # P6-1A: Architect 细纲
            planning="",                # P6-1A: 细纲已在 outline 中
        )
        layer3 = build_layer3_constraints(target_words)
        dynamic_content = (
            f"{layer1}\n\n"
            f"{variable_layer2}\n\n"
            f"{layer3}\n\n"
            f"现在开始写第 {chapter_num} 章正文。只输出正文,不要输出元信息。"
        )

        dynamic_messages = [
            {"role": "user", "content": dynamic_content},
        ]

        writer_resp = await _call_with_retry(
            writer_adapter, dynamic_messages,
            cacheable_prefix=cacheable_prefix,
            temperature=0.8,
            max_tokens=16384,
        )
    else:
        # v3 旧逻辑,完全不动
        writer_messages = [
            {"role": "system", "content": _get_v3_system_prompt()},
            {"role": "user", "content": build_writer_user_prompt(
                planning=planning_text,
                outline=outline,
                target_words=target_words,
                genre=genre,
                characters=characters,
                context_block=context_block,
                info_boundary=info_boundary,
                worldbook_prompt=worldbook_prompt,
                prev_tail=prev_tail,
                present_characters=present_characters,
            )},
        ]
        writer_resp = await _call_with_retry(
            writer_adapter, writer_messages, temperature=0.8,
            max_tokens=16384,
        )
    skeleton_text = writer_resp.text
    stage_latencies["writer"] = time.time() - t0
    total_cost += writer_resp.cost
    _log_cost(book, chapter_num, "writer", writer_resp.cost, stage_latencies["writer"])
    skeleton_count = count_cjk_chars(skeleton_text)
    print(f"  [2/4] OK - {stage_latencies['writer']:.1f}s, ¥{writer_resp.cost:.4f}, {skeleton_count}字")

    # ---- V3 self-continuation (D-01): if skeleton < 4500, ask V3 to continue ----
    if skeleton_count < 4500:
        remaining = target_words - skeleton_count
        print(f"  [2/4+] V3 自续 (骨架仅 {skeleton_count} 字,目标再写 {remaining} 字)...")
        cont_prompt = (
            f"你刚才写的章节到这里：\n{skeleton_text[-2000:]}\n\n"
            f"大纲还有未完成部分：\n{outline}\n\n"
            f"请继续写,风格和前文保持一致,不要重复已写内容。目标再写 {remaining} 字。"
        )
        cont_messages = [
            {"role": "system", "content": _get_v3_system_prompt()},
            {"role": "user", "content": cont_prompt},
        ]
        t_cont = time.time()
        cont_resp = await _call_with_retry(
            writer_adapter, cont_messages, temperature=0.8,
            max_tokens=16384,
        )
        stage_latencies["writer_continuation"] = time.time() - t_cont
        total_cost += cont_resp.cost
        _log_cost(book, chapter_num, "writer_continuation", cont_resp.cost, stage_latencies["writer_continuation"])
        if cont_resp.text and cont_resp.text.strip():
            skeleton_text = skeleton_text + "\n" + cont_resp.text
            skeleton_count = count_cjk_chars(skeleton_text)
            print(f"  [2/4+] 自续完成 - {stage_latencies['writer_continuation']:.1f}s, "
                  f"¥{cont_resp.cost:.4f}, 自续后 {skeleton_count}字")
        else:
            warnings.append("V3 自续返回空文本,跳过")
            print("  [2/4+] 自续返回空文本,跳过")

    # ---- Chapter number fix (T-P3-A) ----
    skeleton_text = _fix_chapter_number(skeleton_text, chapter_num)

    # ---- Stage 3: WordGuard ----
    text_after_guard = skeleton_text
    guard_result: WordGuardResult | None = None
    print(f"  [3/4] WordGuard (字数检查: {skeleton_count}/{min_words})...")
    t0 = time.time()

    async def _continuation_fn(current_text: str, remaining: int) -> str | None:
        """Request continuation from planner model."""
        cont_prompt = (
            f"以下是上一章正文(已写{count_cjk_chars(current_text)}字,目标{target_words}字):\n\n"
            f"{current_text[-1500:]}\n\n"
            f"请从断点处自然续写约{remaining}字,保持风格和人物一致。\n"
            f"只输出续写正文,不要输出说明。"
        )
        messages = [{"role": "user", "content": cont_prompt}]
        resp = await _call_with_retry(planner_adapter, messages)
        return resp.text

    guard_result = await enforce_floor(
        text=skeleton_text,
        target=target_words,
        floor=min_words,
        continuation_fn=_continuation_fn,
    )
    text_after_guard = guard_result.text
    stage_latencies["wordguard"] = time.time() - t0
    if guard_result.continued:
        cont_cost = planning_resp.cost * (guard_result.continuation_word_count / max(skeleton_count, 1))
        total_cost += cont_cost
        _log_cost(book, chapter_num, "wordguard", cont_cost, stage_latencies["wordguard"])
    if guard_result.warning:
        warnings.append(guard_result.warning)
    print(
        f"  [3/4] {'续写触发' if guard_result.continued else '达标'} - "
        f"{skeleton_count}→{guard_result.word_count}字"
        + (f" [WARN: {guard_result.warning}]" if guard_result.warning else "")
    )

    # ---- Stage 3.5: dash_fixer (破折号后处理) ----
    if prompt_version == "v4":
        from biyu.postproc.dash_fixer import fix_dashes
        dash_result = fix_dashes(text_after_guard)
        if dash_result.original_count != dash_result.fixed_count:
            dash_log_dir = book.logs_dir / f"ch{chapter_num}"
            dash_log_dir.mkdir(parents=True, exist_ok=True)
            (dash_log_dir / "skeleton_raw.md").write_text(dash_result.original_text, encoding="utf-8")
            (dash_log_dir / "skeleton_dashfixed.md").write_text(dash_result.fixed_text, encoding="utf-8")
            text_after_guard = dash_result.fixed_text
            print(
                f"  [dash_fixer] 破折号 {dash_result.original_count} → {dash_result.fixed_count}"
                f" ({len(dash_result.replacements)} 条规则触发)"
            )
            # Git commit: dash_fixer 修复
            try:
                from biyu.git_helper import commit_chapter
                dash_hash = commit_chapter(
                    book_dir, chapter_num,
                    f"dash_fixer 修复（{dash_result.original_count}→{dash_result.fixed_count}）",
                    auto=True,
                )
                print(f"  [git] dash_fixer 已提交: {dash_hash}")
            except Exception as e:
                print(f"  [git] dash_fixer 提交失败(warning): {e}")
        else:
            print(f"  [dash_fixer] 破折号 {dash_result.original_count} 个,无需修复")

    # ---- Stage 3.6: wenyan_fixer (文白夹杂后处理,可通过 wenyan_enabled=false 跳过) ----
    wenyan_enabled = registry.get_pipeline_config().get("wenyan_enabled", True)
    if prompt_version == "v4" and wenyan_enabled:
        from biyu.postproc.wenyan_fixer import fix_wenyan
        in_secret_realm = _detect_secret_realm(outline)
        wenyan_result = fix_wenyan(text_after_guard, in_secret_realm=in_secret_realm)
        if wenyan_result.replacements:
            text_after_guard = wenyan_result.fixed_text
            total_replaced = sum(r["count"] for r in wenyan_result.replacements)
            print(
                f"  [wenyan_fixer] 文白修复 {total_replaced} 处"
                f" ({len(wenyan_result.replacements)} 类文言词替换)"
            )
        else:
            print(f"  [wenyan_fixer] 无文白夹杂问题")
    elif not wenyan_enabled:
        print(f"  [wenyan_fixer] 跳过 (wenyan_enabled=false)")

    # ---- Stage 3.7: grammar_check (T-P3-C P1) ----
    if prompt_version == "v4":
        from biyu.grammar_check.checker import check_chapter as grammar_check, auto_fix as grammar_auto_fix
        print(f"  [grammar_check] 本地检查...")
        grammar_result = grammar_check(text_after_guard, book_dir)
        if grammar_result.has_issues:
            text_after_guard, grammar_fixed = grammar_auto_fix(text_after_guard, grammar_result)
            if grammar_fixed > 0:
                print(f"  [grammar_check] 修复 {grammar_fixed} 处（占位符{len(grammar_result.placeholders)} / 错别字{len(grammar_result.typos)} / 重复字{len(grammar_result.repeated_chars)}）")
                try:
                    from biyu.git_helper import commit_chapter
                    gh_hash = commit_chapter(book_dir, chapter_num, f"grammar 修复 ({grammar_fixed} 处)", auto=True)
                    print(f"  [git] grammar_check 已提交: {gh_hash}")
                except Exception as e:
                    print(f"  [git] grammar_check 提交失败(warning): {e}")
            else:
                print(f"  [grammar_check] 发现 {grammar_result.total_count} 处问题但无高置信自动修")
        else:
            print(f"  [grammar_check] 通过")

    # ---- Stage 3.8: Editor 审稿 (T-P3-C P1 / T-P3-D-2 multi-agent) ----
    editor_enabled = registry.get_pipeline_config().get("editor_enabled", True)
    editor_result_obj = None
    editor_section = ""  # 审计报告 section 4 内容
    if prompt_version == "v4" and editor_enabled:
        t0_ed = time.time()
        try:
            from biyu.editor.auto_fix import auto_fix_issues as editor_auto_fix

            # 加载上一章末尾
            prev_tail_for_editor = ""
            if chapter_num > 1:
                prev_ch = book_dir / "chapters" / f"ch{chapter_num - 1}.md"
                if prev_ch.exists():
                    prev_text = prev_ch.read_text(encoding="utf-8")
                    prev_tail_for_editor = prev_text[-500:]

            editor_adapter = registry.get_adapter_for_stage("writer", override=None)

            # 读取 editor config 判断 mode
            from biyu.editor.multi_agent import load_editor_config, review_chapter_multi_agent
            from biyu.editor.merge import render_audit_report
            ed_config = load_editor_config()
            ed_mode = ed_config.get("mode", "single")

            if ed_mode == "multi_agent":
                # Multi-agent 审稿
                print(f"  [Editor] Multi-Agent 审稿 (A/B/C)...")
                merge_result = await review_chapter_multi_agent(
                    chapter_num=chapter_num,
                    chapter_text=text_after_guard,
                    book_dir=book_dir,
                    adapter=editor_adapter,
                    prev_chapter_tail=prev_tail_for_editor,
                )
                stage_latencies["editor"] = time.time() - t0_ed
                _log_cost(book, chapter_num, "editor", merge_result.total_cost, stage_latencies["editor"])

                editor_section = render_audit_report(chapter_num, merge_result)
                n_issues = merge_result.total_issues
                n_high = len(merge_result.high_issues)
                print(f"  [Editor] {n_issues} 个合并问题（{n_high} 个高严重度）")
                if merge_result.fallback_used:
                    print(f"  [Editor] ⚠️ 成本超限，已回退到 Phase 1 直接合并")

                # 高严重度 issue 触发 _pending
                if merge_result.high_issues:
                    write_to_pending = True
                    high_types = {i.type for i in merge_result.high_issues}
                    warnings.append(f"Editor 标记需审查: {', '.join(high_types)}")
                    print(f"  [Editor] → 进 _pending/（需老板审查）")

            else:
                # Single mode（原有逻辑）
                print(f"  [Editor] V4-Pro 审稿 (single mode)...")
                from biyu.editor.editor import review_chapter as editor_review

                editor_result_obj = await editor_review(
                    chapter_num=chapter_num,
                    chapter_text=text_after_guard,
                    book_dir=book_dir,
                    adapter=editor_adapter,
                    prev_chapter_tail=prev_tail_for_editor,
                )
                stage_latencies["editor"] = time.time() - t0_ed
                ed_cost = editor_result_obj.cost
                _log_cost(book, chapter_num, "editor", ed_cost, stage_latencies["editor"])

                n_issues = len(editor_result_obj.issues)
                n_auto = len(editor_result_obj.auto_fixable_issues)
                print(f"  [Editor] {n_issues} 个问题（{n_auto} 个可自动修）")

                # 字面伪影自动修
                if editor_result_obj.auto_fixable_issues:
                    text_after_guard, ed_fixed = editor_auto_fix(text_after_guard, editor_result_obj.auto_fixable_issues)
                    if ed_fixed > 0:
                        print(f"  [Editor] 字面伪影自动修 {ed_fixed} 处")
                        try:
                            from biyu.git_helper import commit_chapter
                            ed_hash = commit_chapter(book_dir, chapter_num, f"Editor 字面伪影自动修 ({ed_fixed} 处)", auto=True)
                            print(f"  [git] Editor 自动修已提交: {ed_hash}")
                        except Exception as e:
                            print(f"  [git] Editor 自动修提交失败(warning): {e}")

                # 高严重度 issue 触发 _pending
                high_severity_types = {"视角穿帮", "逻辑漏洞", "跨章一致性"}
                if any(i.type in high_severity_types for i in editor_result_obj.issues):
                    write_to_pending = True
                    warnings.append(f"Editor 标记需审查: {', '.join(i.type for i in editor_result_obj.issues if i.type in high_severity_types)}")
                    print(f"  [Editor] → 进 _pending/（需老板审查）")

                # ---- T-P3-D-3: 生成双层报告 (JSON + MD) ----
                if editor_result_obj and editor_result_obj.issues:
                    try:
                        from biyu.audit_reports.state import build_report_from_editor_result
                        from biyu.audit_reports.builder import build_audit_md_from_json

                        audit_report = build_report_from_editor_result(
                            chapter_num=chapter_num,
                            editor_result=editor_result_obj,
                            editor_cost_yuan=ed_cost,
                            editor_mode="single",
                        )
                        report_dir = book_dir / "audit_reports"
                        report_dir.mkdir(parents=True, exist_ok=True)
                        json_path = audit_report.save(report_dir)
                        md_path = build_audit_md_from_json(audit_report, book_dir)
                        print(f"  [Editor] 双层报告已生成: {json_path.name} + {md_path.name}")
                    except Exception as e:
                        print(f"  [Editor] 双层报告生成失败(warning): {e}")

        except Exception as e:
            print(f"  [Editor] 审稿失败(warning): {e}")
            warnings.append(f"Editor 审稿失败(warning): {e}")

    # ---- Stage 4: Polish (可通过 polish_enabled=false 跳过) ----
    final_text = text_after_guard
    polish_result: PolishResult | None = None
    polisher_alias = overrides.get("polisher") or registry.get_pipeline_config().get("polisher", "kimi")
    polish_enabled = registry.get_pipeline_config().get("polish_enabled", True)

    if polish_enabled:
        print(f"  [4/4] Polish ({polisher_alias} 润色)...")
        t0 = time.time()
        polish_result = await polish_chapter(
            text_after_guard, registry,
            model_key=polisher_alias,
        )
        stage_latencies["polisher"] = time.time() - t0
        total_cost += polish_result.cost
        _log_cost(book, chapter_num, "polisher", polish_result.cost, stage_latencies["polisher"])
        if polish_result.success:
            final_text = polish_result.polished_text
            # D-03: Kimi 削减超 10% 则回退到润色前版本
            guard_count = count_cjk_chars(text_after_guard)
            polished_count = count_cjk_chars(final_text)
            if polished_count < guard_count * 0.9:
                warnings.append(
                    f"Kimi 削减超 10% ({guard_count}→{polished_count}),使用润色前版本"
                )
                final_text = text_after_guard
                print(f"  [4/4] WARN - Kimi 削减 {guard_count}→{polished_count},回退原文")
            else:
                print(f"  [4/4] OK - {stage_latencies['polisher']:.1f}s, ¥{polish_result.cost:.4f}")
        else:
            warnings.append(f"Kimi 润色失败: {polish_result.error}")
            print(f"  [4/4] FAIL - 降级使用原文: {polish_result.error}")
    else:
        print(f"  [4/4] Polish 跳过 (polish_enabled=false)")
        # 创建一个空的 polish_result 占位,后续 meta 写入不会崩
        polish_result = PolishResult(
            polished_text=text_after_guard,
            success=True,
            cost=0.0,
            error="",
        )

    total_latency = time.time() - total_start
    final_count = count_cjk_chars(final_text)

    # ---- Consistency check ----
    from biyu.consistency import check_chapter
    consistency_issues = check_chapter(book_dir, chapter_num, chapter_text=final_text)
    consistency_dicts = []
    if consistency_issues:
        for iss in consistency_issues:
            warnings.append(
                f"[一致性] {iss.rule}: {iss.character} 在 ch{chapter_num} "
                f"段落『{iss.location[:30]}...』"
            )
            consistency_dicts.append({
                "rule": iss.rule,
                "severity": iss.severity,
                "character": iss.character,
                "location": iss.location,
                "suggestion": iss.suggestion,
            })

    # ---- Save outputs ----
    # D-05: 正则清理元标记（双保险，prompt 层已加清理规则）
    final_text = re.sub(r'【[^】]{1,20}】', '', final_text)

    # ---- Stage 5: Observer (更新真相文件) ----
    print(f"  [Observer] 更新真相文件...")
    observer_ok = False
    try:
        # Observer 始终用 V3(deepseek-chat),不跟随 Writer 的 override
        # 理由: Observer 任务是"提取事实",V3 指令遵循优于 R1
        observer_alias = registry.get_pipeline_config().get("writer", "v3")
        observer_adapter = registry.get_adapter_for_stage("writer", override=observer_alias)
        observer_ok = await update_truth_files(
            book_dir, chapter_num, final_text, observer_adapter,
        )
        if not observer_ok:
            warnings.append("Observer 更新真相文件失败(warning,不阻塞)")
    except Exception as e:
        warnings.append(f"Observer 异常(warning): {e}")
        print(f"  [Observer] 异常(warning): {e}")

    # ---- Auditor (T-P3-A) ----
    audit_results: list[AuditResult] = []
    audit_warnings: list[str] = []
    print(f"  [Auditor] 执行 9 项检查...")
    try:
        audit_ctx = {
            "book_dir": str(book_dir),
            "chapter_num": chapter_num,
            "worldbook": wb,
            "characters": characters,
            "present_characters": present_characters,
            "outline": outline,
            "planning": planning_text,
        }
        audit_results = run_audit(final_text, audit_ctx)
        # 保存审计报告
        report_path = save_audit_report(book_dir, chapter_num, audit_results)
        print(f"  [Auditor] 报告已保存: {report_path}")

        for ar in audit_results:
            severity_label = ar.severity.value if isinstance(ar.severity, Severity) else str(ar.severity)
            print(f"    [{severity_label}] {ar.checker}: {ar.message}")
            audit_warnings.append(f"[{severity_label}] {ar.checker}: {ar.message}")

            # BLOCK → 进 _pending/
            if ar.severity == Severity.BLOCK:
                write_to_pending = True
                warnings.append(f"Auditor BLOCK: {ar.checker} - {ar.message}")
    except Exception as e:
        audit_warnings.append(f"Auditor 整体异常: {e}")
        print(f"  [Auditor] 整体异常(warning): {e}")

    # 根据质量门决定写入路径
    book.chapters_dir.mkdir(parents=True, exist_ok=True)
    if write_to_pending:
        pending_dir = book.chapters_dir / "_pending"
        pending_dir.mkdir(exist_ok=True)
        output_path = pending_dir / f"ch{chapter_num}.md"
        print(f"  → 写入 _pending/ch{chapter_num}.md (质量未达标)")
    else:
        output_path = book.chapter_path(chapter_num)
    output_path.write_text(final_text, encoding="utf-8")

    # ---- Git commit: 初次生成 ----
    try:
        from biyu.git_helper import commit_chapter
        commit_hash = commit_chapter(book_dir, chapter_num, "初次生成", auto=True)
        print(f"  [git] 已提交: {commit_hash}")
    except Exception as e:
        print(f"  [git] 提交失败(warning): {e}")

    log_dir = book.chapter_log_dir(chapter_num)
    (log_dir / "planning.md").write_text(planning_text, encoding="utf-8")
    (log_dir / "skeleton.md").write_text(skeleton_text, encoding="utf-8")
    if polish_result:
        (log_dir / "polished.md").write_text(polish_result.polished_text, encoding="utf-8")
    # compute quality string outside f-string to avoid format specifier issues
    (log_dir / "meta.md").write_text(
        f"Chapter {chapter_num}\n"
        f"Word count: {final_count}\n"
        f"Cost: ¥{total_cost:.4f}\n"
        f"Latency: {total_latency:.1f}s\n"
        f"Stages: {stage_latencies}\n"
        f"Models: planner={planner_alias}, writer={writer_alias}, polisher={polisher_alias}\n"
        f"Pending: {write_to_pending}\n"
        f"Warnings: {warnings}\n"
        f"Consistency issues: {len(consistency_issues)}\n",
        encoding="utf-8",
    )

    # Also write meta.json for programmatic access
    import json
    meta_dict = {
        "chapter": chapter_num,
        "word_count": final_count,
        "cost_cny": total_cost,
        "latency_seconds": total_latency,
        "stage_latencies": stage_latencies,
        "models": {"planner": planner_alias, "writer": writer_alias, "polisher": polisher_alias},
        "prompt_version": prompt_version,
        "polish_skipped": not polish_enabled,
        "warnings": warnings,
        "consistency_issues": len(consistency_issues),
        "pending": write_to_pending,
        "audit_warnings": audit_warnings,
    }
    (log_dir / "meta.json").write_text(
        json.dumps(meta_dict, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ---- Record to SQLite ----
    record_chapter(
        book_dir,
        chapter_num=chapter_num,
        word_count=final_count,
        cost_cny=total_cost,
        latency_seconds=total_latency,
        warnings=warnings,
        consistency_issues=consistency_dicts,
    )

    # ---- Long-run metrics CSV (Phase 4) ----
    try:
        _dr = dash_result
    except NameError:
        _dr = None
    try:
        _write_long_run_csv(
            book_dir=book_dir,
            chapter_num=chapter_num,
            model=writer_alias,
            planning_resp=planning_resp,
            writer_resp=writer_resp,
            total_cost=total_cost,
            audit_results=audit_results,
            dash_result=_dr,
            final_count=final_count,
            context_block=context_block,
            final_text=final_text,
        )
    except Exception as e:
        print(f"  [long_run_csv] \u5199\u5165\u5931\u8d25(warning): {e}")

    # ---- Index chapter for RAG (if applicable) ----
    if context_mode == "rag":
        try:
            retriever.index_chapter(chapter_num, final_text)
        except Exception as e:
            warnings.append(f"RAG 索引失败(warning): {e}")
            print(f"  [RAG] 索引失败(warning): {e}")

    # ---- Build audit report (T-P3-C) ----
    try:
        from biyu.audit_reports.builder import build_audit_report
        # Convert audit_results to serializable dicts
        audit_dicts = [
            {"checker": ar.checker, "severity": ar.severity.value if hasattr(ar.severity, "value") else str(ar.severity), "message": ar.message}
            for ar in audit_results
        ]
        report_path = build_audit_report(
            book_dir, chapter_num,
            audit_results=audit_dicts,
            word_count=final_count,
            postproc_summary="",
            pending=write_to_pending,
            editor_section=editor_section,
        )
        print(f"  [audit_report] 已生成: {report_path}")
    except Exception as e:
        print(f"  [audit_report] 生成失败(warning): {e}")

    return ChapterResult(
        chapter_num=chapter_num,
        final_text=final_text,
        word_count=final_count,
        cost_cny=total_cost,
        latency_seconds=total_latency,
        stage_latencies=stage_latencies,
        warnings=warnings,
        planning_text=planning_text,
        skeleton_text=skeleton_text,
        polished_text=polish_result.polished_text if polish_result else "",
        audit_warnings=audit_warnings,
    )


def _get_v3_system_prompt() -> str:
    """Get the V3 system prompt."""
    from biyu.prompts.v3_opening import V3_OPENING_SYSTEM
    return V3_OPENING_SYSTEM
