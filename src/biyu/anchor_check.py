"""Anchor check 引擎 — 纯确定性 value-match,零 LLM。

P6-A2: 从 tools/anchor_checker.py 抽出引擎核心入包, 供 auditor 和 CLI 共用。
包内 import 不依赖 repo 根的 tools/ 目录(装包后也可用)。

判定(value-match 三态, 纯子串字符比对, 不造归一化引擎):
1. canonical 或 alias 命中 → status="present"
2. 否则若 mismatch_aliases(错值 distractor)命中 → status="value_mismatch"
3. 否则 → status="missing"

归一化: 全角→半角(字母/数字/标点), 连续空白压缩为单空格, strip。
不做数字自动转换(确定性优先)。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# 归一化
# ---------------------------------------------------------------------------
_FULLWIDTH_MAP = str.maketrans(
    "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
    "０１２３４５６７８９"
    "！＠＃＄％＾＆＊（）－＝＋［］｛｝；＇：＂，．／＜＞？",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789"
    "!@#$%^&*()-=+[]{};':\",./<>?",
)


def normalize(text: str) -> str:
    """归一化: 全角→半角, 连续空白压缩为单空格, strip 首尾。"""
    text = text.translate(_FULLWIDTH_MAP)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------
def load_anchors(yaml_path: str | Path) -> dict[str, Any]:
    """加载 anchors.yaml, 返回原始字典。"""
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_text(file_path: str | Path) -> str:
    """加载待检测文本文件。"""
    p = Path(file_path)
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 检测逻辑
# ---------------------------------------------------------------------------
def check_atomic(
    anchors_list: list[dict], text: str
) -> list[dict]:
    """检查 atomic 锚点命中情况(value-match 三态)。

    判定优先级:
    1. canonical 或任一 alias 命中 → status="present"
    2. 否则若任一 mismatch_aliases(错值 distractor)命中 → status="value_mismatch"
    3. 否则 → status="missing"

    hit 字段保留向后兼容(== status=="present")。
    distractor 仅做 string/别名级子串比对, 不做同义归一化(D-43 边界)。
    生成章里未声明 distractor 的 novel 错值会落为 missing(已知局限, slot-pattern 留下一刀)。
    """
    norm_text = normalize(text)
    results = []
    for a in anchors_list:
        anchor_id = a["id"]
        anchor_type = a["type"]
        canonical = a["canonical"]
        aliases = a.get("aliases", [])
        mismatch_aliases = a.get("mismatch_aliases", [])
        cross_chapter = a.get("cross_chapter_of")

        norm_canonical = normalize(canonical)
        status = "missing"
        hit = False
        hit_by = None
        mismatch_by = None

        # 1. present: canonical 或 alias
        if norm_canonical in norm_text:
            status = "present"
            hit = True
            hit_by = canonical
        else:
            for alias in aliases:
                if normalize(alias) in norm_text:
                    status = "present"
                    hit = True
                    hit_by = alias
                    break

        # 2. value_mismatch: canonical 未命中才查 distractor(canonical 优先)
        if not hit:
            for distractor in mismatch_aliases:
                if normalize(distractor) in norm_text:
                    status = "value_mismatch"
                    mismatch_by = distractor
                    break

        results.append({
            "id": anchor_id,
            "type": anchor_type,
            "canonical": canonical,
            "hit": hit,
            "hit_by": hit_by,
            "status": status,
            "mismatch_by": mismatch_by,
            "cross_chapter_of": cross_chapter,
        })
    return results


def check_composite(
    composite_list: list[dict], atomic_results: list[dict]
) -> list[dict]:
    """检查 composite 锚点命中情况。

    命中条件: 所有 members 对应的 atomic 全部命中(AND)。
    """
    hit_map = {r["id"]: r["hit"] for r in atomic_results}
    results = []
    for c in composite_list:
        members = c["members"]
        all_hit = all(hit_map.get(m, False) for m in members)
        member_details = [
            {"id": m, "hit": hit_map.get(m, False)} for m in members
        ]
        results.append({
            "id": c["id"],
            "name": c["name"],
            "all_hit": all_hit,
            "members": member_details,
        })
    return results


# ---------------------------------------------------------------------------
# 统计汇总
# ---------------------------------------------------------------------------
def compute_stats(
    chapter_id: str,
    atomic_results: list[dict],
    composite_results: list[dict] | None = None,
) -> dict[str, Any]:
    """按类型汇总命中统计(present / value_mismatch / missing 三态分桶)。"""
    total = len(atomic_results)
    hits = sum(1 for r in atomic_results if r["hit"])
    value_mismatch = sum(
        1 for r in atomic_results if r.get("status") == "value_mismatch"
    )

    # 按类型分组
    type_stats: dict[str, dict[str, int]] = {}
    for r in atomic_results:
        t = r["type"]
        if t not in type_stats:
            type_stats[t] = {"total": 0, "hit": 0, "value_mismatch": 0}
        type_stats[t]["total"] += 1
        if r["hit"]:
            type_stats[t]["hit"] += 1
        elif r.get("status") == "value_mismatch":
            type_stats[t]["value_mismatch"] += 1

    # 跨章锚子集(T3 等)
    cross_chapter = [r for r in atomic_results if r.get("cross_chapter_of")]
    cross_total = len(cross_chapter)
    cross_hits = sum(1 for r in cross_chapter if r["hit"])

    stats = {
        "chapter": chapter_id,
        "atomic": {
            "total": total,
            "hit": hits,
            "value_mismatch": value_mismatch,
            "miss": total - hits - value_mismatch,
            "ratio": hits / total if total > 0 else 0.0,
        },
        "by_type": {},
        "cross_chapter": {
            "total": cross_total,
            "hit": cross_hits,
            "ratio": cross_hits / cross_total if cross_total > 0 else None,
        },
    }

    for t, s in type_stats.items():
        stats["by_type"][t] = {
            "total": s["total"],
            "hit": s["hit"],
            "value_mismatch": s["value_mismatch"],
            "miss": s["total"] - s["hit"] - s["value_mismatch"],
            "ratio": s["hit"] / s["total"] if s["total"] > 0 else 0.0,
        }

    # composite
    if composite_results is not None:
        comp_total = len(composite_results)
        comp_hits = sum(1 for r in composite_results if r["all_hit"])
        stats["composite"] = {
            "total": comp_total,
            "hit": comp_hits,
            "ratio": comp_hits / comp_total if comp_total > 0 else None,
        }

    return stats


# ---------------------------------------------------------------------------
# 完整检测流程
# ---------------------------------------------------------------------------
def run_check_text(
    yaml_path: str | Path,
    text: str,
    chapter_id: str,
) -> dict[str, Any]:
    """对内存文本执行完整锚点检测(细纲层 planning_text 等不落盘场景)。

    Args:
        yaml_path: anchors.yaml 路径
        text: 待检测文本(细纲或正文)
        chapter_id: 章节标识(如 T1/T2/T3), 必填
    """
    anchors_data = load_anchors(yaml_path)

    chapter_data = anchors_data.get(chapter_id, {})
    atomic_list = chapter_data.get("atomic", [])
    composite_list = chapter_data.get("composite", [])

    atomic_results = check_atomic(atomic_list, text)
    composite_results = check_composite(composite_list, atomic_results) if composite_list else []
    stats = compute_stats(chapter_id, atomic_results, composite_results)

    return {
        "chapter": chapter_id,
        "atomic_results": atomic_results,
        "composite_results": composite_results,
        "stats": stats,
    }


def run_check(
    yaml_path: str | Path,
    text_path: str | Path,
    chapter_id: str | None = None,
) -> dict[str, Any]:
    """对单个文本文件执行完整锚点检测。

    Args:
        yaml_path: anchors.yaml 路径
        text_path: 待检测文本路径
        chapter_id: 章节标识(如 T1/T2/T3), 若 None 则从文件名推断

    Returns:
        完整检测报告字典
    """
    text = load_text(text_path)
    if chapter_id is None:
        chapter_id = Path(text_path).stem.split("_")[0].upper()

    report = run_check_text(yaml_path, text, chapter_id)
    report["source_file"] = str(text_path)
    return report


def run_two_layer_check(
    yaml_path: str | Path,
    chapter_id: str,
    skeleton_text: str,
    body_text: str,
) -> dict[str, Any]:
    """细纲层 + 正文层 便利函数(同一 anchors / chapter_id 跑两次)。

    用于 P6-A2 转正: Architect 出细纲后跑 skeleton(非阻塞早闸),
    Writer 出正文后跑 body(正文层 QC, 已由 AnchorCheckAuditor 承载)。

    Args:
        yaml_path: anchors.yaml 路径
        chapter_id: 章节标识(如 T1)
        skeleton_text: 细纲文本(Stage 1 planning_text)
        body_text: 正文文本(Writer final_text)

    Returns:
        {"skeleton": <report>, "body": <report>}
    """
    return {
        "skeleton": run_check_text(yaml_path, skeleton_text, chapter_id),
        "body": run_check_text(yaml_path, body_text, chapter_id),
    }
