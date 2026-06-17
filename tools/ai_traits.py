"""AI 痕迹机械度量 CLI — `python -m tools.ai_traits <text...>`。

对每章正文调用 biyu.ai_traits.measure_all,输出 JSON + MD 报告。
只输出数字 + 提示,不否决、不判人味(§3.3)。
"""
from __future__ import annotations

import json
from pathlib import Path

from biyu.ai_traits import measure_all


def generate_json_report(results: list[dict], output_path: str | Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def generate_md_report(results: list[dict], output_path: str | Path) -> None:
    """MD 报告:每章一篮子度量 + proxy 免责声明。"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# AI 痕迹机械度量报告\n"]
    lines.append("> ⚠ 全部度量仅供参考。感叹号/单行段有刻板例外(真高潮不算错)。"
                 "代偿项均带 **proxy** 标记 —— 是趋势信号,**不否决、不判人味**。阈值由 TL 定。\n")
    for r in results:
        ch = r["chapter"]
        m = r["metrics"]
        lines.append(f"## {ch}\n")
        if "source_file" in r:
            lines.append(f"- 源文件: `{r['source_file']}`")
        lines.append(f"- CJK 字数: {m['char_count_cjk']}  退化: {m['degenerate']}")
        pl = m["paragraph_lengths"]
        lines.append(f"- 段落数: {pl['count']} | 均值 {pl['mean']:.1f} | 中位 {pl['median']:.1f} "
                     f"| 最长 {pl['max']} | 超长段占比 {pl['long_para_ratio']*100:.1f}%")
        lines.append(f"- 感叹号 /千字: {m['exclaim_density_per_1k']:.2f}")
        lines.append(f"- 破折号 /千字: {m['dash_density_per_1k']:.2f}")
        lines.append(f"- 无标点超长句占比: {m['long_unpunct_sentence_ratio']*100:.1f}%")
        mod = m["modifier_proxy"]
        lines.append(f"- 描饰词 proxy: {mod['count']} 次 / {mod['density_per_1k']:.2f}/千字 (proxy)")
        par = m["parallelism_proxy"]
        lines.append(f"- 对仗 proxy: 整齐串句占比 {par['uniform_run_ratio']*100:.1f}% | "
                     f"同字开头连续 {par['same_start_count']} (proxy)")
        fc = m["four_char_proxy"]
        lines.append(f"- 四字格 proxy: 成语命中 {fc['idiom_hits']} | 原始4CJK {fc['raw_four_cjk_count']} "
                     f"| {fc['idiom_density_per_1k']:.2f}/千字 (proxy)")
        nr = m["number_rhythm"]
        lines.append(f"- 数字呼应: implemented={nr['implemented']} ({nr['note']})")
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """CLI: python -m tools.ai_traits <text1> [text2 ...] [--chapter-ids ID ...] [--output-dir DIR]"""
    import argparse
    parser = argparse.ArgumentParser(description="AI 痕迹机械度量(确定性,¥0)")
    parser.add_argument("texts", nargs="+", help="待测文本文件路径")
    parser.add_argument("--chapter-ids", nargs="*", help="章节 ID 列表,与 texts 一一对应")
    parser.add_argument("--output-dir", default=".", help="输出目录")
    args = parser.parse_args()

    results = []
    for i, text_path in enumerate(args.texts):
        ch = args.chapter_ids[i] if args.chapter_ids and i < len(args.chapter_ids) \
            else Path(text_path).stem
        text = Path(text_path).read_text(encoding="utf-8")
        results.append({"chapter": ch, "source_file": str(text_path),
                        "metrics": measure_all(text)})

    out_dir = Path(args.output_dir)
    generate_json_report(results, out_dir / "ai_traits_report.json")
    generate_md_report(results, out_dir / "ai_traits_report.md")
    for r in results:
        m = r["metrics"]
        print(f"{r['chapter']}: CJK {m['char_count_cjk']} | 感叹 {m['exclaim_density_per_1k']:.2f}/千 "
              f"| 破折 {m['dash_density_per_1k']:.2f}/千 | 超长句 {m['long_unpunct_sentence_ratio']*100:.1f}%")


if __name__ == "__main__":
    main()
