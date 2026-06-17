#!/usr/bin/env python3
"""P6-A1 A4-V0 Part 2 — 带注入条件生成脚本。

唯一变量: truth_filter_enabled=True (其余与 generate_baseline.py 逐字一致)。
- 复用 generate_baseline.setup_book_dir → D-45 同一书目录准备
- 复用 generate_baseline.get_truth_source → 同一 truth 来源映射
- generate_chapter(..., truth_filter_enabled=True) → 注入仅含本章出场实体的 truth

输出:
- eval_set_v0/post_injection/T{1,2,3}_clean.md       (正文)
- eval_set_v0/post_injection/T{1,2,3}_planning.md    (细纲, 用于细纲层重打分)
- eval_set_v0/post_injection/cost_breakdown.json

预算上限 ¥2.0(P6-A1 §A4-V0)。基线三章实测 ¥0.19, 同量级。
"""
import asyncio
import json
import sys
import time
from pathlib import Path

# 复用基线脚本的书目录准备与 truth 来源映射(D-45 等价准备)
from generate_baseline import setup_book_dir, get_truth_source, BOOK_DIR

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = PROJECT_ROOT / "eval_set_v0"
POST_DIR = EVAL_DIR / "post_injection"


async def generate_one(chapter_key: str) -> dict:
    """生成单章(带注入条件)。

    Returns:
        dict: chapter_key, final_text, planning_text, word_count,
              cost_cny, elapsed_seconds, stage_latencies, boundary_events
    """
    from biyu.pipeline import generate_chapter

    chapter_num = int(chapter_key[1])
    truth_source = get_truth_source(chapter_key)

    # 与 baseline 逐字一致的书目录准备(每章换 truth 来源)
    setup_book_dir(BOOK_DIR, chapter_key, truth_source)

    t0 = time.time()
    boundary_events: list = []
    result = None

    try:
        result = await generate_chapter(
            book_dir=BOOK_DIR,
            chapter_num=chapter_num,
            prompt_version="v4",
            truth_filter_enabled=True,  # ★ 唯一变量
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
            "planning_text": "",
            "word_count": 0,
            "cost_cny": 0.0,
            "elapsed_seconds": elapsed,
            "stage_latencies": {},
            "boundary_events": boundary_events,
        }

    for w in result.warnings:
        boundary_events.append({"type": "WARNING", "detail": w})
    if result.word_count < 3000:
        boundary_events.append({
            "type": "SHORT_CHAPTER",
            "word_count": result.word_count,
        })

    return {
        "chapter_key": chapter_key,
        "final_text": result.final_text,
        "planning_text": result.planning_text,
        "word_count": result.word_count,
        "cost_cny": result.cost_cny,
        "elapsed_seconds": elapsed,
        "stage_latencies": result.stage_latencies,
        "boundary_events": boundary_events,
    }


async def main():
    POST_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("P6-A1 A4-V0 Part 2 — 带注入条件生成 (truth_filter_enabled=True)")
    print("=" * 60)
    print(f"Book dir: {BOOK_DIR}")
    print(f"Output:   {POST_DIR}")
    print(f"Budget:   ¥2.0 (cap)")
    print()

    # 连通性预检(与 baseline 同款)
    import subprocess
    ck = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "llm_connectivity_check.py")],
        capture_output=True, text=True,
    )
    if ck.returncode != 0:
        print("连通性预检失败, 退出。")
        print(ck.stdout)
        print(ck.stderr)
        sys.exit(1)
    print()

    all_results = {}
    total_cost = 0.0
    all_boundary: list = []

    # 全三章; 已生成的输出默认跳过(避免烧钱重跑 LLM)。
    # 删 eval_set_v0/post_injection/T{N}_clean.md 或设 FORCE_REGEN=1 可重生。
    import os
    for t_key in ["T1", "T2", "T3"]:
        existing = POST_DIR / f"{t_key}_clean.md"
        if existing.exists() and os.environ.get("FORCE_REGEN") != "1":
            print(f"--- 跳过 {t_key} (已存在, FORCE_REGEN=1 可重生) ---")
            continue
        print(f"--- 生成 {t_key} (truth_filter_enabled=True) ---")
        res = await generate_one(t_key)

        if res["final_text"]:
            (POST_DIR / f"{t_key}_clean.md").write_text(
                res["final_text"], encoding="utf-8"
            )
            print(f"  → {t_key}_clean.md ({res['word_count']} 字)")
        else:
            print(f"  → {t_key} 生成失败(空正文)")

        if res["planning_text"]:
            (POST_DIR / f"{t_key}_planning.md").write_text(
                res["planning_text"], encoding="utf-8"
            )

        total_cost += res["cost_cny"]
        all_boundary.extend(res["boundary_events"])
        all_results[t_key] = res
        print(f"  cost: {res['elapsed_seconds']:.1f}s, ¥{res['cost_cny']:.4f}")
        print()

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "condition": "truth_filter_enabled=True",
        "total_cost_cny": total_cost,
        "budget_limit_cny": 2.0,
        "within_budget": total_cost <= 2.0,
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

    (POST_DIR / "cost_breakdown.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("=" * 60)
    print(f"三章生成完成  total cost: ¥{total_cost:.4f} (cap ¥2.0)")
    print(f"边界事件: {len(all_boundary)} 个")
    for be in all_boundary:
        print(f"  [{be.get('type')}] {be}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
