#!/usr/bin/env python
"""Generate D-42 adjudication table from D-54 clean re-run captures."""
from __future__ import annotations
import json, sys
from pathlib import Path
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

base = Path("eval_set_v0/comparison_results")

# ── Ground truth (from STEP6_SCORING_DRAFT.md §3) ──
truth = [
    {"eid": "E01", "cat": "跨章·时间", "desc": "苏皓失踪日期 11/19 vs 1/16", "ch": "2", "keys": ["11/19", "1/16", "一月十六", "十一月十九", "失踪日期"]},
    {"eid": "E02", "cat": "跨章·数字", "desc": "A-131 应为 A-113", "ch": "3", "keys": ["A-131", "A-113"]},
    {"eid": "E03", "cat": "跨章·头衔", "desc": "聂守仁名字在自我介绍前被使用", "ch": "1", "keys": ["聂守仁", "怎么称呼", "自我介绍"]},
    {"eid": "E05", "cat": "逻辑·两地", "desc": "何沛电话中翻纸（视觉穿帮）", "ch": "1", "keys": ["翻纸", "翻了一页", "何沛", "电话"]},
    {"eid": "E07", "cat": "逻辑·因果", "desc": "六人体检/生物识别因果推断无中生有", "ch": "2", "keys": ["体检", "生物识别", "同一台机器", "同一机构"]},
    {"eid": "E08", "cat": "视角穿帮", "desc": "聂守仁内心被读心", "ch": "1", "keys": ["内心深处", "读心", "感知到", "承诺", "不想让他拿走"]},
    {"eid": "E09", "cat": "视角·跨章", "desc": "勿配刻字前后矛盾（首见 vs 次日再看）", "ch": "1", "keys": ["勿配", "刻字", "看清", "辨认"]},
    {"eid": "E10", "cat": "设定矛盾", "desc": "老覃工龄 32年/23年", "ch": "3", "keys": ["三十二年", "二十三年", "32年", "23年", "老覃"]},
    {"eid": "E11", "cat": "设定矛盾", "desc": "一件证物/三件证物", "ch": "1", "keys": ["一件证物", "三件证物", "证物"]},
    {"eid": "E12", "cat": "跨章·地点", "desc": "黄铜钥匙编号 第三项/第五项", "ch": "1", "keys": ["第三项", "第五项", "编号"]},
]

excluded = [
    {"eid": "E04", "cat": "跨章·约定", "desc": "需要 truth_files 才能检测"},
    {"eid": "E06", "cat": "逻辑·数字", "desc": "文本中不存在此事实"},
    {"eid": "E13", "cat": "跨章·时间", "desc": "需要 truth_files 才能检测"},
    {"eid": "E14", "cat": "—", "desc": "(未在 STEP6 明确列出)"},
]

# ── Extract all flags ──
runs_cfg = [
    ("d54_single", "d54_multi", "single-r1", "multi-r1"),
    ("d54_r2_single", "d54_r2_multi", "single-r2", "multi-r2"),
    ("d54_r3_single", "d54_r3_multi", "single-r3", "multi-r3"),
]

all_flags: list[dict] = []

def _get_ch(msgs):
    for m in msgs:
        c = m.get("content", "")
        if isinstance(c, str):
            if "第 1 章" in c: return "1"
            elif "第 2 章" in c: return "2"
            elif "第 3 章" in c: return "3"
    return "?"

def _extract_submit_issues(tc_func):
    try:
        args = json.loads(tc_func.get("arguments", "{}"))
        return args.get("issues", [])
    except json.JSONDecodeError:
        return None

for s_dir, m_dir, s_label, m_label in runs_cfg:
    # Single
    for f in sorted((base / s_dir).glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        ch = _get_ch(data.get("request", {}).get("messages", []))
        raw = data.get("response", {}).get("raw", {})
        choices = raw.get("choices", [{}])
        msg_d = choices[0].get("message", {}) if choices else {}
        for tc in msg_d.get("tool_calls", []):
            if tc["function"]["name"] == "submit_review":
                issues = _extract_submit_issues(tc["function"])
                if issues is None:
                    all_flags.append({"run": s_label, "ch": ch, "type": "PARSE_ERROR",
                        "paragraph": "", "keyword": "", "description": "submit_review JSON parse failed", "severity": "—"})
                else:
                    for iss in issues:
                        all_flags.append({
                            "run": s_label, "ch": ch,
                            "type": iss.get("type", "?"),
                            "paragraph": str(iss.get("paragraph", iss.get("line", ""))),
                            "keyword": (iss.get("keyword", "") or iss.get("quote", ""))[:80],
                            "description": (iss.get("description", "") or iss.get("explanation", ""))[:150],
                            "severity": iss.get("severity", "?"),
                        })

    # Multi Phase 2 only
    for f in sorted((base / m_dir).glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        msgs = data.get("request", {}).get("messages", [])
        sys_msg = ""
        for m in msgs:
            if m.get("role") == "system":
                sys_msg = m.get("content", "")[:60]
                break
        if "反思" not in sys_msg:
            continue
        agent = "?"
        if "Editor-A" in sys_msg: agent = "A"
        elif "Editor-B" in sys_msg: agent = "B"
        elif "Editor-C" in sys_msg: agent = "C"
        ch = _get_ch(msgs)
        raw = data.get("response", {}).get("raw", {})
        choices = raw.get("choices", [{}])
        msg_d = choices[0].get("message", {}) if choices else {}
        for tc in msg_d.get("tool_calls", []):
            if tc["function"]["name"] == "submit_review":
                issues = _extract_submit_issues(tc["function"])
                if issues is None:
                    all_flags.append({"run": f"{m_label}(agent-{agent})", "ch": ch, "type": "PARSE_ERROR",
                        "paragraph": "", "keyword": "", "description": "submit_review JSON parse failed", "severity": "—"})
                else:
                    for iss in issues:
                        all_flags.append({
                            "run": f"{m_label}(agent-{agent})", "ch": ch,
                            "type": iss.get("type", "?"),
                            "paragraph": str(iss.get("paragraph", iss.get("line", ""))),
                            "keyword": (iss.get("keyword", "") or iss.get("quote", ""))[:80],
                            "description": (iss.get("description", "") or iss.get("explanation", ""))[:150],
                            "severity": iss.get("severity", "?"),
                        })

# ── Machine matching ──
def match_flag(flag, truth_list):
    best_eid = "none"
    best_score = 0
    flag_ch = flag["ch"]
    flag_text = flag["keyword"] + " " + flag["description"]
    for t in truth_list:
        if flag_ch != t["ch"]:
            continue
        score = sum(1 for k in t["keys"] if k in flag_text)
        if score > best_score:
            best_score = score
            best_eid = t["eid"]
    return best_eid if best_score > 0 else "none"

for f in all_flags:
    f["guess"] = match_flag(f, truth)

# ── Generate markdown ──
lines: list[str] = []
def L(s=""):
    lines.append(s)

L("# D-42 Adjudication Table (D-54 Clean Re-runs)")
L()
L("Generated: 2026-06-12")
L("Source: D-54 smoke test + 2 clean re-runs (6 runs total: single x3 + multi x3)")
L("Status: **RAW -- TL adjudicates all flag<->E-id hits**")
L()
L("---")
L()
L("## S1 Planted Issue Ground Truth (E01-E14)")
L()
L("### Detectable (10)")
L()
L("| E-id | Category | Chapter | Description | Key Content |")
L("|------|----------|---------|-------------|-------------|")
for t in truth:
    L(f"| {t['eid']} | {t['cat']} | ch{t['ch']} | {t['desc']} | {', '.join(t['keys'][:5])} |")

L()
L("### Excluded (4)")
L()
L("| E-id | Category | Reason |")
L("|------|----------|--------|")
for e in excluded:
    L(f"| {e['eid']} | {e['cat']} | {e['desc']} |")

L()
L("---")
L()
L("## S2 Single Mode Flags (3 runs)")
L()

for run_label in ["single-r1", "single-r2", "single-r3"]:
    run_flags = [f for f in all_flags if f["run"] == run_label]
    L(f"### {run_label}")
    L()
    L("| # | Ch | Type | Para | Sev | Keyword | Description | Guess |")
    L("|---|-----|------|------|-----|---------|-------------|-------|")
    for i, f in enumerate(run_flags, 1):
        kw = f["keyword"].replace("|", "/")[:60]
        desc = f["description"].replace("|", "/")[:100]
        L(f"| {i} | ch{f['ch']} | {f['type']} | {f['paragraph']} | {f['severity']} | {kw} | {desc} | **{f['guess']}** |")
    L()

L("---")
L()
L("## S3 Multi Mode Flags -- Phase 2 Final (3 runs)")
L()

for run_label in ["multi-r1", "multi-r2", "multi-r3"]:
    run_flags = [f for f in all_flags if f["run"].startswith(run_label)]
    L(f"### {run_label}")
    L()
    L("| # | Agent | Ch | Type | Para | Sev | Keyword | Description | Guess |")
    L("|---|-------|-----|------|------|-----|---------|-------------|-------|")
    for i, f in enumerate(run_flags, 1):
        agent = f["run"].split("agent-")[-1].rstrip(")")
        kw = f["keyword"].replace("|", "/")[:60]
        desc = f["description"].replace("|", "/")[:100]
        L(f"| {i} | {agent} | ch{f['ch']} | {f['type']} | {f['paragraph']} | {f['severity']} | {kw} | {desc} | **{f['guess']}** |")
    L()

L("---")
L()
L("## S4 Machine Guess Legend")
L()
L("Match method: chapter match + keyword overlap (any truth key appears in flag keyword+description).")
L("This is a **clue only** -- TL makes final adjudication.")
L()
L("| Guess | Meaning |")
L("|-------|---------|")
L("| E01-E12 | Best keyword overlap with that planted issue |")
L("| none | No keyword overlap with any planted issue (potential FP or uncatalogued issue) |")
L()
L("---")
L()
L("## S5 Summary Stats")
L()

for run_label in ["single-r1", "single-r2", "single-r3"]:
    rf = [f for f in all_flags if f["run"] == run_label]
    types = Counter(f["type"] for f in rf)
    guesses = Counter(f["guess"] for f in rf)
    L(f"**{run_label}**: {len(rf)} flags -- types: {dict(types)} -- guesses: {dict(guesses)}")
    L()

for run_label in ["multi-r1", "multi-r2", "multi-r3"]:
    rf = [f for f in all_flags if f["run"].startswith(run_label)]
    types = Counter(f["type"] for f in rf)
    guesses = Counter(f["guess"] for f in rf)
    L(f"**{run_label}**: {len(rf)} flags -- types: {dict(types)} -- guesses: {dict(guesses)}")
    L()

L("---")
L()
L("## S6 STOP")
L()
L("Out table stop. No adjudication, no recall calculation, no D-42 conclusions. TL adjudicates each flag.")

# Write
out = base / "D42_adjudication_table.md"
out.write_text("\n".join(lines), encoding="utf-8")
print(f"Written: {out} ({len(lines)} lines, {len(all_flags)} total flags)")
