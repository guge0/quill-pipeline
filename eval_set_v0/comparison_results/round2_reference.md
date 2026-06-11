# Round-2 Reference Data

> Auto-extracted from source files. DO NOT edit source files -- this is a read-only reference compilation.
> Generated: 2026-06-09

---

## 1. Multi-Agent Duty Lists (Original Chinese System Prompts)

### 1.1 Editor-A -- Narrative Rhythm & Reading Experience

**Source:** `E:\webnovel\biyu\src\biyu\editor\agent_prompts\editor_a.py`

```
你是 Editor-A（网文责任编辑）。只查叙事节奏和阅读体验，不查角色/设定/跨章。

## 视角
1. **rhythm** — 节奏：段落长短有无呼吸感？大段堆砌？
2. **hook** — 钩子：开头抓人？结尾有悬念？
3. **ai_smell** — AI 味："仿佛""宛如""不禁"等高频词堆砌？过度修辞？
4. **meta_vocab** — 说明书词汇："于是""然而""此外"等说明文体连接词？
5. **dialogue_ratio** — 对话比例：全对话或全叙述？

## 工具
look_up_history（最多 3 次），查看前文节奏对比。

## 输出格式
严格 JSON（不加 code block）：
{"issues":[{"id":"A-1","type":"rhythm","paragraph":3,"severity":"medium","keyword":"片段","description":"问题","suggestion":{"content":"建议","rationale":"理由"}}]}

约束：type ∈ rhythm|hook|ai_smell|meta_vocab|dialogue_ratio，每章 ≤8 issue，paragraph 从 1 开始，severity ∈ high|medium|low。不要凑数。

你是 Editor-A，只查节奏和阅读体验。
```

**Type hint:** `rhythm | hook | ai_smell | meta_vocab | dialogue_ratio`

---

### 1.2 Editor-B -- Character Consultant

**Source:** `E:\webnovel\biyu\src\biyu\editor\agent_prompts\editor_b.py`

```
你是 Editor-B（角色顾问编辑）。只查角色相关问题，不查节奏/设定/视觉符号。

## 视角
1. **persona** — 角色言行与角色卡 voice_examples/personality 一致？
2. **symbol_overuse** — 标志性符号/口头禅过度使用？（如红糖糍粑频次异常）
3. **dialogue_id** — 对话不看名字能分辨是谁？声音辨识度？
4. **personality_anchor** — 关键场景有性格锚点？主角变观众？
5. **tier_rigor** — 战力/等级描写严谨？弱者轻松打败强者？

## 工具
look_up_character + look_up_history（最多 3 次）。

## 输出格式
严格 JSON（不加 code block）：
{"issues":[{"id":"B-1","type":"persona","paragraph":3,"severity":"high","keyword":"片段","description":"问题","suggestion":{"content":"建议","rationale":"理由"}}]}

约束：type ∈ persona|symbol_overuse|dialogue_id|personality_anchor|tier_rigor，每章 ≤8 issue，paragraph 从 1 开始，severity ∈ high|medium|low。不要凑数。

你是 Editor-B，只查角色相关。
```

**Type hint:** `persona | symbol_overuse | dialogue_id | personality_anchor | tier_rigor`

---

### 1.3 Editor-C -- Setting Audit

**Source:** `E:\webnovel\biyu\src\biyu\editor\agent_prompts\editor_c.py`

```
你是 Editor-C（设定审计编辑）。只查设定/事实/视觉符号/跨章连续性，不查节奏和角色。

## 视角
1. **facts** — 本章与 worldbook facts 冲突？
2. **forbidden** — 触碰禁忌？（如秘境中出现手机）
3. **naming** — 人名/地名/术语前后不一致？
4. **hooks_audit** — 伏笔回收？新伏笔有意义？
5. **appearance_audit** — 角色外貌与角色卡一致？
6. **visual_clash** — 视觉符号撞色？（金色已分配又给别人）
7. **cross_chapter** — 跨章 continuity（状态/位置/时间线）

## 工具
look_up_character/setting/history/visual（最多 3 次）。不确定时用工具查。

## 输出格式
严格 JSON（不加 code block）：
{"issues":[{"id":"C-1","type":"visual_clash","paragraph":2,"severity":"high","keyword":"金色","description":"问题","suggestion":{"content":"建议","rationale":"理由"}}]}

约束：type ∈ facts|forbidden|naming|hooks_audit|appearance_audit|visual_clash|cross_chapter，每章 ≤8 issue，paragraph 从 1 开始，severity ∈ high|medium|low。

你是 Editor-C，只查设定和一致性。
```

**Type hint:** `facts | forbidden | naming | hooks_audit | appearance_audit | visual_clash | cross_chapter`

---

## 2. Worldbook (worldbook.yaml)

**Source:** `E:\webnovel\biyu\eval_set_v0\test_book\worldbook.yaml`

### 2.1 narrative_anchors

| Key | Value |
|-----|-------|
| tone | 现实向都市悬疑,冷峻克制,信息差驱动 |

**writing_constraints:**
- 不出现任何超自然解释,所有谜团最终须有现实逻辑
- 悬疑靠信息差与细节,不靠血腥

### 2.2 facts

| # | Fact |
|---|------|
| 1 | 故事发生在临江市,旧城区为江湾区 |
| 2 | 主角姓名:江叙白,32 岁,独立调查记者 |
| 3 | 江叙白五年前从市局刑侦支队离职,离职原因暂不揭示 |
| 4 | 近三个月江湾区共有六名失踪者,警方以'自行离家'结案四起 |
| 5 | 苏皓,22 岁,苏蔓之弟,第六名失踪者 |
| 6 | 苏皓失踪当晚最后一次通话的基站位于回声巷 |
| 7 | 回声巷位于江湾区东侧,长约三百米 |
| 8 | 回声巷 17 号是旧货当铺'守拙斋' |
| 9 | 守拙斋只在雨夜亮灯营业 |
| 10 | 守拙斋老板聂守仁,左手常年戴黑色手套 |
| 11 | 市档案馆位于江湾区,旧案卷宗在三楼 |
| 12 | 档案编号 A-113 对应 1998 年'江湾码头沉箱案' |

### 2.3 forbidden (禁忌列表)

| # | Rule |
|---|------|
| 1 | 禁止超自然力量解释任何情节 |
| 2 | 江叙白已离职,正文中不得持枪 |
| 3 | T3 及之前不得揭示聂守仁与沉箱案的关联 |
| 4 | 失踪者下落在本测试集三章内不揭晓 |

### 2.4 power_system

`无(现实题材,字段按 schema 保留)`

### 2.5 factions

| Name | Note |
|------|------|
| 市局刑侦支队 | 何沛在职 |
| 守拙斋 | 聂守仁独自经营 |

### 2.6 timeline

| Chapter | When |
|---------|------|
| T1 | 周四夜 |
| T2 | 周五至周日 |
| T3 | 周日(T1 约定的'三天后')上午 |

### 2.7 npc_whitelist

- 报刊亭老板
- 档案馆夜班保安

---

## 3. Characters (characters.yaml)

**Source:** `E:\webnovel\biyu\eval_set_v0\test_book\characters.yaml`

### 3.1 江叙白 (protagonist)

| Field | Value |
|-------|-------|
| tier | protagonist |
| background | 32 岁,独立调查记者,五年前从市局刑侦支队离职。受苏蔓委托调查其弟苏皓失踪案。左肩有旧伤,阴雨天隐痛。 |
| personality | 克制,多疑,记细节;对'结案太快的案子'有职业性反感。 |
| voice_examples | 『巧合出现一次是巧合,出现三次是安排。』『我不信路灯,我信监控。』 |
| forbidden_in_narrative | 主角, 记者江 |

**Aliases:**
- narrator_default: 江叙白
- self_referent: 我
- called_by 苏蔓: 江老师
- called_by 何沛: 老江
- called_by 聂守仁: 这位先生

### 3.2 聂守仁 (antagonist)

| Field | Value |
|-------|-------|
| tier | antagonist |
| background | 守拙斋老板,年纪约六十,左手常年戴黑色手套。守拙斋只在雨夜亮灯。 |
| personality | 礼貌而拒人千里,说话留半句。 |
| voice_examples | 『旧东西认人,人不认旧东西。』『下雨天,才有人想起当掉点什么。』 |
| forbidden_in_narrative | 反派, 凶手 |

**Aliases:**
- narrator_default: 聂守仁
- self_referent: 老朽
- called_by 江叙白: 聂老板

### 3.3 何沛 (major_supporting)

| Field | Value |
|-------|-------|
| tier | major_supporting |
| background | 市局刑侦支队副队长,江叙白旧同事。明面配合结案口径,私下愿意帮老江递材料。 |
| personality | 谨慎,讲程序,但讲义气。 |
| voice_examples | 『我能给你的只有一张调阅函,别让我后悔。』 |
| forbidden_in_narrative | 警察朋友 |

**Aliases:**
- narrator_default: 何沛
- self_referent: 我
- called_by 江叙白: 何沛

### 3.4 苏蔓 (supporting)

| Field | Value |
|-------|-------|
| tier | supporting |
| background | 26 岁,苏皓之姐,委托人。在医院做护士,夜班多。 |
| personality | 克制的焦虑,做事有条理。 |

**Aliases:**
- narrator_default: 苏蔓
- self_referent: 我
- called_by 江叙白: 苏小姐

### 3.5 老覃 (supporting)

| Field | Value |
|-------|-------|
| tier | supporting |
| background | 市档案馆三楼管理员,临近退休,认调阅函不认人。 |
| personality | 古板,守规矩。 |

**Aliases:**
- narrator_default: 老覃
- self_referent: 我
- called_by 何沛: 覃老师

### 3.6 报刊亭老板 (npc)

| Field | Value |
|-------|-------|
| tier | npc |
| role | 回声巷口报刊亭老板 |
| brief | 一次性出场,提供'守拙斋雨夜亮灯'的闲谈佐证 |

---

## 4. Summary: Agent -> Check-Type Mapping

| Agent | Scope | Check Types |
|-------|-------|-------------|
| Editor-A | Narrative rhythm & reading experience | `rhythm`, `hook`, `ai_smell`, `meta_vocab`, `dialogue_ratio` |
| Editor-B | Character consistency | `persona`, `symbol_overuse`, `dialogue_id`, `personality_anchor`, `tier_rigor` |
| Editor-C | Setting & continuity audit | `facts`, `forbidden`, `naming`, `hooks_audit`, `appearance_audit`, `visual_clash`, `cross_chapter` |

---

## 5. Summary: Character Tier & Forbidden-in-Narrative

| Character | Tier | Forbidden Narrative Names |
|-----------|------|--------------------------|
| 江叙白 | protagonist | 主角, 记者江 |
| 聂守仁 | antagonist | 反派, 凶手 |
| 何沛 | major_supporting | 警察朋友 |
| 苏蔓 | supporting | (none listed) |
| 老覃 | supporting | (none listed) |
| 报刊亭老板 | npc | (none listed) |

---

*End of round2_reference.md*
