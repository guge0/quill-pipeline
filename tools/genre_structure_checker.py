"""P6-2 genre structure checker.

扫描 planning.md 文件,统计 genre 结构 marker 的命中情况。
学 anchor_checker 模式:归一化 + canonical/alias 子串匹配 + JSON/MD 报告。

CLI:
    python -m tools.genre_structure_checker <markers.yaml> <planning.md...>
        [--labels L1 L2 ...] [--output-dir DIR]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

# 全角→半角偏移
_FULLWIDTH_OFFSET = 0xFEE0
_PUNCT_MAP = {
    "(": "(", ")": ")", ",": ",", ".": ".",
    ":": ":", ";": ";", "!": "!", "?": "?",
    '"': '"', '"': '"', "'": "'", "'": "'",
}


def normalize(text: str) -> str:
    """全角→半角 + 连续空白压缩为单空格 + strip。

    确定性优先:不做语义转换(如三→3)。
    """
    if not text:
        return ""
    out = []
    for ch in text:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - _FULLWIDTH_OFFSET))
        elif ch in _PUNCT_MAP:
            out.append(_PUNCT_MAP[ch])
        else:
            out.append(ch)
    s = "".join(out)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def load_markers(path) -> dict:
    """加载 markers.yaml。返回 {category: [{id, canonical, aliases}, ...]}。"""
    with Path(path).open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data


def scan_text(text: str, markers: dict) -> set:
    """扫描文本,返回命中的 marker id 集合。

    命中规则:归一化后的文本含 canonical 或任一 alias 的归一化子串。
    """
    norm_text = normalize(text)
    hits = set()
    for category, items in markers.items():
        for item in items:
            candidates = [item["canonical"]] + list(item.get("aliases", []))
            for cand in candidates:
                norm_cand = normalize(cand)
                if norm_cand and norm_cand in norm_text:
                    hits.add(item["id"])
                    break
    return hits


def run_check(markers_path, files, labels, output_dir) -> dict:
    """跑 checker,输出 out.json + out.md。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    markers = load_markers(markers_path)

    if len(labels) != len(files):
        labels = [Path(f).stem for f in files]

    results = []
    for file, label in zip(files, labels):
        text = Path(file).read_text(encoding="utf-8")
        hits = scan_text(text, markers)
        per_category = {}
        for cat, items in markers.items():
            cat_ids = {it["id"] for it in items}
            per_category[cat] = sorted(hits & cat_ids)
        results.append({
            "label": label,
            "file": str(file),
            "hits": sorted(hits),
            "total_hits": len(hits),
            "per_category": per_category,
        })

    report = {
        "markers_file": str(markers_path),
        "total_markers": sum(len(v) for v in markers.values()),
        "results": results,
    }

    (output_dir / "out.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_lines = ["# P6-2 Genre Structure Checker 报告", ""]
    md_lines.append(f"- markers: `{markers_path}`")
    md_lines.append(f"- 总 marker 数: {report['total_markers']}")
    md_lines.append("")
    md_lines.append("## 命中汇总")
    md_lines.append("")
    md_lines.append("| Label | 总命中 | pacing | goals | opening |")
    md_lines.append("|---|---:|---:|---:|---:|")
    for r in results:
        md_lines.append(
            f"| {r['label']} | {r['total_hits']} | "
            f"{len(r['per_category'].get('pacing', []))} | "
            f"{len(r['per_category'].get('goals', []))} | "
            f"{len(r['per_category'].get('opening', []))} |"
        )
    md_lines.append("")
    md_lines.append("## 详细命中")
    for r in results:
        md_lines.append(f"\n### {r['label']} ({r['total_hits']} hits)")
        for cat in ["pacing", "goals", "opening"]:
            md_lines.append(f"- **{cat}**: {', '.join(r['per_category'].get(cat, [])) or '(无)'}")

    (output_dir / "out.md").write_text("\n".join(md_lines), encoding="utf-8")

    return report


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("markers", type=Path)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--labels", nargs="*", default=None)
    ap.add_argument("--output-dir", type=Path, default=Path("."))
    args = ap.parse_args(argv)
    labels = args.labels if args.labels else [f.stem for f in args.files]
    run_check(args.markers, args.files, labels, args.output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
