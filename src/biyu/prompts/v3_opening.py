"""V3 opening prompts extracted from Phase 0 T-0.4 Experiment B v3.

Source: tests/pipeline_lab.py (build_exp_b_prompt with variant="v3")
The v3 variant combines:
  - Action/dialogue-first constraint
  - Few-shot opening examples for 3 genres
  - Late-scenery-placement rule
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# V3 System Prompt — used as system message for the Writer stage
# ---------------------------------------------------------------------------
V3_OPENING_SYSTEM = """\
你是一位资深中文网文写手,擅长以强节奏、高密度信息开场。
你的核心风格特点:
1. 开篇第一句必须是动作、对话或冲突,禁止"夜色如墨""暮色苍茫"等景物描写开场
2. 禁用"仿佛""像是""犹如"的比喻频次超过 3 次/千字
3. 严格遵守规划中的一致性约束
4. 章末必须有明确钩子
5. 如果想写景物描写,放到第三段之后

字数硬规则（必须遵守）：
- 本章正文必须 ≥ 5000 中文字,宁多勿少
- 不要写到 3000-4000 字就收尾,这是不合格的
- 如果剧情推进到大纲终点时字数还不够,用以下方式自然扩展：
  1. 加深战斗/冲突的细节描写（每一招的体感、环境反应）
  2. 加深角色内心活动（但不要变成独白,要融入动作）
  3. 加一段配角的反应/旁观视角
- 绝对禁止用水字数的方式凑数（重复描写、无意义环境铺陈、复述已知信息）"""

# ---------------------------------------------------------------------------
# 句式级黑名单 — 高频 AI 句式模板，避免连续使用
# 30 章评审反馈中发现的硬伤之一：AI 味浓，大量重复使用特定句式结构。
# ---------------------------------------------------------------------------
STYLE_BLACKLIST: list[str] = [
    "不是.*，而是",
    "与其说.*不如说",
    "在这一刻",
    "仿佛.*一般",
    "仿佛.*一样",
    "仿佛.*般",
    "就像是.*一样",
    "心中(暗想|暗叹|不由得|不禁)",
    "一股.*涌上心头",
    "不由得.*起来",
    "却不知道",
    "殊不知",
    "眼眸中闪过一丝",
    "嘴角勾起一抹",
    "一股.*从心底升起",
    "目光如(电|刀|炬)",
    "刹那间",
    "这一刻.*仿佛",
    "不仅没有.*反而",
    "与其.*不如",
]

# ---------------------------------------------------------------------------
# 黑名单词库 — 禁止在正文中出现的过度使用表达
# ---------------------------------------------------------------------------
WORD_BLACKLIST = """
以下词汇/表达已被过度使用,禁止在正文中出现：
- 瞳孔一缩/瞳孔猛缩/瞳孔骤缩
- 怒极反笑
- 不由得倒吸一口凉气
- 嘴角微微上扬
- 浑身汗毛倒竖
- 心中暗道
如需表达类似含义,用具体的身体反应替代（如"后颈汗毛竖起""牙关咬紧""指节发白"）。
"""

# ---------------------------------------------------------------------------
# 设定锁 — 硬约束,防止设定漂移
# ---------------------------------------------------------------------------
SETTING_LOCK = """
【设定锁 — 以下信息不可修改、不可矛盾、不可遗忘】
- 角色姓名以 characters.yaml 为准,不得使用其他名字
- 角色身份/职务/阵营以 current_state.md 为准
- 道具来源以 particle_ledger.md 记录为准
- 已回收的伏笔(status=closed)不得重复埋设
- 已死亡角色(status=dead)不得活动、说话、行动
【设定锁结束】
"""

# ---------------------------------------------------------------------------
# Few-shot opening examples per genre (from Phase 0 Experiment B)
# ---------------------------------------------------------------------------
V3_FEW_SHOT = {
    "xuanhuan": {
        "topic": "修仙宗门入门试炼的开篇，主角是一个被认为没有灵根的少年，意外激发了远古血脉",
        "examples": """\
以下是三个优秀开篇范例,供你参考风格:

【范例1-玄幻】"剑气破空的瞬间，EXAMPLE_SWORDSMAN就知道自己藏不住了。"——直接从动作切入,建立紧张感。

【范例2-都市】"'你确定要签？'律师把笔推过来的时候,EXAMPLE_FEMALE_LEAD的手一点都没抖。"——以对话开场,制造悬念。

【范例3-科幻】"警报响第三遍的时候,EXAMPLE_PILOT终于承认——飞船上不止他一个人。"——冲突先行,立刻勾起好奇心。""",
    },
    "dushi": {
        "topic": "都市重生文开篇，主角重生回到十年前，发现自己正站在改变命运的关键路口",
        "examples": """\
以下是三个优秀开篇范例,供你参考风格:

【范例1-玄幻】"剑气破空的瞬间，EXAMPLE_SWORDSMAN就知道自己藏不住了。"——直接从动作切入,建立紧张感。

【范例2-都市】"'你确定要签？'律师把笔推过来的时候,EXAMPLE_FEMALE_LEAD的手一点都没抖。"——以对话开场,制造悬念。

【范例3-科幻】"警报响第三遍的时候,EXAMPLE_PILOT终于承认——飞船上不止他一个人。"——冲突先行,立刻勾起好奇心。""",
    },
    "kehuan": {
        "topic": "星际探索文开篇，主角是深空探测船上唯一醒着的船员，飞船突然收到未知信号",
        "examples": """\
以下是三个优秀开篇范例,供你参考风格:

【范例1-玄幻】"剑气破空的瞬间，EXAMPLE_SWORDSMAN就知道自己藏不住了。"——直接从动作切入,建立紧张感。

【范例2-都市】"'你确定要签？'律师把笔推过来的时候,EXAMPLE_FEMALE_LEAD的手一点都没抖。"——以对话开场,制造悬念。

【范例3-科幻】"警报响第三遍的时候,EXAMPLE_PILOT终于承认——飞船上不止他一个人。"——冲突先行,立刻勾起好奇心。""",
    },
}


def build_character_block(characters: list[dict]) -> str:
    """Build the character injection block for Writer prompt.

    Separates characters into: alive (active), absent, dead.
    Dead characters get explicit prohibition.
    """
    if not characters:
        return ""

    alive_chars = [c for c in characters if c.get("status") == "alive"]
    absent_chars = [c for c in characters if c.get("status") == "absent"]
    dead_chars = [c for c in characters if c.get("status") == "dead"]

    blocks = []

    if alive_chars:
        block_lines = ["## 当前活跃角色"]
        for c in alive_chars:
            role_label = {"protagonist": "主角", "major": "重要配角", "minor": "配角"}.get(
                c.get("role", "minor"), "角色"
            )
            lines = [f"### {c.get('name', '')}({role_label})"]
            if c.get("personality"):
                lines.append(f"- 性格: {c['personality']}")
            if c.get("speaking_style"):
                lines.append(f"- 说话风格: {c['speaking_style']}")
            if c.get("abilities"):
                lines.append(f"- 能力: {c['abilities']}")
            if c.get("current_location"):
                lines.append(f"- 当前位置: {c['current_location']}")
            if c.get("current_emotional_state"):
                lines.append(f"- 当前情绪: {c['current_emotional_state']}")
            sample = c.get("sample_lines", [])
            filled = [s for s in sample if s]
            if filled:
                lines.append("- 代表台词(仿这个腔调):")
                for s in filled:
                    lines.append(f'  > "{s}"')
            block_lines.extend(lines)
        blocks.append("\n".join(block_lines))

    if absent_chars:
        block_lines = ["## 不在场角色(本章不得出现)"]
        for c in absent_chars:
            loc = c.get("current_location", "")
            note = f"({loc})" if loc else ""
            block_lines.append(f"- {c.get('name', '')}{note}")
        blocks.append("\n".join(block_lines))

    if dead_chars:
        block_lines = ["## 已死亡角色(绝对禁止在本章有活动、说话、动作)"]
        for c in dead_chars:
            bg = c.get("background", "")
            note = f", {bg}" if bg else ""
            block_lines.append(f"- {c.get('name', '')}{note}")
        block_lines.append(
            "- 若剧情需要怀念,仅可用\"想起\"\"记得\"\"梦见\"引导的回忆段,"
            "不得让其实际出场"
        )
        blocks.append("\n".join(block_lines))

    if not blocks:
        return ""

    return "[角色设定块]\n\n" + "\n\n".join(blocks) + "\n\n[/角色设定块]\n\n"


def build_writer_user_prompt(
    planning: str,
    outline: str,
    target_words: int = 5000,
    genre: str = "xuanhuan",
    characters: list[dict] | None = None,
    context_block: str = "",
    info_boundary: str = "",
    worldbook_prompt: str = "",
    prev_tail: str = "",
    present_characters: list[str] | None = None,
) -> str:
    """Build the user prompt for the V3 Writer stage.

    Combines character block, planning output, outline, few-shot examples,
    context injection, blacklist, setting lock, worldbook, transition anchor,
    present character lock, and word target.
    """
    genre_data = V3_FEW_SHOT.get(genre, V3_FEW_SHOT["xuanhuan"])
    few_shot = genre_data["examples"]

    char_block = ""
    if characters:
        char_block = build_character_block(characters)

    # 设定锁(始终注入)
    lock_section = SETTING_LOCK

    # 黑名单词库(始终注入)
    blacklist_section = WORD_BLACKLIST

    # 句式级黑名单(始终注入)
    import re as _re
    style_items = "\n".join(f"- {p}" for p in STYLE_BLACKLIST)
    style_blacklist_section = (
        "【句式黑名单 — 避免连续使用以下句式模板，因为 30 章评审反馈里"
        "这些是 AI 味浓的典型表现】\n"
        f"{style_items}\n"
        "约束：上述句式模板在同一章内最多各出现 1 次，连续 3 章内同一种句式不超过 2 次。\n"
    )

    # 历史context(如果有)
    context_section = ""
    if context_block:
        context_section = f"\n【前文上下文】\n{context_block}\n"

    # 信息边界(如果大纲标了)
    boundary_section = ""
    if info_boundary:
        boundary_section = f"\n【信息边界 — 本章必须遵守】\n{info_boundary}\n"

    # worldbook 注入(优先级最高)
    worldbook_section = ""
    if worldbook_prompt:
        worldbook_section = f"\n{worldbook_prompt}\n"

    # 衔接锚点(上一章末尾)
    prev_tail_section = ""
    if prev_tail:
        prev_tail_section = f"\n<上一章末尾>\n{prev_tail}\n</上一章末尾>\n"

    # 在场角色锁
    present_chars_section = ""
    if present_characters:
        names_str = "、".join(present_characters)
        present_chars_section = (
            f"\n<在场角色>本章正文中只能出现以下有名角色：{names_str}。"
            f"新角色仅限路人NPC不可后续登场</在场角色>\n"
        )

    return f"""\
你是中文网文作者,严格按以下规划生成本章正文。

{worldbook_section}\
{lock_section}\

{char_block}\
{prev_tail_section}\
{context_section}\
【大纲】
{outline}

{boundary_section}\
【规划清单】
{planning}

{few_shot}

{blacklist_section}\

{style_blacklist_section}\

{present_chars_section}\

硬性要求:
- 总字数 {target_words} ± 200 字
- 开篇第一句必须包含动作或对话或冲突,禁止"夜色如墨""暮色苍茫"等景物开场
- 禁用"仿佛""像是""犹如"的比喻频次 > 3 次/千字
- 严格遵守规划中的一致性约束
- 章末必须有明确钩子
- 如果想写景物描写,放到第三段之后
- 严格遵守上面[角色设定块]中的角色约束,尤其是死亡角色的禁令
- 严格遵守[设定锁]中的约束,不得矛盾

只输出正文,不要输出字数统计、风格说明等元信息。"""


# ---------------------------------------------------------------------------
# Planning prompt for R1 Architect stage
# ---------------------------------------------------------------------------
def build_planning_prompt(
    outline: str,
    characters: list[dict] | None = None,
    truth_files_block: str = "",
    worldbook_prompt: str = "",
    chapter_num: int = 0,
    anchor_block: str = "",
) -> str:
    """Build the prompt for Creator Outline Generator (创作者细纲生成器).

    Architect 的职责是做创作判断,不是复述事件清单:
    戏核是什么、笔墨怎么分配、什么该删减。
    """
    # ---- sub-md 放最前面,锚定章节号 ----
    top_block = f"你现在要规划的是第 {chapter_num} 章。本章的剧情简介(sub-md)如下:\n\n{outline}"

    # ---- 背景材料放在 sub-md 之后 ----
    background_sections = []

    if worldbook_prompt.strip():
        background_sections.append("# 世界观\n" + worldbook_prompt.strip())

    if characters:
        char_lines = []
        for char in characters:
            if not isinstance(char, dict):
                continue
            name = char.get("name", "")
            if not name:
                continue
            tier = char.get("tier", "")
            if tier == "npc":
                continue
            parts = [f"- **{name}**"]
            if char.get("background"):
                parts.append(f"背景: {char['background']}")
            if char.get("personality"):
                parts.append(f"性格: {char['personality']}")
            char_lines.append("  ".join(parts))
        if char_lines:
            background_sections.append("# 在场角色\n" + "\n".join(char_lines))

    if truth_files_block.strip():
        background_sections.append(
            "# 前文摘要(truth_files)\n"
            "以下 truth_files 是已发生的故事状态,供你理解前文上下文,\n"
            "不是让你规划 truth_files 之后的章节。你要规划的章节,以上面的 sub-md 为准。\n\n"
            + truth_files_block.strip()
        )

    background_block = "\n\n".join(background_sections)

    return f"""\
你是中文网文的资深创作者(或编剧/导演),为下一章做创作判断。
你不是来复述事件清单的——你是来想清楚这章存在的理由,
说清楚笔墨该砸在哪、什么是过渡、什么可以删减。

{top_block}

{background_block}

## 创作引导

1. **先想这章存在的理由是什么。这一章不能没有的东西是什么。这就是戏核。**
2. 不要默认主角是焦点。戏核可以是配角高光、伏笔揭晓、世界观真相、节奏留白。
3. 想清楚戏核后,笔墨自然就有了分配——戏核所在的段落重笔,其他段落服务戏核或简略过渡。
4. 不要预设每章都有主角弧、都要凸显主角、都要回收伏笔。这章有就写,没有就不写。
5. **写"戏核如何承载"这一段时,自然带上技法选择**(长镜头/快切/特写/慢节奏/留白)。**只讲手法,不讲风格**——风格是 Writer 层的事,与你无关。

## 输出格式

按以下结构输出创作者细纲:

# 第 N 章 创作者细纲

## 戏核
这一章的存在是为了 [一句话]。
读者读完这章,记住的东西应该是 [一句话]。

## 戏核如何承载(含技法)
[2-4 段叙述,说清核心场景/瞬间/对照是什么,节奏怎么走、情绪怎么走、氛围怎么营造。在叙述承载方式时,自然带上技法选择(长镜头/快切/特写/慢节奏/留白等)。这部分是细纲的核心,要在这里输出真正的创作判断。不字段化,叙述性。不讲风格,只讲手法。]

## 笔墨分配
- **关键处**:[哪些段落是戏核所在,要展开、要细、要好。指明大致位置(开篇/中段/章末)和篇幅占比(粗略,如"约占全章 40%")]
- **过渡处**:[哪些段落是必要的承接,但不能抢戏,简略带过]
- **删减判断**:[sub-md 里有但这章可以一笔带过或不展开的事]

## 与前后章的关系
- **承**:[CH(N-1) 留下什么,这章哪里接住]
- **启**:[这章给 CH(N+1) 留下什么]

## 硬信息锚点块

这一块是**事实清单**,不是创作内容。从 sub-md 逐条照搬,不改写、不遗漏、不合并。
按以下类型分组,逐条列出 sub-md 中出现的全部硬事实:

- **时间**:所有明确的时间点/时间段(如"十一点二十""三天后""周五下午")
- **地点**:所有具体的地点/地址(如"回声巷17号""市档案馆三楼")
- **人物**:所有出现的人名/头衔/身份(如"角色B""刑侦支队副队长")
- **数字**:所有具体数字(如"六名失踪者""四十一分钟""A-113")
- **约定**:角色之间的约定/承诺/安排(如"不单独进当铺""调阅函")
- **设定**:世界观/道具/规则类设定(如"黑色手套""雨夜亮灯")

{anchor_block}
格式要求:
1. 逐条列出,每条一行,前面加"- "
2. 照搬 sub-md 原文措辞,不得改写数字/时间/称谓
3. 如果某类型在本章 sub-md 中没有出现,写"无"
4. 这一块的目的是让 Writer 对照落实,确保正文不遗漏硬事实

## 输出长度
整体 600-1200 字。

## 输出禁词

本细纲禁止出现以下词汇:
风格、文风、调性、笔触、文笔风格、风格指引、风格强化、声纹、指纹

理由:风格是 Writer 层整本书统一的底色,本细纲只讲本章创作判断和技法手法。
只输出细纲,不输出正文。"""


# ---------------------------------------------------------------------------
# Polish prompt for Kimi Polisher stage
# ---------------------------------------------------------------------------
def build_polish_prompt(skeleton: str) -> str:
    """Build the prompt for Kimi polish stage."""
    return f"""\
你是资深网文文笔编辑。以下是一章正文,仅做局部润色:

{skeleton}

权限:
1. 重写开篇前 500 字以增强抓人度
2. 章末 200 字钩子强化
3. 优化 3-5 处关键对话增加记忆点

禁区:
- 不得改动情节、设定、人物关系、修为层级
- 不得增删段落,字数波动限 ±200 字
- 不得引入原创前情、新角色、新物品
- 不得使用英文词、现代科学/法律梗、穿越梗

输出:完整润色后章节,保持原长度。

字数硬规则：润色后正文的中文字数不得低于原文。如果重写开篇导致字数减少,必须在其他位置补回等量文字。

清理规则：删除正文中所有结构标签,包括但不限于【章末钩子】【伏笔】【作者笔记】【转场】等方括号标记。这些是生成过程的内部标记,不得出现在最终正文中。"""
