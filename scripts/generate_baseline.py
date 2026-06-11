#!/usr/bin/env python3
"""P6-13-B2 三章基线生成脚本。

从冻结的 eval_set_v0 素材生成 T1/T2/T3 基线正文。
格式桥接：B1 素材(YAML truth / dict characters) → 管线期望格式(MD truth / list characters)。
不修改 B1 素材文件本身，仅在临时 book_dir 中做格式适配。

输出：
- eval_set_v0/baseline/T{1,2,3}_clean.md
- eval_set_v0/baseline/cost_breakdown.json
- D-47: 任一章 Writer 首个请求体 → eval_set_v0/baseline/writer_request_body.json
"""
import asyncio
import json
import shutil
import sys
import time
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = PROJECT_ROOT / "eval_set_v0"
BOOK_DIR = PROJECT_ROOT / "data" / "EV1_回声巷"
BASELINE_DIR = EVAL_DIR / "baseline"

# 指令要求：Editor single 模式，控制变量
# polish_enabled=false (models.yaml 中已配)
# 不跑 Observer (使用冻结 truth，不用实跑 Observer 输出)


def setup_book_dir(book_dir: Path, chapter_key: str, truth_source: str):
    """创建/准备 book 目录，桥接 B1 格式到管线格式。

    Args:
        book_dir: 书目录路径
        chapter_key: "T1", "T2", "T3"
        truth_source: truth 来源目录 — "truth_files" (序章) 或 "truth_files_frozen" (FT1/FT2)
    """
    book_dir.mkdir(parents=True, exist_ok=True)

    # 1. book.json
    meta = {
        "title": "EV1 回声巷",
        "genre": "都市悬疑",
        "chapter_target_words": 5000,
        "chapter_min_words": 3000,
        "context_mode": "long_context",
    }
    (book_dir / "book.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 2. worldbook.yaml — 直接拷贝（格式兼容）
    shutil.copy2(EVAL_DIR / "worldbook.yaml", book_dir / "worldbook.yaml")

    # 3. characters.yaml — 格式桥接：{name: {fields}} → {characters: [{name: ..., **fields}]}
    with open(EVAL_DIR / "characters.yaml", encoding="utf-8") as f:
        chars_dict = yaml.safe_load(f)
    chars_list = []
    for name, fields in chars_dict.items():
        if isinstance(fields, dict):
            chars_list.append({"name": name, **fields})
    pipeline_chars = {"characters": chars_list}
    (book_dir / "characters.yaml").write_text(
        yaml.dump(pipeline_chars, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )

    # 4. truth_files/ — 格式桥接：YAML → .md (内容不变，LLM 照读)
    tf_src = EVAL_DIR / truth_source
    tf_dst = book_dir / "truth_files"
    tf_dst.mkdir(parents=True, exist_ok=True)
    for yaml_file in tf_src.glob("*.yaml"):
        # 复制 YAML 内容到 .md 文件（管线读 .md）
        content = yaml_file.read_text(encoding="utf-8")
        md_name = yaml_file.stem + ".md"
        (tf_dst / md_name).write_text(content, encoding="utf-8")

    # 5. outlines/ — sub_md 作为大纲
    outline_dir = book_dir / "outlines"
    outline_dir.mkdir(parents=True, exist_ok=True)
    chapter_num = int(chapter_key[1])  # T1 → 1, T2 → 2, T3 → 3
    sub_md_src = EVAL_DIR / "sub_md" / f"{chapter_key}.md"
    shutil.copy2(sub_md_src, outline_dir / f"ch{chapter_num}.md")

    # 6. 清理旧输出
    for sub in ["chapters", "logs", "audit_reports"]:
        d = book_dir / sub
        if d.exists():
            shutil.rmtree(d)


def get_truth_source(chapter_key: str) -> str:
    """返回对应章节的 truth 来源目录。"""
    if chapter_key == "T1":
        return "truth_files"       # 序章 truth
    elif chapter_key == "T2":
        return "truth_files_frozen"  # FT1
    elif chapter_key == "T3":
        return "truth_files_frozen"  # FT2
    raise ValueError(f"Unknown chapter: {chapter_key}")


async def generate_one(
    chapter_key: str,
    capture_request_body: bool = False,
) -> dict:
    """生成单章基线。

    Returns:
        dict with keys: chapter_key, final_text, word_count, cost_cny,
                        stage_latencies, cost_breakdown, boundary_events
    """
    from biyu.config import BookConfig, get_registry
    from biyu.pipeline import generate_chapter
    from biyu.llm import DeepSeekAdapter

    chapter_num = int(chapter_key[1])
    truth_source = get_truth_source(chapter_key)

    # 每章重新 setup book dir (换 truth 来源)
    setup_book_dir(BOOK_DIR, chapter_key, truth_source)

    # D-47: Monkey-patch Writer adapter to capture first request body
    captured_body = []
    if capture_request_body:
        registry = get_registry()
        writer_adapter = registry.get_adapter_for_stage("writer")
        original_generate = writer_adapter.generate

        async def capturing_generate(messages, **kwargs):
            if not captured_body:
                body = {
                    "model": writer_adapter.model_name,
                    "messages_summary": [
                        {
                            "role": m.get("role", "?"),
                            "content_length": len(m.get("content", "")),
                            "content_preview": m.get("content", "")[:300],
                        }
                        for m in messages
                    ],
                    "cacheable_prefix_count": len(kwargs.get("cacheable_prefix", [])),
                    "temperature": kwargs.get("temperature"),
                    "max_tokens": kwargs.get("max_tokens"),
                }
                captured_body.append(body)
            return await original_generate(messages, **kwargs)

        writer_adapter.generate = capturing_generate

    # 确保不跑 Polish 和 Observer (控制变量)
    # Polish 已在 models.yaml 中 polish_enabled: false
    # 我们不调用 Observer — truth 由冻结夹具提供

    t0 = time.time()
    boundary_events = []
    result = None

    try:
        result = await generate_chapter(
            book_dir=BOOK_DIR,
            chapter_num=chapter_num,
            prompt_version="v4",
        )
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        boundary_events.append({
            "type": "RUN_FAIL",
            "chapter": chapter_key,
            "error": str(e),
            "traceback": tb,
        })
        print(f"  [FAIL] {chapter_key}: {e}")
        print(tb)

    elapsed = time.time() - t0

    if result is None:
        return {
            "chapter_key": chapter_key,
            "final_text": "",
            "word_count": 0,
            "cost_cny": 0,
            "elapsed_seconds": elapsed,
            "stage_latencies": {},
            "cost_breakdown": {},
            "boundary_events": boundary_events,
            "captured_body": captured_body[0] if captured_body else None,
        }

    # 检查边界事件
    for w in result.warnings:
        boundary_events.append({"type": "WARNING", "detail": w})
    if result.word_count < 3000:
        boundary_events.append({
            "type": "SHORT_CHAPTER",
            "word_count": result.word_count,
        })

    # 恢复 adapter
    if capture_request_body:
        registry = get_registry()
        writer_adapter = registry.get_adapter_for_stage("writer")
        writer_adapter.generate = original_generate

    return {
        "chapter_key": chapter_key,
        "final_text": result.final_text,
        "word_count": result.word_count,
        "cost_cny": result.cost_cny,
        "elapsed_seconds": elapsed,
        "stage_latencies": result.stage_latencies,
        "cost_breakdown": {
            "total": result.cost_cny,
        },
        "boundary_events": boundary_events,
        "captured_body": captured_body[0] if captured_body else None,
    }


async def main():
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("P6-13-B2 三章基线生成")
    print("=" * 60)
    print(f"Book dir: {BOOK_DIR}")
    print(f"Output: {BASELINE_DIR}")
    print()

    # 预检
    import subprocess
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "llm_connectivity_check.py")],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("连通性预检失败，退出。")
        print(result.stdout)
        print(result.stderr)
        sys.exit(1)
    print()

    all_results = {}
    total_cost = 0.0
    all_boundary = []

    for i, t_key in enumerate(["T1", "T2", "T3"]):
        capture = (t_key == "T1")  # D-47: T1 的 Writer 请求体落盘
        print(f"--- 生成 {t_key} {'(D-47 请求体捕获)' if capture else ''} ---")

        res = await generate_one(t_key, capture_request_body=capture)

        # 落盘 clean 正文
        if res["final_text"]:
            clean_path = BASELINE_DIR / f"{t_key}_clean.md"
            clean_path.write_text(res["final_text"], encoding="utf-8")
            print(f"  → {clean_path} ({res['word_count']} 字)")
        else:
            print(f"  → {t_key} 生成失败（空正文）")

        # D-47 落盘
        if res["captured_body"]:
            req_path = BASELINE_DIR / "writer_request_body.json"
            req_path.write_text(
                json.dumps(res["captured_body"], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"  → D-47 请求体: {req_path}")

        total_cost += res["cost_cny"]
        all_boundary.extend(res["boundary_events"])
        all_results[t_key] = res
        print(f"  cost: {res['elapsed_seconds']:.1f}s, CNY{res['cost_cny']:.4f}")
        print()

    # 汇总落盘
    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_cost_cny": total_cost,
        "budget_estimate_cny": 0.90,
        "budget_limit_cny": 1.20,
        "chapters": {},
        "boundary_events": all_boundary,
    }
    for t_key, res in all_results.items():
        summary["chapters"][t_key] = {
            "word_count": res["word_count"],
            "cost_cny": res["cost_cny"],
            "elapsed_seconds": res["elapsed_seconds"],
            "stage_latencies": res["stage_latencies"],
        }

    (BASELINE_DIR / "cost_breakdown.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("=" * 60)
    print(f"三章生成完成")
    print(f"total cost: CNY{total_cost:.4f} (budget 0.90, limit 1.20)")
    print(f"边界事件: {len(all_boundary)} 个")
    for be in all_boundary:
        print(f"  [{be.get('type')}] {be}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
