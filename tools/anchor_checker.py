"""Anchor checker — 纯确定性工具,零 LLM。

输入: anchors.yaml + 任意文本文件
输出: 逐锚命中表 + 按类型计数比率 + composite 结果, JSON 与 MD 双格式。

归一化规则:
- 全角→半角(字母、数字、标点)
- 所有连续空白压缩为单空格
- 不做数字自动转换(确定性优先)
"""
from __future__ import annotations

import json
import re
import sys
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
    """检查 atomic 锚点命中情况。

    命中条件: 归一化后文本含 canonical 或任一 alias 的归一化子串。
    """
    norm_text = normalize(text)
    results = []
    for a in anchors_list:
        anchor_id = a["id"]
        anchor_type = a["type"]
        canonical = a["canonical"]
        aliases = a.get("aliases", [])
        cross_chapter = a.get("cross_chapter_of")

        norm_canonical = normalize(canonical)
        hit = False
        hit_by = None

        if norm_canonical in norm_text:
            hit = True
            hit_by = canonical
        else:
            for alias in aliases:
                if normalize(alias) in norm_text:
                    hit = True
                    hit_by = alias
                    break

        results.append({
            "id": anchor_id,
            "type": anchor_type,
            "canonical": canonical,
            "hit": hit,
            "hit_by": hit_by,
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
    """按类型汇总命中统计。"""
    total = len(atomic_results)
    hits = sum(1 for r in atomic_results if r["hit"])

    # 按类型分组
    type_stats: dict[str, dict[str, int]] = {}
    for r in atomic_results:
        t = r["type"]
        if t not in type_stats:
            type_stats[t] = {"total": 0, "hit": 0}
        type_stats[t]["total"] += 1
        if r["hit"]:
            type_stats[t]["hit"] += 1

    # 跨章锚子集(T3 等)
    cross_chapter = [r for r in atomic_results if r.get("cross_chapter_of")]
    cross_total = len(cross_chapter)
    cross_hits = sum(1 for r in cross_chapter if r["hit"])

    stats = {
        "chapter": chapter_id,
        "atomic": {
            "total": total,
            "hit": hits,
            "miss": total - hits,
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
            "miss": s["total"] - s["hit"],
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
    anchors_data = load_anchors(yaml_path)
    text = load_text(text_path)

    if chapter_id is None:
        chapter_id = Path(text_path).stem.split("_")[0].upper()

    chapter_data = anchors_data.get(chapter_id, {})
    atomic_list = chapter_data.get("atomic", [])
    composite_list = chapter_data.get("composite", [])

    atomic_results = check_atomic(atomic_list, text)
    composite_results = check_composite(composite_list, atomic_results) if composite_list else []
    stats = compute_stats(chapter_id, atomic_results, composite_results)

    return {
        "chapter": chapter_id,
        "source_file": str(text_path),
        "atomic_results": atomic_results,
        "composite_results": composite_results,
        "stats": stats,
    }


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------
def generate_json_report(results: list[dict], output_path: str | Path) -> None:
    """生成 JSON 格式报告。"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def generate_md_report(results: list[dict], output_path: str | Path) -> None:
    """生成 Markdown 格式报告。"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Anchor Check Report\n"]

    for report in results:
        ch = report["chapter"]
        stats = report["stats"]
        atomic = report["atomic_results"]
        composite = report["composite_results"]

        lines.append(f"## {ch}\n")
        lines.append(f"- 源文件: `{report['source_file']}`\n")

        # 总体
        a = stats["atomic"]
        lines.append(f"### Atomic 概览\n")
        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 总数 | {a['total']} |")
        lines.append(f"| 命中 | {a['hit']} |")
        lines.append(f"| 未命中 | {a['miss']} |")
        pct = f"{a['ratio'] * 100:.1f}%"
        lines.append(f"| 命中率 | {pct} |")
        lines.append("")

        # 按类型
        if stats.get("by_type"):
            lines.append("### 按类型统计\n")
            lines.append("| 类型 | 总数 | 命中 | 未命中 | 命中率 |")
            lines.append("|------|------|------|--------|--------|")
            for t, s in stats["by_type"].items():
                r = f"{s['ratio'] * 100:.1f}%"
                lines.append(f"| {t} | {s['total']} | {s['hit']} | {s['miss']} | {r} |")
            lines.append("")

        # 跨章锚
        cc = stats.get("cross_chapter", {})
        if cc.get("total", 0) > 0:
            lines.append("### 跨章锚(cross_chapter_of)\n")
            r = f"{cc['ratio'] * 100:.1f}%" if cc["ratio"] is not None else "N/A"
            lines.append(f"- 总数: {cc['total']}, 命中: {cc['hit']}, 命中率: {r}\n")

        # 逐锚命中表
        lines.append("### 逐锚命中表\n")
        lines.append("| ID | 类型 | canonical | 命中 | 命中方式 | 跨章 |")
        lines.append("|----|------|-----------|------|----------|------|")
        for a in atomic:
            cross = a.get("cross_chapter_of") or ""
            hit_str = "✓" if a["hit"] else "✗"
            hit_by = a.get("hit_by") or ""
            lines.append(
                f"| {a['id']} | {a['type']} | {a['canonical']} "
                f"| {hit_str} | {hit_by} | {cross} |"
            )
        lines.append("")

        # Composite
        if composite:
            lines.append("### Composite 结果\n")
            lines.append("| ID | 名称 | 全命中 | 成员状态 |")
            lines.append("|----|------|--------|----------|")
            for c in composite:
                all_hit_str = "✓" if c["all_hit"] else "✗"
                members_str = ", ".join(
                    f"{m['id']}({'✓' if m['hit'] else '✗'})" for m in c["members"]
                )
                lines.append(f"| {c['id']} | {c['name']} | {all_hit_str} | {members_str} |")
            lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------
def main() -> None:
    """命令行入口: python -m tools.anchor_checker <yaml> <text1> [text2 ...] [--chapter-id ID] [--output-dir DIR]"""
    import argparse

    parser = argparse.ArgumentParser(description="Anchor checker")
    parser.add_argument("yaml", help="anchors.yaml 路径")
    parser.add_argument("texts", nargs="+", help="待检测文本文件路径")
    parser.add_argument("--chapter-ids", nargs="*", help="章节 ID 列表, 与 texts 一一对应")
    parser.add_argument("--output-dir", default=".", help="输出目录")
    args = parser.parse_args()

    results = []
    for i, text_path in enumerate(args.texts):
        ch_id = args.chapter_ids[i] if args.chapter_ids and i < len(args.chapter_ids) else None
        report = run_check(args.yaml, text_path, chapter_id=ch_id)
        results.append(report)

    out_dir = Path(args.output_dir)
    generate_json_report(results, out_dir / "anchor_report.json")
    generate_md_report(results, out_dir / "anchor_report.md")

    # 打印摘要
    for r in results:
        ch = r["chapter"]
        a = r["stats"]["atomic"]
        pct = f"{a['ratio'] * 100:.1f}%"
        print(f"{ch}: {a['hit']}/{a['total']} = {pct}")


if __name__ == "__main__":
    main()
