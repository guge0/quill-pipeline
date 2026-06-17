"""P6-2 题材模板渲染器:把 config/template_genre.yaml 渲染为 genre_block 文本。

genre_block 是 Layer 2 信息上下文(参考性,why-based),不是 NEVER/ALWAYS 硬约束。
注入到 build_planning_prompt 的 "## 输出格式" 之前。

稳定性:纯函数,同 (yaml_path, chapter_num) → 同输出。
"""
from pathlib import Path

import yaml


HEADER = """## 题材结构骨架(参考,非硬约束)

这是创作参考,不是硬规则。字数为典型值,真高潮密集/破格都算合理例外。
由模型自己判断每条原则在本章是否适用、如何落实。
"""

FOOTER_TEMPLATE = """
### 本章应用提示(第 {chapter} 章 / 累计约 {cumulative} 字)
对照上面的骨架判断:
- 本章在哪个"局"内?是否局尾(可考虑高潮)?
- 本章对应哪个目标层?需不需要指方向?
- 累计字数临近哪个锚点(1万/3万/6万)?

不要硬塞。过渡章/铺垫章可跳过对应条目。真高潮密集或破格冲击都算合理例外。
"""


def _format_high_points(items):
    lines = ["**高潮字数锚点(典型值)**"]
    for it in items:
        why = it.get("why", "")
        lines.append(f"- {it['typical_at_words']}字 = {it['tier']}(为什么:{why})")
    return "\n".join(lines)


def _format_ju(ju):
    why = ju.get("why", "").strip().replace("\n", " ")
    structure = "→".join(ju.get("structure", []))
    return (
        f"**\"局\"颗粒度**:{ju['chapters_per_ju']}章一个完整\"局\""
        f"({structure}),{ju.get('climax_position', '局尾')}掐高潮。\n为什么:{why}"
    )


def _format_hook(hook):
    why = hook.get("why", "")
    return (
        f"**章尾钩子**:{hook['chapter_length_words']}字一章,"
        f"约 {hook['hook_starts_at_words']} 字处开始铺,留 500 字落实。\n为什么:{why}"
    )


def _format_goals(goals):
    lines = ["### 目标体系(三层 = 节奏的引擎)"]
    for layer in goals["layers"]:
        lines.append(f"- {layer['tier']}({layer['typical_set_by_words']}字内立) —— 为什么:{layer['why']}")
    if "ladder_principle" in goals:
        why = goals["ladder_principle"]["why"].strip().replace("\n", " ")
        lines.append(f"- 为什么这样设计:{why}")
    for p in goals.get("principles", []):
        lines.append(f"- 原则:{p['rule']} —— 为什么:{p['why']}")
    return "\n".join(lines)


def _format_opening(opening):
    lines = ["### 开篇结构(前3万字定生死)"]
    ft = opening["feng_tou"]
    lines.append(f"- 凤头 —— 为什么:{ft['why']}")
    pf = opening["protagonist_focus"]
    lines.append(f"- 主角聚光 —— 为什么:{pf['why']}")
    df = opening["double_foreshadow"]
    lines.append(
        f"- 双伏笔:埋一长一短;短线 {df['short_line']['reveal_within_words']} 字内揭"
        f"(读者回头翻找 = 成功信号);长线撑长期目标"
    )
    sd = opening["slim_down"]
    lines.append(f"- 瘦身 —— 为什么:前 {sd['after_words']} 字完成后反写 {sd['outline_length_words']} 字细纲,删冗余")
    return "\n".join(lines)


def render_genre_block(yaml_path, chapter_num: int) -> str:
    """渲染 genre_block。稳定性:纯函数,同输入同输出。"""
    yaml_path = Path(yaml_path)
    with yaml_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    pacing = data["pacing"]
    goals = data["goals"]
    opening = data["opening"]

    cumulative = max(0, (chapter_num - 1) * pacing["chapter_end_hook"]["chapter_length_words"])

    parts = [HEADER, "### 节奏曲线"]
    parts.append(_format_high_points(pacing["high_points"]))
    parts.append("")
    parts.append(_format_ju(pacing["ju"]))
    parts.append("")
    parts.append(_format_hook(pacing["chapter_end_hook"]))
    parts.append("")
    parts.append(_format_goals(goals))
    parts.append("")
    parts.append(_format_opening(opening))
    parts.append(FOOTER_TEMPLATE.format(chapter=chapter_num, cumulative=cumulative))

    return "\n".join(parts)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("yaml", type=Path)
    ap.add_argument("--chapter", type=int, default=1)
    args = ap.parse_args()
    print(render_genre_block(args.yaml, args.chapter))
