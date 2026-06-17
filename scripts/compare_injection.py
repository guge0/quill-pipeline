#!/usr/bin/env python3
"""P6-A1 A4-V0 Part 3 — 改造前后对比。

对 baseline 与 post_injection 两条件的三章正文+细纲重打分, 输出 missing/present
/value_mismatch 计数对比表。两条件都用同一个 value-match checker(P6-A2), 唯一
变量是管线里的 truth_filter_enabled(False vs True)。

输入:
- eval_set_v0/baseline/T{1,2,3}_clean.md         (改造前正文)
- eval_set_v0/post_injection/T{1,2,3}_clean.md   (改造后正文)
- eval_set_v0/post_injection/T{1,2,3}_planning.md(改造后细纲)
- eval_set_v0/anchors.yaml

输出:
- eval_set_v0/comparison_results/injection_vs_baseline.json
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = PROJECT_ROOT / "eval_set_v0"
ANCHORS_YAML = EVAL_DIR / "anchors.yaml"
BASELINE_DIR = EVAL_DIR / "baseline"
POST_DIR = EVAL_DIR / "post_injection"
OUT_DIR = EVAL_DIR / "comparison_results"


def score_layer(yaml_path: Path, chapter_key: str, text: str) -> dict:
    """对一章文本运行 value-match, 返回 stats.atomic + value_mismatch 列表。"""
    from biyu.anchor_check import run_check_text
    report = run_check_text(str(yaml_path), text, chapter_key)
    atomic = report["stats"]["atomic"]
    # 抓出 value_mismatch 条目详情
    mismatches = [
        {"id": r["id"], "canonical": r["canonical"], "mismatch_by": r.get("mismatch_by")}
        for r in report["atomic_results"]
        if r.get("status") == "value_mismatch"
    ]
    misses = [
        {"id": r["id"], "canonical": r["canonical"], "type": r["type"]}
        for r in report["atomic_results"]
        if r.get("status") == "missing"
    ]
    return {
        "stats": atomic,
        "mismatches": mismatches,
        "misses": misses,
    }


def main():
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not ANCHORS_YAML.exists():
        print(f"[ERR] 缺 {ANCHORS_YAML}")
        sys.exit(1)

    out: dict = {
        "condition_baseline": {"truth_filter_enabled": False},
        "condition_post_injection": {"truth_filter_enabled": True},
        "chapters": {},
    }

    for t_key in ["T1", "T2", "T3"]:
        ch_out: dict = {}

        # 正文层 — 两条件都有
        baseline_body = (BASELINE_DIR / f"{t_key}_clean.md")
        post_body = (POST_DIR / f"{t_key}_clean.md")
        if baseline_body.exists() and post_body.exists():
            ch_out["body"] = {
                "baseline": score_layer(ANCHORS_YAML, t_key, baseline_body.read_text(encoding="utf-8")),
                "post_injection": score_layer(ANCHORS_YAML, t_key, post_body.read_text(encoding="utf-8")),
            }

        # 细纲层 — 仅 post_injection 有 planning 落盘
        post_plan = (POST_DIR / f"{t_key}_planning.md")
        if post_plan.exists():
            ch_out["skeleton_post_injection"] = score_layer(
                ANCHORS_YAML, t_key, post_plan.read_text(encoding="utf-8"),
            )

        out["chapters"][t_key] = ch_out

    # 汇总表(打到 stdout + 落 json)
    print("=" * 70)
    print("P6-A1 A4-V0 — 注入条件 vs 基线 (正文层 value-match 重打分)")
    print("=" * 70)
    print(f"{'章':<4} {'条件':<16} {'在场':>6} {'值错':>6} {'缺':>6} {'共':>6} {'命中率':>8}")
    print("-" * 70)
    for t_key, ch in out["chapters"].items():
        if "body" not in ch:
            continue
        for cond_name, label in [
            ("baseline", "baseline (F)"),
            ("post_injection", "post_inj (T)"),
        ]:
            s = ch["body"][cond_name]["stats"]
            ratio = s.get("ratio")
            ratio_str = f"{ratio*100:.1f}%" if ratio is not None else "n/a"
            print(f"{t_key:<4} {label:<16} {s['hit']:>6} {s['value_mismatch']:>6} "
                  f"{s['miss']:>6} {s['total']:>6} {ratio_str:>8}")
        # delta
        b = ch["body"]["baseline"]["stats"]
        p = ch["body"]["post_injection"]["stats"]
        d_miss = p["miss"] - b["miss"]
        d_hit = p["hit"] - b["hit"]
        d_vm = p["value_mismatch"] - b["value_mismatch"]
        print(f"{'':<4} {'DELTA':<16} {d_hit:>+6} {d_vm:>+6} {d_miss:>+6}")
        print("-" * 70)

    out_path = OUT_DIR / "injection_vs_baseline.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n详细结果: {out_path}")


if __name__ == "__main__":
    main()
