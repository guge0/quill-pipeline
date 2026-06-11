#!/usr/bin/env python3
"""P6-13-C 改造后生成脚本。

在 baseline 基础上注入锚点改造:
1. Architect: 传入 anchor_block (从 anchors.yaml 构建)
2. Writer: Layer 3 已新增锚点核对段 (chapter_writer.py 已改)

输出:
- eval_set_v0/post_c/outlines/T{n}_run{r}_outline.md  (Architect 细纲)
- eval_set_v0/post_c/T{n}_run{r}.md                    (正文)
- eval_set_v0/post_c/cost_breakdown.json

预算: B2 baseline 3章=¥0.19, 6次预估¥0.38, 上限¥0.8
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
POST_C_DIR = EVAL_DIR / "post_c"
OUTLINE_DIR = POST_C_DIR / "outlines"


def build_anchor_block_from_yaml(chapter_key: str) -> str:
    """从 anchors.yaml 构建注入 Architect 的锚点提示块。"""
    anchors_path = EVAL_DIR / "anchors.yaml"
    with open(anchors_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    chapter_data = data.get(chapter_key, {})
    atomic = chapter_data.get("atomic", [])

    if not atomic:
        return ""

    # 按类型分组
    by_type: dict[str, list[str]] = {}
    for a in atomic:
        t = a["type"]
        canonical = a["canonical"]
        by_type.setdefault(t, []).append(canonical)

    lines = ["提示:以下锚点来自 frozen anchors.yaml,请确保 sub-md 中对应事实逐条出现在你的锚点块中:", ""]
    for t in ["时间", "地点", "人物", "数字", "约定", "设定"]:
        items = by_type.get(t, [])
        if items:
            lines.append(f"- **{t}**: {', '.join(items)}")
        else:
            lines.append(f"- **{t}**: 无")
    return "\n".join(lines)


def setup_book_dir(book_dir: Path, chapter_key: str, truth_source: str):
    """创建/准备 book 目录, 桥接 B1 格式到管线格式。"""
    book_dir.mkdir(parents=True, exist_ok=True)

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

    shutil.copy2(EVAL_DIR / "worldbook.yaml", book_dir / "worldbook.yaml")

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

    tf_src = EVAL_DIR / truth_source
    tf_dst = book_dir / "truth_files"
    tf_dst.mkdir(parents=True, exist_ok=True)
    for yaml_file in tf_src.glob("*.yaml"):
        content = yaml_file.read_text(encoding="utf-8")
        md_name = yaml_file.stem + ".md"
        (tf_dst / md_name).write_text(content, encoding="utf-8")

    outline_dir = book_dir / "outlines"
    outline_dir.mkdir(parents=True, exist_ok=True)
    chapter_num = int(chapter_key[1])
    sub_md_src = EVAL_DIR / "sub_md" / f"{chapter_key}.md"
    shutil.copy2(sub_md_src, outline_dir / f"ch{chapter_num}.md")

    for sub in ["chapters", "logs", "audit_reports"]:
        d = book_dir / sub
        if d.exists():
            shutil.rmtree(d)


def get_truth_source(chapter_key: str) -> str:
    if chapter_key == "T1":
        return "truth_files"
    elif chapter_key == "T2":
        return "truth_files_frozen"
    elif chapter_key == "T3":
        return "truth_files_frozen"
    raise ValueError(f"Unknown chapter: {chapter_key}")


async def generate_one(
    chapter_key: str,
    run_num: int,
) -> dict:
    """生成单章改造后正文。"""
    from biyu.config import get_registry
    from biyu.pipeline import generate_chapter
    import biyu.prompts.v3_opening as v3_mod
    import biyu.pipeline as pipeline_mod

    chapter_num = int(chapter_key[1])
    truth_source = get_truth_source(chapter_key)

    setup_book_dir(BOOK_DIR, chapter_key, truth_source)

    # 构建 anchor_block
    anchor_block = build_anchor_block_from_yaml(chapter_key)

    # Monkey-patch build_planning_prompt to inject anchor_block
    _orig = v3_mod.build_planning_prompt

    def _patched(*args, **kwargs):
        kwargs["anchor_block"] = anchor_block
        return _orig(*args, **kwargs)

    v3_mod.build_planning_prompt = _patched
    pipeline_mod.build_planning_prompt = _patched

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
            "run": run_num,
            "error": str(e),
            "traceback": tb,
        })
        print(f"  [FAIL] {chapter_key} run{run_num}: {e}")
        print(tb)
    finally:
        # Restore original
        v3_mod.build_planning_prompt = _orig
        pipeline_mod.build_planning_prompt = _orig

    elapsed = time.time() - t0

    if result is None:
        return {
            "chapter_key": chapter_key,
            "run": run_num,
            "final_text": "",
            "outline_text": "",
            "word_count": 0,
            "cost_cny": 0,
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
        "run": run_num,
        "final_text": result.final_text,
        "outline_text": result.planning_text,
        "word_count": result.word_count,
        "cost_cny": result.cost_cny,
        "elapsed_seconds": elapsed,
        "stage_latencies": result.stage_latencies,
        "boundary_events": boundary_events,
    }


async def main():
    POST_C_DIR.mkdir(parents=True, exist_ok=True)
    OUTLINE_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("P6-13-C 改造后生成 (3章 x 2次 = 6次)")
    print("=" * 60)
    print(f"Book dir: {BOOK_DIR}")
    print(f"Output: {POST_C_DIR}")
    print()

    # 预检
    import subprocess
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "llm_connectivity_check.py")],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("连通性预检失败,退出。")
        print(result.stdout)
        print(result.stderr)
        sys.exit(1)
    print()

    # 精确估算
    # B2 baseline: 3章 = ¥0.19
    # 本脚本: 3章 x 2次 = 6次, 但改造后 prompt 更长(anchor block + Layer3 anchor check)
    # 保守估计: ¥0.19 x 2 x 1.3(prompt 加长系数) ≈ ¥0.49
    estimate = 0.49
    print(f"cost estimate: ~CNY{estimate:.2f} (limit CNY0.80)")
    if estimate > 0.80:
        print("over budget, exit.")
        sys.exit(1)
    print()

    all_results = []
    total_cost = 0.0
    all_boundary = []

    for run_num in [1, 2]:
        for t_key in ["T1", "T2", "T3"]:
            label = f"{t_key}_run{run_num}"
            print(f"--- 生成 {label} ---")

            res = await generate_one(t_key, run_num)

            # 落盘正文
            if res["final_text"]:
                text_path = POST_C_DIR / f"{t_key}_run{run_num}.md"
                text_path.write_text(res["final_text"], encoding="utf-8")
                print(f"  → {text_path} ({res['word_count']} 字)")
            else:
                print(f"  → {label} 生成失败(空正文)")

            # 落盘 Architect 细纲
            if res["outline_text"]:
                outline_path = OUTLINE_DIR / f"{t_key}_run{run_num}_outline.md"
                outline_path.write_text(res["outline_text"], encoding="utf-8")
                print(f"  → {outline_path}")

            total_cost += res["cost_cny"]
            all_boundary.extend(res["boundary_events"])
            all_results.append(res)
            print(f"  cost: {res['elapsed_seconds']:.1f}s, CNY{res['cost_cny']:.4f}")
            print()

    # 汇总
    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_cost_cny": total_cost,
        "budget_estimate_cny": estimate,
        "budget_limit_cny": 0.80,
        "runs": [],
        "boundary_events": all_boundary,
    }
    for res in all_results:
        summary["runs"].append({
            "chapter": res["chapter_key"],
            "run": res["run"],
            "word_count": res["word_count"],
            "cost_cny": res["cost_cny"],
            "elapsed_seconds": res["elapsed_seconds"],
            "stage_latencies": res["stage_latencies"],
        })

    (POST_C_DIR / "cost_breakdown.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("=" * 60)
    print(f"改造后生成完成")
    print(f"total cost: CNY{total_cost:.4f} (estimate CNY{estimate:.2f}, limit CNY0.80)")
    print(f"边界事件: {len(all_boundary)} 个")
    for be in all_boundary:
        print(f"  [{be.get('type')}] {be}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
