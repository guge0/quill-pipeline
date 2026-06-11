"""Chapter writer prompt v4 - 三层注入架构

替代 v3_opening.py 的罗列式 prompt。三层目的清晰:
- Layer 1: 硬规则(违反必拦)
- Layer 2: 上下文信息(只读不约束)
- Layer 3: 写作约束(数值化,可量化)

设计原则: why > must (来自 Anthropic Skills 设计指南)
"""
from __future__ import annotations


# system prompt 模板
WRITER_SYSTEM_V4 = """你是中文网文作者,本作品定位见 Layer 2 中的 worldbook.narrative_anchors。
你的工作:按照 user prompt 中的 Layer 2 信息和 Layer 1+3 约束,生成本章正文。
只输出正文,不输出元信息(章节标题、字数统计、风格说明)。"""

# Layer 1/2/3 标记常量(便于 Auditor 识别)
LAYER1_BEGIN = "【Layer 1 硬规则 - 违反这些 = 废稿】"
LAYER1_END = "【Layer 1 结束】"
LAYER2_BEGIN = "【Layer 2 信息上下文 - 写作时参考】"
LAYER2_END = "【Layer 2 结束】"
LAYER3_BEGIN = "【Layer 3 写作约束 - 写完前自检】"
LAYER3_END = "【Layer 3 结束】"


def build_layer1_hard_rules(chapter_num: int, worldbook: dict | None) -> str:
    """Layer 1 硬规则,200 字内。

    包含:
    - 主角姓名(从 worldbook.facts 提取)
    - 已死亡角色禁令
    - worldbook 中标记为 facts 的核心设定
    - 章节号
    """
    rules = []
    rules.append(f"1. 章节号: 第 {chapter_num} 章")

    # 从 worldbook 提取主角姓名和核心设定
    protagonist_name = None
    if worldbook and isinstance(worldbook, dict):
        facts = worldbook.get("facts", [])
        for fact in facts:
            if isinstance(fact, str):
                # 查找主角姓名
                if "主角姓名" in fact or "主角" in fact:
                    protagonist_name = fact
                    break
        # 添加核心设定(非主角姓名的 facts)
        for fact in facts:
            if isinstance(fact, str) and fact != protagonist_name:
                idx = len(rules) + 1
                rules.append(f"{idx}. {fact}")

    if protagonist_name:
        # 插入到第 2 条
        rules.insert(1, f"2. 主角姓名: {protagonist_name}")
        # 重新编号
        for i in range(len(rules)):
            rule_text = rules[i]
            # 去掉旧编号
            if i + 1 > 1 and rule_text.startswith(f"{i + 1}."):
                rule_text = rule_text[len(str(i + 1)) + 2:]
            elif i + 1 > 1 and rule_text[0].isdigit() and "." in rule_text[:3]:
                rule_text = rule_text[rule_text.index(".") + 2:]
            if i == 0:
                rules[i] = f"1. 章节号: 第 {chapter_num} 章"
            elif i == 1:
                rules[i] = f"2. 主角姓名: {protagonist_name}"
            else:
                rules[i] = f"{i + 1}. {rule_text}"

    # 添加通用硬规则
    idx = len(rules) + 1
    rules.append(f"{idx}. 已死亡角色不得有任何活动、台词、动作")

    lines = [LAYER1_BEGIN] + rules + [LAYER1_END]
    return "\n".join(lines)


def build_layer2_context(
    worldbook_prompt: str,
    characters: list[dict],
    truth_files_block: str,
    prev_tail: str,
    context_block: str,
    outline: str,
    planning: str,
) -> str:
    """Layer 2 信息上下文,只读不约束。"""
    parts = [LAYER2_BEGIN,
             "你拿到的不是事件清单,是创作者的本章规划(创作者细纲)。",
             "你的工作是落地这份规划:把戏核写到位,按笔墨分配把关键处展开、过渡处克制。",
             "sub-md(剧情简介)由 Architect 已转化为本细纲,你不需要再读 sub-md。"]

    # 世界观
    if worldbook_prompt:
        parts.append("# 世界观")
        parts.append(worldbook_prompt)

    # 在场角色
    if characters:
        char_block = _build_character_block(characters)
        if char_block:
            parts.append("# 在场角色")
            parts.append(char_block)

        # 称谓使用指引
        naming_guide = _build_naming_guide(characters)
        if naming_guide:
            parts.append(naming_guide)

    # 故事现状
    if truth_files_block:
        parts.append("# 故事现状")
        parts.append(truth_files_block)

    # 上一章末段(衔接锚点)
    if prev_tail:
        parts.append("# 上一章末段(衔接锚点)")
        parts.append(prev_tail)

    # 历史章节
    if context_block:
        parts.append("# 历史章节")
        parts.append(context_block)

    # 创作者细纲
    if outline:
        parts.append("# 创作者细纲")
        parts.append(outline)

    # 本章规划
    if planning:
        parts.append("# 本章规划")
        parts.append(planning)

    parts.append(LAYER2_END)
    return "\n\n".join(parts)


def _build_character_block(characters: list[dict]) -> str:
    """构建角色注入块，按 tier 分层排列。

    主角顶部硬注入，NPC 不注入。
    不同 tier 用不同详细度：
    - full: protagonist/antagonist/major_supporting（含全部字段）
    - medium: supporting（不含 voice_examples）
    - skip: npc（不注入 prompt）
    """
    TIER_ORDER = ["protagonist", "antagonist", "major_supporting", "supporting"]
    TIER_LABELS = {
        "protagonist": "主角",
        "antagonist": "反派",
        "major_supporting": "重要配角",
        "supporting": "配角",
    }

    # 按 tier 分组
    tier_groups: dict[str, list[dict]] = {t: [] for t in TIER_ORDER}
    for char in characters:
        if not isinstance(char, dict):
            continue
        name = char.get("name", "")
        if not name:
            continue
        tier = char.get("tier", "supporting")
        if tier == "npc":
            continue  # NPC 不进 prompt
        if tier not in tier_groups:
            tier = "supporting"
        tier_groups[tier].append(char)

    # 按 tier 顺序拼接
    sections: list[str] = []
    for tier in TIER_ORDER:
        group = tier_groups[tier]
        if not group:
            continue

        detail = "full" if tier in ("protagonist", "antagonist", "major_supporting") else "medium"
        label = TIER_LABELS.get(tier, tier)
        section_lines = [f"### {label}"]

        for char in group:
            char_block = _format_single_char(char, detail)
            if char_block:
                section_lines.append(char_block)

        sections.append("\n\n".join(section_lines))

    return "\n\n".join(sections)


def _format_single_char(char: dict, detail: str = "full") -> str:
    """格式化单个角色卡。

    Args:
        char: 角色数据。
        detail: 'full' 含全部字段, 'medium' 不含 voice_examples。
    """
    name = char.get("name", "")
    lines = [f"## {name}"]
    if char.get("background"):
        lines.append(f"背景: {char['background']}")
    if detail == "full" and char.get("voice_examples"):
        lines.append(f"语声样本: {char['voice_examples']}")
    if char.get("personality"):
        lines.append(f"性格: {char['personality']}")
    return "\n".join(lines)


def _build_naming_guide(characters: list[dict]) -> str:
    """生成称谓使用指引,放进 Layer 2 末尾。"""
    lines = ["# 称谓使用指引(每个角色不同人嘴里有不同叫法)"]
    has_content = False
    for char in characters:
        if not isinstance(char, dict):
            continue
        if "aliases" not in char:
            continue
        has_content = True
        name = char["name"]
        aliases = char["aliases"]
        lines.append(f"\n## {name}")
        lines.append(f"- 叙述者默认: {aliases.get('narrator_default', name)}")
        lines.append(f"- 自称: {aliases.get('self_referent', '我')}")
        if "called_by" in aliases:
            lines.append("- 别人怎么叫他/她:")
            for caller, call in aliases["called_by"].items():
                lines.append(f"  - {caller} → {call}")
        if char.get("forbidden_in_narrative"):
            forbidden_list = ", ".join(f'"{x}"' for x in char["forbidden_in_narrative"])
            lines.append(f"- **正文绝对禁用**: {forbidden_list}(这些是工程层代号)")
    return "\n".join(lines) if has_content else ""


def build_layer3_constraints(target_words: int = 5000) -> str:
    """Layer 3 写作约束,数值化。"""
    return f"""{LAYER3_BEGIN}

# 字数
- 本章 ≥ {target_words} 中文字符,≤ {target_words + 1500} 字符

# 标点密度(防 AI 文风)
- 破折号(——)≤ 3 次/千字。**仅限对话戛然停顿(如"这——"被打断)使用,
  禁止用于补充说明、句中转折、动作叙述。补充说明用句号 + 短句替代**
- 反例:"是物理上的——空气变得滞重"
- 正例:"是物理上的。空气变得滞重"
- 反例:"卧槽——" 角色C打了个激灵 (补充说明)
- 正例:"卧槽!" 角色C打了个激灵
- 省略号(……)≤ 2 次/千字
- 感叹号 ≤ 8 次/千字

# 句式偏好(避免重复)
- "不是X而是Y"格式 ≤ 2 次/章
- "仿佛/像是/犹如"比喻 ≤ 3 次/千字
- 不使用"瞳孔一缩、怒极反笑、嘴角微微上扬、心中暗道"等套路化表情
  (改用具体身体反应:后颈汗毛竖起、牙关咬紧、指节发白)

# 视角守恒(防穿帮)
- 秘境源世界角色(如曹操、关羽)说话只能基于该角色历史时点的认知
- 禁用元词汇:后人、后世、史书、历史(指评价义)、未来、先人、流传、记载、典籍、传记
- 反例: "那都是后人编的"
- 正例: "那都是说书人瞎编"

# 动作描写(防游戏化)
- 正文中不出现 X% / 0.X 秒等精确数字描述能力或速度
- 数字描述只能在"白色空间界面"段落使用
- 反例: "命甲在 0.3 秒内披上"
- 正例: "他几乎看不见命甲披上的过程,只感觉胸口一沉"

# 对话密度
- 整章对话占比 ≤ 60%
- 非对话段落必须有动作、环境、心理、感官描写
- 温情/政策/铺垫章尤其要警惕"全章坐着说话"

# 章末完整性
- 章末段落收束后,不得续写场景重启段(回到更早时间点、重新讨论已发生事件)
- 反例:章末写了"赤壁之战开始了",后续还有段落讨论怎么躲明天的火攻

# 笔墨分配执行
按细纲的笔墨分配执行——
关键处展开,文笔细一些、节奏慢一些;
过渡处节制,简练带过,不要把所有段落写得一样仔细。
细纲指明"特写""慢节奏""留白"等技法,在对应段落落地这些手法。

# 章末钩子(网文翻页率核心)
- 章末段落必须含有以下三项之一:
  1. 具体数字(如"存活人数 42/46""任务剩余 21:43:17""第 3 个伤口")
  2. 具体威胁信号(脚步声、林子里有动静、远方刀光)
  3. 具体身份揭示(某人是某身份、某物是某物的暗示)
- 禁止纯情绪/天气/景物作为唯一章末收尾
- 反例:"天快亮了。东南风还在刮。" (纯情绪)
- 正例:"天快亮了。东南风还在刮。系统提示又跳出一行字:存活人数 42。"

# 开篇要求
- 第一句必须是动作、对话或冲突
- 景物/环境描写最早从第 4 段开始

# 锚点核对
成稿之前,对照细纲中的"硬信息锚点块"逐条核对:
1. 读取锚点块中列出的每一条硬事实(时间/地点/人物/数字/约定/设定)
2. 检查正文是否已包含该条事实。包含的标准:正文中出现了该事实的关键信息(具体数字、具体名称、具体地点)
3. 任何缺失项必须自然融入正文补齐——不得以列举式堆砌,必须融入叙事(对话、叙述、角色视角均可)
4. 锚点的具体表述以锚点块原文为准,不得改写数字/时间/称谓
5. 核对完毕后输出正文,不输出核对过程

{LAYER3_END}"""


def build_writer_prompt_v4(
    chapter_num: int,
    worldbook: dict | None,
    worldbook_prompt: str,
    characters: list[dict],
    truth_files_block: str,
    prev_tail: str,
    context_block: str,
    outline: str,
    planning: str,
    target_words: int = 5000,
    present_characters: list[str] | None = None,
) -> tuple[str, str]:
    """组装完整的 system + user prompt。

    Returns: (system_prompt, user_prompt)

    system_prompt: 简短角色定位
    user_prompt: Layer 1 + Layer 2 + Layer 3 + 收尾指令
    """
    system_prompt = WRITER_SYSTEM_V4

    layer1 = build_layer1_hard_rules(chapter_num, worldbook)
    layer2 = build_layer2_context(
        worldbook_prompt=worldbook_prompt,
        characters=characters,
        truth_files_block=truth_files_block,
        prev_tail=prev_tail,
        context_block=context_block,
        outline=outline,
        planning=planning,
    )
    layer3 = build_layer3_constraints(target_words)

    user_prompt = (
        f"{layer1}\n\n"
        f"{layer2}\n\n"
        f"{layer3}\n\n"
        f"现在开始写第 {chapter_num} 章正文。只输出正文,不要输出元信息。"
    )

    return system_prompt, user_prompt
