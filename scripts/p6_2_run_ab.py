#!/usr/bin/env python3
"""P6-2 A/B orchestrator。

跑 baseline(无 patch)vs template(有 patch)各 3 章 Architect + Writer pipeline,
提取 planning.md,跑 genre_structure_checker 对比。

控制变量:
- baseline 和 template 除 patch 外完全相同(sub_md/characters/worldbook 一致)
- 同一隔离测试书 EV1_回声巷(非真书)
- n=1 each(小 n,只作方向,不下幅度结论)

输出:
- eval_set_v0/p6_genre/baseline/ch[N]/planning.md
- eval_set_v0/p6_genre/template/ch[N]/planning.md
- eval_set_v0/p6_genre/comparison/{out.json,out.md}
- eval_set_v0/p6_genre/cost_breakdown.json
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path

# 纪律:Windows GBK 陷阱(P6-人味 栽过)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

EVAL_DIR = PROJECT_ROOT / "eval_set_v0"
BOOK_DIR = PROJECT_ROOT / "data" / "EV1_回声巷"  # 隔离测试书,非真书
OUTPUT_ROOT = EVAL_DIR / "p6_genre"
YAML_PATH = EVAL_DIR / "template_genre.yaml"
MARKERS_PATH = EVAL_DIR / "genre_markers.yaml"

from generate_baseline import setup_book_dir, get_truth_source  # noqa: E402


def get_chapter_key(ch: int) -> str:
    return f"T{ch}"


async def run_one_chapter(chapter_num: int, side: str) -> dict:
    """跑一章 pipeline,复制 planning.md,返回 metrics。"""
    chapter_key = get_chapter_key(chapter_num)
    truth_source = get_truth_source(chapter_key)

    # 每章重新 setup(切换 truth 来源)
    setup_book_dir(BOOK_DIR, chapter_key, truth_source)

    from biyu.pipeline import generate_chapter

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
            "side": side,
            "error": str(e),
            "traceback": tb,
        })
        print(f"  [FAIL] {side}/{chapter_key}: {e}")
        print(tb)

    elapsed = time.time() - t0

    # 复制 planning.md
    planning_src = BOOK_DIR / "logs" / f"ch{chapter_num}" / "planning.md"
    dest_dir = OUTPUT_ROOT / side / f"ch{chapter_num}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    planning_dest = dest_dir / "planning.md"
    if planning_src.exists():
        shutil.copy2(planning_src, planning_dest)
        print(f"  → {planning_dest}")
    else:
        print(f"  [WARN] planning.md 未生成:{planning_src}")
        boundary_events.append({
            "type": "PLANNING_MISSING",
            "chapter": chapter_key,
            "side": side,
        })

    if result is not None:
        for w in result.warnings:
            boundary_events.append({"type": "WARNING", "detail": w, "side": side, "chapter": chapter_key})

    return {
        "chapter_key": chapter_key,
        "side": side,
        "word_count": result.word_count if result else 0,
        "cost_cny": result.cost_cny if result else 0.0,
        "elapsed_seconds": elapsed,
        "boundary_events": boundary_events,
        "planning_path": str(planning_dest) if planning_src.exists() else None,
    }


async def run_side(side: str, chapters: list[int]) -> list[dict]:
    results = []
    for ch in chapters:
        print(f"[{side}] ch{ch} ...", flush=True)
        r = await run_one_chapter(ch, side=side)
        results.append(r)
        print(f"[{side}] ch{ch} done ({r['word_count']} 字, CNY{r['cost_cny']:.4f})", flush=True)
    return results


def run_checker(chapters: list[int]) -> dict:
    from tools.genre_structure_checker import run_check

    files = []
    labels = []
    for side in ["baseline", "template"]:
        for ch in chapters:
            p = OUTPUT_ROOT / side / f"ch{ch}" / "planning.md"
            if p.exists():
                files.append(p)
                labels.append(f"{side}_ch{ch}")

    comparison_dir = OUTPUT_ROOT / "comparison"
    comparison_dir.mkdir(parents=True, exist_ok=True)
    return run_check(MARKERS_PATH, files, labels, comparison_dir)


async def amain():
    chapters = [1, 2, 3]

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    # 预检:config 真实 yaml(P6-人味 教训)
    if not (PROJECT_ROOT / "config" / "models.yaml").exists():
        print("[FATAL] config/models.yaml 不存在 — 运行前需从 /e/webnovel/biyu/config/ 复制")
        sys.exit(1)

    print("=" * 60)
    print("P6-2 A/B 验证")
    print(f"  book: EV1_回声巷(隔离测试书)")
    print(f"  chapters: {chapters}")
    print(f"  n=1 each(只作方向,不下幅度)")
    print(f"  输出: {OUTPUT_ROOT}")
    print("=" * 60)

    # ---- baseline(无 patch)----
    print("\n--- BASELINE(原 Architect,无 genre_block)---")
    baseline_results = await run_side("baseline", chapters)

    # ---- 安装 patch ----
    print("\n--- 安装 genre monkey-patch(双绑定 vo+pipe)---")
    from p6_2_generate_template_variant import install_genre_patch
    install_genre_patch(YAML_PATH)
    print("  patch 已安装")

    # ---- template(patch 激活)----
    print("\n--- TEMPLATE(genre_block 注入)---")
    template_results = await run_side("template", chapters)

    # ---- checker ----
    print("\n--- 运行 genre_structure_checker ---")
    report = run_checker(chapters)
    print(f"  报告:{OUTPUT_ROOT / 'comparison' / 'out.md'}")

    # ---- 成本汇总 ----
    total_cost = sum(r["cost_cny"] for r in baseline_results + template_results)
    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "chapters": chapters,
        "n_per_side": 1,
        "baseline_cost_cny": sum(r["cost_cny"] for r in baseline_results),
        "template_cost_cny": sum(r["cost_cny"] for r in template_results),
        "total_cost_cny": total_cost,
        "budget_limit_cny": 2.0,
        "baseline_results": baseline_results,
        "template_results": template_results,
        "comparison_report": report,
    }
    (OUTPUT_ROOT / "cost_breakdown.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n" + "=" * 60)
    print(f"A/B 完成")
    print(f"  baseline cost: CNY{summary['baseline_cost_cny']:.4f}")
    print(f"  template cost: CNY{summary['template_cost_cny']:.4f}")
    print(f"  total:         CNY{total_cost:.4f} / 上限 ¥2.0")
    print(f"  报告: {OUTPUT_ROOT / 'comparison' / 'out.md'}")
    print("=" * 60)


def main():
    asyncio.run(amain())


if __name__ == "__main__":
    main()
