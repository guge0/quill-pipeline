#!/usr/bin/env python3
"""P6-人味 A/B 对比: 基线 vs 改版(反机械)整篮子升降 + 代偿声明。

读 baseline_scores.json(基线 ¥0 重打分,Task 5 产物)+ variant/run*_*_final.md
(改版生成,Task 8.1 产物),按章聚合(改版 n runs 取均值),输出:
- comparison_report.md: 章节指标升降表 + 代偿自检声明 + 边缘数据归类
- comparison_data.json: 机读版相同数据

⚠ §4 / §8: n 小,只看趋势方向,不下幅度结论。所有 proxy 指标带 disclaimer。
⚠ D-45: RUN_FAIL/SHORT_CHAPTER/degenerate 的边缘数据单独归类,不混入统计桶。
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from biyu.ai_traits import measure_all  # noqa: E402

HUM = PROJECT_ROOT / "eval_set_v0" / "p6_humanity"
BASELINE = HUM / "baseline_scores.json"
VARIANT_DIR = HUM / "variant"


def pick(m: dict) -> dict:
    """从 measure_all 嵌套输出中提取关心的篮子指标(平铺)。"""
    return {
        "exclaim_per_1k": m["exclaim_density_per_1k"],
        "dash_per_1k": m["dash_density_per_1k"],
        "long_unpunct_sent_ratio": m["long_unpunct_sentence_ratio"],
        "long_para_ratio": m["paragraph_lengths"]["long_para_ratio"],
        "modifier_density": m["modifier_proxy"]["density_per_1k"],
        "parallel_uniform_ratio": m["parallelism_proxy"]["uniform_run_ratio"],
        "idiom_density": m["four_char_proxy"]["idiom_density_per_1k"],
        "raw4_density": m["four_char_proxy"]["raw_density_per_1k"],
    }


def main() -> None:
    # --- 基线(单次,n=1)---
    base_raw = json.loads(BASELINE.read_text(encoding="utf-8"))
    base = {r["chapter"]: pick(r["metrics"]) for r in base_raw}

    # --- 改版(n runs,按章聚合)---
    per_ch: dict[str, list[dict]] = {}
    edge: list[dict] = []
    n_runs_seen: set[int] = set()
    for f in sorted(VARIANT_DIR.glob("run*_*_final.md")):
        # 文件名: run{N}_{T1}_final.md → stem = "run{N}_{T1}_final"
        parts = f.stem.split("_")
        if len(parts) < 3:
            edge.append({"file": str(f), "reason": "filename_unparseable"})
            continue
        run_str, ch = parts[0], parts[1]
        try:
            n_runs_seen.add(int(run_str.replace("run", "")))
        except ValueError:
            pass
        text = f.read_text(encoding="utf-8")
        if not text.strip():
            edge.append({"file": str(f), "reason": "empty_file"})
            continue
        m = measure_all(text)
        if m["degenerate"]:
            edge.append({"file": str(f), "reason": "degenerate(CJK=0)"})
            continue
        per_ch.setdefault(ch, []).append(pick(m))

    n_runs = max(n_runs_seen) if n_runs_seen else 0

    # --- 输出 ---
    lines: list[str] = []
    lines.append("# P6-人味 A/B 对比: 基线 vs 反机械改版\n")
    lines.append(f"改版运行次数 n = {n_runs}(基线 n=1)\n")
    lines.append("")
    lines.append("⚠ 所有 proxy 指标(disclaimer): 仅作趋势参考,不代表人味/AI 味判定。")
    lines.append("⚠ n 小,只看方向,不下幅度结论(§4)。\n")
    lines.append("## 章节指标升降表\n")
    lines.append("| 章 | 指标 | 基线 | 改版(均值) | Δ | 方向 |")
    lines.append("|---|---|---|---|---|---|")

    comp: dict[str, dict] = {}
    for ch in ["T1", "T2", "T3"]:
        if ch not in base or ch not in per_ch:
            continue
        runs = per_ch[ch]
        mean = {k: statistics.mean(r[k] for r in runs) for k in runs[0]}
        comp[ch] = {"baseline": base[ch], "variant_mean": mean, "n": len(runs)}
        for k in base[ch]:
            d = mean[k] - base[ch][k]
            arrow = "↑" if d > 0 else ("↓" if d < 0 else "→")
            lines.append(
                f"| {ch} | {k} | {base[ch][k]:.3f} | {mean[k]:.3f} | "
                f"{arrow}{abs(d):.3f} | {arrow} |"
            )

    lines.append("")

    # --- 代偿自检(§8): 降 A 升 B?---
    lines.append("## 代偿自检(降 A 升 B?)\n")
    lines.append("期望: 改版降 exclaim/dash/idiom(反机械约束直击的目标)。")
    lines.append("警惕: 同时升 modifier/parallel(代偿借尸还魂,文风变本加厉 AI 味)。\n")
    comp_summary: dict[str, dict[str, str]] = {}
    for ch, data in comp.items():
        b, v = data["baseline"], data["variant_mean"]
        directions = {}
        for k in b:
            d = v[k] - b[k]
            directions[k] = "↑" if d > 1e-9 else ("↓" if d < -1e-9 else "→")
        comp_summary[ch] = directions
        targets_down = ["exclaim_per_1k", "dash_per_1k", "idiom_density"]
        risks_up = ["modifier_density", "parallel_uniform_ratio", "raw4_density"]
        actual_down = [k for k in targets_down if directions.get(k) == "↓"]
        actual_up = [k for k in risks_up if directions.get(k) == "↑"]
        lines.append(f"### {ch}")
        lines.append(
            f"- 期望降({','.join(targets_down)}): 实际降 {actual_down or '(无)'}"
        )
        lines.append(
            f"- 警惕升({','.join(risks_up)}): 实际升 {actual_up or '(无)'}"
        )
        if actual_up and actual_down:
            lines.append(
                f"- ⚠ **代偿信号**: 同时降 {actual_down} 升 {actual_up} —— "
                f"反机械约束可能挤压到其他维度,需人工核验正文样本。"
            )
        lines.append("")

    # --- 边缘数据(D-45 单独归类)---
    if edge:
        lines.append("## 边缘数据(单独归类,D-45)\n")
        lines.append("这些样本不进入上方统计桶,只记录在案:\n")
        for e in edge:
            lines.append(f"- `{e['file']}`: {e['reason']}")
        lines.append("")

    # --- 落盘 ---
    out_md = HUM / "comparison_report.md"
    out_json = HUM / "comparison_data.json"
    out_md.write_text("\n".join(lines), encoding="utf-8")
    out_json.write_text(
        json.dumps(
            {
                "comp": comp,
                "directions": comp_summary,
                "edge": edge,
                "n_runs_variant": n_runs,
                "n_runs_baseline": 1,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"→ {out_md}")
    print(f"→ {out_json}")
    print(f"边缘数据 {len(edge)} 条")


if __name__ == "__main__":
    main()
