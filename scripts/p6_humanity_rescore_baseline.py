#!/usr/bin/env python3
"""P6-人味: 对 D-54 基线三章用 ai_traits 重打分(¥0,纯规则)。

输入: eval_set_v0/baseline/T{1,2,3}_clean.md
输出: eval_set_v0/p6_humanity/baseline_scores.{json,md}
不调用任何 LLM。
"""
from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_DIR = PROJECT_ROOT / "eval_set_v0" / "baseline"
OUT_DIR = PROJECT_ROOT / "eval_set_v0" / "p6_humanity"

sys.path.insert(0, str(PROJECT_ROOT))
from biyu.ai_traits import measure_all  # noqa: E402
from tools.ai_traits import generate_json_report, generate_md_report  # noqa: E402


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for ch in ["T1", "T2", "T3"]:
        p = BASELINE_DIR / f"{ch}_clean.md"
        if not p.exists():
            print(f"[WARN] 缺 {p},跳过")
            continue
        text = p.read_text(encoding="utf-8")
        results.append({"chapter": ch, "source_file": str(p),
                        "metrics": measure_all(text)})
        m = results[-1]["metrics"]
        print(f"{ch}: CJK {m['char_count_cjk']} | 感叹 {m['exclaim_density_per_1k']:.2f}/千 "
              f"| 超长句 {m['long_unpunct_sentence_ratio']*100:.1f}% | "
              f"对仗串 {m['parallelism_proxy']['uniform_run_ratio']*100:.1f}% | "
              f"四字 {m['four_char_proxy']['idiom_hits']}")
    generate_json_report(results, OUT_DIR / "baseline_scores.json")
    generate_md_report(results, OUT_DIR / "baseline_scores.md")
    print(f"→ {OUT_DIR / 'baseline_scores.json'}")


if __name__ == "__main__":
    main()
