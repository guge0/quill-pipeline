#!/usr/bin/env python3
"""P6-13-C Step 5: post-modification anchor measurement + comparison report."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.anchor_checker import run_check, generate_json_report

YAML_PATH = "eval_set_v0/anchors.yaml"


def main():
    # 1. 正文检测 (6 个)
    text_results = []
    for ch in ["T1", "T2", "T3"]:
        for run in [1, 2]:
            text_path = f"eval_set_v0/post_c/{ch}_run{run}.md"
            report = run_check(YAML_PATH, text_path, ch)
            report["run"] = run
            text_results.append(report)

    # 2. 细纲检测 (6 个)
    outline_results = []
    for ch in ["T1", "T2", "T3"]:
        for run in [1, 2]:
            outline_path = f"eval_set_v0/post_c/outlines/{ch}_run{run}_outline.md"
            report = run_check(YAML_PATH, outline_path, ch)
            report["run"] = run
            outline_results.append(report)

    # 3. 加载基线
    with open("eval_set_v0/measurements/baseline_anchor_report.json", "r", encoding="utf-8") as f:
        baseline_data = json.load(f)
    baseline_map = {r["chapter"]: r for r in baseline_data}

    # 4. 构建报告
    L = []
    L.append("# P6-13-C Post-Modification Anchor Report\n")
    L.append("## 测量口径\n")
    L.append("- 端到端: sub-md -> 正文")
    L.append("- 细纲层: sub-md -> 细纲 (检查 Architect 输出是否包含锚点)")
    L.append("- 检测工具: tools/anchor_checker.py (纯确定性,零 LLM)\n")

    # 一、端到端
    L.append("## 一、端到端 (sub-md -> 正文)\n")
    L.append("### 1.1 基线 vs 改造后 (按章)\n")
    L.append("| 章节 | 基线命中率 | run1 命中率 | run2 命中率 | 波动(run1-run2) |")
    L.append("|------|-----------|-----------|-----------|---------------|")

    for ch in ["T1", "T2", "T3"]:
        bl = baseline_map[ch]["stats"]["atomic"]
        bl_pct = f'{bl["ratio"]*100:.1f}%'
        r1 = [r for r in text_results if r["chapter"] == ch and r["run"] == 1][0]
        r2 = [r for r in text_results if r["chapter"] == ch and r["run"] == 2][0]
        r1_pct = r1["stats"]["atomic"]["ratio"] * 100
        r2_pct = r2["stats"]["atomic"]["ratio"] * 100
        swing = abs(r1_pct - r2_pct)
        L.append(f"| {ch} | {bl_pct} | {r1_pct:.1f}% | {r2_pct:.1f}% | {swing:.1f}pp |")
    L.append("")

    # 阈值标注
    L.append("### 1.2 阈值标注 (端到端 >= 90% = 达标)\n")
    for ch in ["T1", "T2", "T3"]:
        r1 = [r for r in text_results if r["chapter"] == ch and r["run"] == 1][0]
        r2 = [r for r in text_results if r["chapter"] == ch and r["run"] == 2][0]
        avg = (r1["stats"]["atomic"]["ratio"] + r2["stats"]["atomic"]["ratio"]) / 2 * 100
        st = "达标" if avg >= 90 else "未达标"
        L.append(f"- {ch}: 平均 {avg:.1f}% [{st}]")
    L.append("")

    # 按类型
    L.append("### 1.3 按类型统计 (基线 vs 改造后加权)\n")
    all_types = set()
    for ch in ["T1", "T2", "T3"]:
        all_types.update(baseline_map[ch]["stats"].get("by_type", {}).keys())
        for r in text_results:
            if r["chapter"] == ch:
                all_types.update(r["stats"].get("by_type", {}).keys())

    bl_t = {}
    bl_h = {}
    pc_t = {}
    pc_h = {}
    for ch in ["T1", "T2", "T3"]:
        for t, s in baseline_map[ch]["stats"].get("by_type", {}).items():
            bl_t[t] = bl_t.get(t, 0) + s["total"]
            bl_h[t] = bl_h.get(t, 0) + s["hit"]
    for r in text_results:
        for t, s in r["stats"].get("by_type", {}).items():
            pc_t[t] = pc_t.get(t, 0) + s["total"]
            pc_h[t] = pc_h.get(t, 0) + s["hit"]

    L.append("| 类型 | 基线(加权) | 改造后(加权) |")
    L.append("|------|-----------|-------------|")
    for t in sorted(all_types):
        br = f'{bl_h.get(t,0)/bl_t[t]*100:.1f}%' if bl_t.get(t) else "N/A"
        pr = f'{pc_h.get(t,0)/pc_t[t]*100:.1f}%' if pc_t.get(t) else "N/A"
        L.append(f"| {t} | {br} | {pr} |")
    L.append("")

    # 约定+设定
    L.append("### 1.4 约定+设定 (已证实重灾区)\n")
    L.append("| 章节 | run | 约定 命中/总数 | 设定 命中/总数 | 合计 | 阈值(>=85%) |")
    L.append("|------|-----|--------------|--------------|------|------------|")

    for ch in ["T1", "T2", "T3"]:
        bl_s = baseline_map[ch]["stats"].get("by_type", {})
        bl_ag = bl_s.get("约定", {})
        bl_se = bl_s.get("设定", {})
        bl_tot = bl_ag.get("total", 0) + bl_se.get("total", 0)
        bl_hit = bl_ag.get("hit", 0) + bl_se.get("hit", 0)
        bl_pct = f'{bl_hit/bl_tot*100:.1f}%' if bl_tot else "N/A"
        L.append(f"| {ch} | baseline | {bl_ag.get('hit',0)}/{bl_ag.get('total',0)} | {bl_se.get('hit',0)}/{bl_se.get('total',0)} | {bl_hit}/{bl_tot} ({bl_pct}) | - |")

        for r in [r for r in text_results if r["chapter"] == ch]:
            s = r["stats"].get("by_type", {})
            ag = s.get("约定", {})
            se = s.get("设定", {})
            tot = ag.get("total", 0) + se.get("total", 0)
            hit = ag.get("hit", 0) + se.get("hit", 0)
            pct = hit / tot * 100 if tot else 0
            st = "达标" if pct >= 85 else "未达标"
            L.append(f"| {ch} | run{r['run']} | {ag.get('hit',0)}/{ag.get('total',0)} | {se.get('hit',0)}/{se.get('total',0)} | {hit}/{tot} ({pct:.1f}%) | {st} |")
    L.append("")

    # T3 跨章锚
    L.append("### 1.5 T3 跨章锚 (cross_chapter_of 子集)\n")
    bl_t3cc = baseline_map["T3"]["stats"].get("cross_chapter", {})
    L.append(f"- T3 baseline: {bl_t3cc.get('hit',0)}/{bl_t3cc.get('total',0)} = {bl_t3cc.get('ratio',0)*100:.1f}%")
    for r in [r for r in text_results if r["chapter"] == "T3"]:
        cc = r["stats"].get("cross_chapter", {})
        L.append(f"- T3 run{r['run']}: {cc.get('hit',0)}/{cc.get('total',0)} = {cc.get('ratio',0)*100:.1f}%")
    L.append("")

    # Composite
    L.append("### 1.6 Composite 通过情况\n")
    for ch in ["T1", "T3"]:
        bl_c = baseline_map[ch]["stats"].get("composite", {})
        if bl_c and bl_c.get("total"):
            L.append(f"- {ch} baseline: {bl_c['hit']}/{bl_c['total']}")
        for r in [r for r in text_results if r["chapter"] == ch]:
            comp = r["stats"].get("composite", {})
            if comp and comp.get("total"):
                L.append(f"- {ch} run{r['run']}: {comp['hit']}/{comp['total']}")
    L.append("")

    # 分层
    L.append("## 二、分层测量 (sub-md -> 细纲)\n")
    L.append("| 章节 | run | 细纲命中率 | 正文命中率 | 细纲->正文损失 |")
    L.append("|------|-----|-----------|-----------|--------------|")
    for ch in ["T1", "T2", "T3"]:
        for run in [1, 2]:
            ol = [r for r in outline_results if r["chapter"] == ch and r["run"] == run][0]
            tx = [r for r in text_results if r["chapter"] == ch and r["run"] == run][0]
            ol_p = ol["stats"]["atomic"]["ratio"] * 100
            tx_p = tx["stats"]["atomic"]["ratio"] * 100
            loss = ol_p - tx_p
            L.append(f"| {ch} | run{run} | {ol_p:.1f}% | {tx_p:.1f}% | -{loss:.1f}pp |")
    L.append("")

    # 波动
    L.append("## 三、两次重复波动幅度\n")
    L.append("| 章节 | run1 | run2 | 波动 |")
    L.append("|------|------|------|------|")
    for ch in ["T1", "T2", "T3"]:
        r1 = [r for r in text_results if r["chapter"] == ch and r["run"] == 1][0]
        r2 = [r for r in text_results if r["chapter"] == ch and r["run"] == 2][0]
        r1p = r1["stats"]["atomic"]["ratio"] * 100
        r2p = r2["stats"]["atomic"]["ratio"] * 100
        sw = abs(r1p - r2p)
        L.append(f"| {ch} | {r1p:.1f}% | {r2p:.1f}% | {sw:.1f}pp |")
    L.append("")

    # 费用
    with open("eval_set_v0/post_c/cost_breakdown.json", "r", encoding="utf-8") as f:
        cost_data = json.load(f)
    L.append("## 四、实际花费 vs 估算\n")
    L.append(f"- 估算: CNY {cost_data['budget_estimate_cny']:.2f}")
    L.append(f"- 实际: CNY {cost_data['total_cost_cny']:.4f}")
    L.append(f"- 上限: CNY {cost_data['budget_limit_cny']:.2f}\n")

    # 边界事件
    L.append("## 五、边界事件清单\n")
    be = cost_data.get("boundary_events", [])
    if be:
        for e in be:
            L.append(f"- [{e.get('type','?')}] {e}")
    else:
        L.append("- 无")
    L.append("")

    # 保存
    report_text = "\n".join(L)
    Path("eval_set_v0/measurements/post_c_anchor_report.md").write_text(report_text, encoding="utf-8")
    generate_json_report(text_results, "eval_set_v0/measurements/post_c_anchor_report.json")

    print(report_text)


if __name__ == "__main__":
    main()
