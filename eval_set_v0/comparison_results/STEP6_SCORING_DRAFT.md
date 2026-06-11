# P6-13-D Step 6: Machine-Judge Scoring DRAFT

Date: 2026-06-10
Model: deepseek-v4-pro (v4_pro)
Status: **DRAFT — TL adjudicates all flag↔issue hits before any recall is finalized**

---

## §0 数据来源与版本

| Mode / Phase | Source | Correction Method | LLM Cost |
|---|---|---|---|
| Single (all 3 chapters) | `d47_single` captures → replay-corrected | Fixed parser (`range(20)` → `range(200)`) applied to captured responses | ¥0 (replay, zero LLM calls) |
| Multi Phase 1 (all 9 agent×chapter combos) | `d47_single` captures → replay-corrected | Same fixed parser; Phase 1 extraction is downstream of the bug fix | ¥0 (replay, zero LLM calls) |
| Multi Phase 2 (ch2-A, ch3-B) | Targeted re-run | 2 LLM calls (¥0.0186) with corrected Phase 1 v1 lists as input | ¥0.0186 |
| Multi Phase 2 (other 7 agent-chapters) | Existing captures | Existing Phase 2 captures from D re-run; no re-run needed | ¥0 |
| Multi merge | Re-merged from corrected Phase 2 v2 lists | Built from the targeted re-run results + existing captures | ¥0 |

**Cost summary:**

| Item | Cost |
|---|---|
| Original D re-run (all modes) | ¥0.7392 |
| Targeted Phase 2 re-run (ch2-A + ch3-B) | ¥0.0186 |
| **Total** | **¥0.7578** |

**Key bug fixed:** `_repair_json()` had an iteration cap of 20, insufficient for real LLM outputs containing 25+ unescaped ASCII quotes. Single-mode `single_call012.json` (ch3) had 13 pairs (26 fixes needed), causing repair to fail at iter 20 and dropping all ch3 output. Cap raised to 200 with TDD regression test. All single-mode captures replay cleanly through the fixed parser at zero LLM cost.

---

## §1 Phase 1 解析状态表（真跑当时）

```
章  Agent  Phase1 Calls  P1 Final Len  旧parser(20iter)    旧Issues  新Issues  Phase2 v1  状态
1   A      2             810           clean                3         3         —         完整
1   B      2             2223          clean                4         4         —         完整
1   C      5             1089          clean                3         3         —         完整
2   A      2             2935          CAP_HIT(20iters)     0         7         0         空(修回)
2   B      4             2030          clean                4         4         —         完整
2   C      5             1097          clean                3         3         —         完整
3   A      2             531           clean                2         2         —         完整
3   B      4             1027          CAP_HIT(20iters)     0         3         0         空(修回)
3   C      5             1540          clean                5         5         —         完整
```

Note: "旧parser" = the 20-iter cap that was active during the real run. "新Issues" = fixed parser (200-iter). Phase2 v1 = what Phase 2 actually received as input. "空(修回)" = the combo that was fed empty v1 and got targeted re-run.

- **ch2-A**: Old parser hit the 20-iter cap → Phase 1 returned 0 issues → Phase 2 received empty v1 → emitted 0 issues. After fix: 7 Phase 1 issues recovered. Targeted re-run produced valid Phase 2 output.
- **ch3-B**: Old parser hit the 20-iter cap → Phase 1 returned 0 issues → Phase 2 received empty v1 → emitted 0 issues. After fix: 3 Phase 1 issues recovered. Targeted re-run produced valid Phase 2 output.
- **All other combos**: Clean parse under both old and new parser; no data loss.

---

## §2 parser.py diff 关键行 + 回归测试

### Git diff (commit `eb97444`)

```diff
diff --git a/src/biyu/editor/parser.py b/src/biyu/editor/parser.py
index 5396166..ed7bae9 100644
--- a/src/biyu/editor/parser.py
+++ b/src/biyu/editor/parser.py
@@ -200,8 +200,10 @@ def _repair_json(json_str: str) -> str:
         pass

     repaired = json_str
-    # 多轮修复：每次修一个未转义引号，最多尝试 20 轮
-    for _ in range(20):
+    # 多轮修复：每次修一个未转义引号
+    # 上限 200 来自 D 重跑实测：single_call012 有 13 对未转义引号(26 处)，
+    # 旧上限 20 不够，repair 在第 20 轮放弃 → 单章 ch3 解析失败丢输出。
+    for _ in range(200):
         try:
             json.loads(repaired)
             return repaired
```

### Regression test: `test_repair_jsonWithMany_unescaped_quotes`

```python
def test_repair_jsonWithMany_unescaped_quotes(self):
    """Regression: D re-run single_call012 had ~13 pairs (26+) unescaped
    ASCII " inside Chinese text. The 20-iteration cap in _repair_json
    caused repair to fail at iter 20, leaving the JSON unparsable.

    This test synthesises the same shape: many issues, each with two
    unescaped Chinese-quoted phrases inside explanation/fix_suggestion.
    The repair must finish within the configured iteration budget.
    """
    # Build an issues array where each issue contributes 4 unescaped
    # ASCII " (2 pairs of Chinese quotes inside string values).
    # 9 issues × 4 = 36 unescaped quotes → exceeds old 20-iter cap.
    issues_block = ",\n".join(
        '    {\n'
        f'      "line": {i + 1},\n'
        f'      "quote": "前文"标记{i}"出现",\n'
        f'      "type": "跨章一致性",\n'
        f'      "severity": "high",\n'
        f'      "explanation": "此处叙述者说"标记{i}"与后文"回响{i}"矛盾",\n'
        f'      "fix_suggestion": "统一为"标记{i}"或"回响{i}"使全文一致",\n'
        f'      "auto_fixable": false,\n'
        f'      "quoted_text": "前文"标记{i}"出现"\n'
        f'    }}'
        for i in range(9)
    )
    broken = '{\n  "issues": [\n' + issues_block + '\n  ]\n}\n'

    repaired = _repair_json(broken)
    data = json.loads(repaired)  # MUST not raise
    assert len(data["issues"]) == 9
    assert data["issues"][3]["type"] == "跨章一致性"
```

**12/12 tests pass** (verified 2026-06-10)

---

## §3 Ground Truth Canon

14 total issues: 10 detectable, 4 excluded.

| E-id | Category | Description | Detectable | Chapter |
|------|----------|-------------|------------|---------|
| E01 | 跨章·时间 | 苏皓失踪日期 11/19 vs 1/16 | Yes | ch2 |
| E02 | 跨章·数字 | A-131 应为 A-113 | Yes | ch3 |
| E03 | 跨章·头衔 | 聂守仁名字在自我介绍前被使用 | Yes | ch1 |
| E05 | 逻辑·两地 | 何沛电话中翻纸（视觉穿帮） | Yes | ch1 |
| E07 | 逻辑·因果 | 六人体检/生物识别因果推断无中生有 | Yes | ch2 |
| E08 | 视角穿帮 | 聂守仁内心被读心 | Yes | ch1 |
| E09 | 视角·跨章 | 勿配刻字前后矛盾 | Yes | ch1→ch3 cross |
| E10 | 设定矛盾 | 老覃工龄 32年/23年 | Yes | ch3 |
| E11 | 设定矛盾 | 一件证物/三件证物 | Yes | ch1 |
| E12 | 跨章·地点 | 黄铜钥匙编号 第三项/第五项 | Yes | ch1→ch3 cross |
| E04 | 跨章·约定 | — | No (truth_files) | — |
| E06 | 逻辑·数字 | — | No (N/A) | — |
| E13 | 跨章·时间 | — | No (truth_files) | — |

**Excluded reasons:**
- E04: Requires access to `truth_files` not present in chapter text.
- E06: The fact is not in the text at all; no editor can detect it.
- E13: Requires cross-referencing with `truth_files` only.

---

## §4 Single Mode Flags (Replay-Corrected)

Source: `d47_replay_summary.json` → `single`. All quotes verbatim from the JSON.

### Chapter 1 (4 issues)

| Flag | Type | Severity | Quote Preview | Best-guess E-id | Design Coverage |
|------|------|----------|---------------|-----------------|-----------------|
| S1-1 | 视角穿帮 | high | "他感觉得到，聂守仁内心深处并不想让他拿走这把钥匙，只是在履行一个多年前许下的承诺。" | **E08** | single covers 视角穿帮 ✓ |
| S1-2 | 视角穿帮 | high | "'还有个情况，'何沛翻了一页纸，'江湾区路口监控的比对结果出来了。'" | **E05** | single covers 视角穿帮 ✓ |
| S1-3 | 逻辑漏洞 | medium | "握紧钥匙的那一刻，何沛电话里的话再次响起。" | **NEW** | single covers 逻辑漏洞 ✓ |
| S1-4 | 逻辑漏洞 | low | "今晚有雨。" | **NEW** | single covers 逻辑漏洞 ✓ |

### Chapter 2 (2 issues)

| Flag | Type | Severity | Quote Preview | Best-guess E-id | Design Coverage |
|------|------|----------|---------------|-----------------|-----------------|
| S2-1 | 跨章一致性 | high | "苏皓，二十三岁，物流公司临时工，一月十六号晚上失踪，穿灰色连帽衫，对室友说去取个东西" | **E01** partial | (date mismatch: 1/16 vs 11/19) |
| S2-2 | 跨章一致性 | medium | "苏皓，二十三岁" | **NEW** | (age discrepancy 23 vs 22) |

**Hallucination filter rejections (ch2):** 2 flags rejected — hallucinated quotes not found in chapter text:
1. `"王思睿失踪那天晚上，穿的是灰色连帽衫。她对室友说，去取个东西..."` → filtered
2. `"你在查他。你查的人，我都会知道。..."` → filtered

These are edge cases: the LLM fabricated quotes that don't exist in the source text.

### Chapter 3 (3 issues)

| Flag | Type | Severity | Quote Preview | Best-guess E-id | Design Coverage |
|------|------|----------|---------------|-----------------|-----------------|
| S3-1 | 跨章一致性 | high | "老覃今年五十八，在档案馆待了三十二年。" | **E10** | single covers 跨章一致性 ✓ |
| S3-2 | 视角穿帮 | high | "但既然现在出现了四个'取件'——二十年前旧账里的那页，可能就不是废纸了。" | **NEW?** | (cross-chapter knowledge leak) |
| S3-3 | 逻辑漏洞 | medium | "江叙白把档案袋重新放回推车上" | **NEW** | (action repeat without intervening retrieval) |

### Single Mode Summary

| Chapter | Issues | Hallucination Rejections | Parse Errors |
|---------|--------|--------------------------|--------------|
| ch1 | 4 | 0 | 0 |
| ch2 | 2 | 2 | 0 |
| ch3 | 3 | 0 | 1 (recovered by fixed parser) |
| **Total** | **9** | **2** | **1** |

---

## §5 Multi Mode Flags (Corrected Merge)

Source: `comparison_results_corrected.json` → `multi`. All `merged_description` text is verbatim from the JSON. Each flag includes its voters list.

### Chapter 1 (9 issues)

| Flag | Type | Severity | Voters | Merged Description (excerpt) | Best-guess E-id | Design Coverage |
|------|------|----------|--------|------------------------------|-----------------|-----------------|
| M1-A1 | rhythm | medium | A | "[A-1] 在聂守仁开口之前插入主角内心感知，过早泄露对方不愿交出钥匙的意图，打断了悬疑氛围的自然积累，让后续对话失去张力。参考 B-1 的视角分析，此处不仅冲淡悬念，还使叙述者显得拥有超出观察层面的读心能力，双重削弱场景效果。" | **NEW** | single does NOT cover rhythm ✗ |
| M1-A2 | rhythm | low | A | "[A-2] 钥匙落袋与问候之间突然插入聂守仁手套的静态描写，切断对话流，显得节奏卡顿。虽然同行未提及此点，但该插入在对话推进中确造成轻微阅读顿挫，值得调整。" | **NEW** | single does NOT cover rhythm ✗ |
| M1-A3 | hook | medium | A | "[A-3] 结尾处通过主角回忆补出'沉箱所用'，但前文电话并未提及此信息，读者容易困惑这是新增线索还是重复叙述，削弱章节收束的震撼力。C-2 指出的证物数量矛盾虽在不同段落，但同属信息一致性范畴，更说明此处钩子需清晰锚定。" | **NEW** | single does NOT cover hook ✗ |
| M1-B1 | persona | medium | B | "[B-1] 江叙白对聂守仁内心状态的解读过于精确。角色卡定义江叙白为「克制、多疑、记细节」，他能观察到聂守仁手指动作中的不情愿是合理的，但直接推断到「履行一个多年前许下的承诺」超出了观察层面，进入了全知叙述者视角。这让江叙白显得像有读心能力，而非依靠细节推断。" | **E08** | multi B covers persona ✓ |
| M1-B2 | personality_anchor | medium | B | "[B-2] 在守拙斋场景中（从进店到离开），江叙白全程被聂守仁引导节奏：聂守仁抛出「雨夜入店」的判断、聂守仁主动介绍钥匙、聂守仁终止对话。江叙白仅提问两句（「这附近最近有没有人来当过手机」「你们收什么」），没有追问苏皓、没有就钥匙来源深挖、没有在聂守仁关闭对话时尝试突破。作为前刑警和正在寻找失踪朋友的人，这种被动程度削弱了角色的驱动力。" | **NEW** | multi B covers personality_anchor ✓ |
| M1-B3 | dialogue_id | low | B | "[B-3] 江叙白在报刊亭对话和电话对话中多次使用单字或两字回应（「找人」「怎么说」「去了」「好」）。虽然「克制」是角色设定，但这类极简回应在脱离上下文时与多数冷硬型角色难以区分。角色卡 voice_examples 中的「巧合出现一次是巧合，出现三次是安排」「我不信路灯，我信监控」在第1章中未出现，使声音辨识度建立滞后。" | **NEW** | multi B covers dialogue_id ✓ |
| M1-B4 | persona | low | B | "[B-4] 江叙白主动询问监控录像帧数，何沛精确回答后，江叙白没有将帧数信息与自己的店内经历做任何关联分析。以他「记细节」的特质，他在店内走了六步进、十二步出，录音时长七分二十四秒——这些精确时间数据与监控覆盖的四十一分钟之间是否存在可推敲的关系（如覆盖时长恰好覆盖了他进店到出店的时间段），他应该有本能的计算反应。" | **NEW** | multi B covers persona ✓ |
| M1-C2 | facts | medium | C | "[C-2] 何沛在电话中说A-113案"有一件证物始终没有找到"（单件），但结尾处说"有三件证物至今下落不明，其中编号第三项的是一把黄铜钥匙"（三件）。两个说法在数量上矛盾。" | **E11** | multi C covers facts ✓ |
| M1-C3 | cross_chapter | low | C | "[C-3] 昨晚江叙白已在台灯侧光下看清钥匙圆柄内侧第二行刻字为"勿配"，但次日清晨写为"他辨认了将近二十秒，才看清那行字。'勿配。丢了的东西别找回来。'"——"才看清那行字"的措辞与昨晚已读到的事实冲突。" | **E09** | multi C covers cross_chapter ✓ |

### Chapter 2 (14 issues)

| Flag | Type | Severity | Voters | Merged Description (excerpt) | Best-guess E-id | Design Coverage |
|------|------|----------|--------|------------------------------|-----------------|-----------------|
| M2-A1 | rhythm | medium | A | "[A-1] 第3段到第10段（张德福→李秀莲→陈望→赵永志→徐蕾/苏皓）连续罗列失踪者信息，六人档案无对话、无动作打断，形成信息墙。读者在缺乏呼吸感的情况下被迫接收大量相似数据，易产生阅读疲劳。" | **NEW** | — |
| M2-A2 | dialogue_ratio | medium | A | "[A-2] 从第1段到第16段（"宏远物流"之前），整整16个自然段几乎全部是叙述+清单信息，对话为零。苏蔓在场却沉默如道具，削弱了茶餐厅场景的张力。" | **NEW** | — |
| M2-A3 | ai_smell | medium | A | "[A-3] 黑伞比喻"像一盏忘记点亮的旧路灯"属于典型的AI文艺腔——用"忘记点亮""旧路灯"叠加两层意象试图营造孤独/悬疑感，但喻体与本体（伞vs路灯）功能差异过大，读者需跳转理解，反而打断沉浸。" | **NEW** | — |
| M2-A4 | ai_smell | low | A | "[A-4] "窗外有雨声从玻璃缝里渗进来，把那一秒的空白填满了"——"渗进来"+"填满空白"是高频AI句式，用自然意象填补人物沉默，手法过于熟套。" | **NEW** | — |
| M2-A5 | rhythm | medium | A | "[A-5] 从"他没有立刻追出去"到"黑伞已经不见了"共约8个自然段，中间穿插烟头、公交站台、等车人、回头看等多处细节，悬疑张力被反复拉长后衰减。" | **NEW** | — |
| M2-A6 | hook | low | A | "[A-6] 开篇"清单摊在桌上。三十七页。"虽有利落感，但相较前章末"沉箱所用"四字悬念，本章开局缺乏同等力度的钩子将读者拉入新场景。" | **NEW** | — |
| M2-A7 | rhythm | low | A | "[A-7] 从茶餐厅到公寓之间的巷子段落（"他走进巷子深处，雨声在两侧墙壁之间形成回响…"）与黑伞追踪功能重叠，两段"雨巷独行"连续出现，读者感受重复。" | **NEW** | — |
| M2-B1 | symbol_overuse | medium | B | "[B-1] 第2章中'左肩旧伤/右肩旧伤/肩膀不适'出现约5次（拧瓶盖时左肩顿住、右肩旧伤隐痛、左肩抽痛、左手握力六成、右肩低一截），叠加第1章4次提及，跨章节累计频率偏高，标志性身体符号开始呈现规律性出现而非有机融入。" | **NEW** | — |
| M2-B2 | personality_anchor | low | B | "[B-2] P1-P16约十三段的失踪者数据分析中，江叙白几乎完全以'信息处理机'模式运转——翻页、排顺序、画线、标注——克制和记细节的性格特征虽在，但多疑、对结案过快案件的反感等核心锚点被稀释，角色温度降低。" | **NEW** | — |
| M2-B3 | dialogue_id | low | B | "[B-3] 章凝和苏蔓都称呼江叙白为'江老师'，且两人说话均呈克制、简短、尾音不上扬的特征——苏蔓的'克制的焦虑'与章凝的'自信直接'在文本层面的语风差异不够鲜明，去掉叙述标签后易混淆。" | **NEW** | — |
| M2-B4 | persona | low | B | "[B-4] 章凝作为本章重要新出场角色——闯入江叙白住所、掌握多个失踪者信息、与江叙白有旧怨——言行密度高且对主线有推动作用，但角色卡中无记录，无法验证其言行一致性。" | **NEW** | — |
| M2-C1 | cross_chapter | high | C | "[C-1] 苏蔓整理的资料显示苏皓最后一通电话为十一月十九日（11月19日），信号当晚消失。但章凝口述苏皓'一月十六号晚上失踪'。两者相差近两个月，江叙白作为细节敏感人物未对此差异做出任何反应。" | **E01** ✓ | (date 11/19 vs 1/16) |
| M2-C2 | cross_chapter | medium | C | "[C-2] 苏蔓亲述苏皓离家时说的是'很快回来'，未提'取个东西'；章凝却称苏皓'对室友说去取个东西'。苏蔓是姐姐而非室友，且'取个东西'的措辞来自其他失踪者（王思睿、李铭远、张旸）而非苏皓。江叙白对'很快回来'的匹配产生强烈反应，却未察觉'取个东西'与'室友'两处偏差。" | **E01 related** | (取个东西/很快回来) |
| M2-C3 | hooks_audit | low | C | "[C-3] 江叙白从抽屉信封中取出纸条，上有四个名字已用红笔圈起，上方写着'取件'。他盯着这两字看了'大半年'。但根据章凝提供的时间线，王思睿案始于去年九月（距今约五个月），'大半年'的说法在时间感知上偏长。" | **NEW** | — |

### Chapter 3 (10 issues)

| Flag | Type | Severity | Voters | Merged Description (excerpt) | Best-guess E-id | Design Coverage |
|------|------|----------|--------|------------------------------|-----------------|-----------------|
| M3-A1 | rhythm | medium | A | "[A-1] 开篇用三个小段描写雨势、江叙白收伞和何沛的车，环境铺陈过多，缺乏即时冲突或悬念，节奏拖沓。" | **NEW** | — |
| M3-A2 | hook | medium | A | "[A-2] 本章开头未抛出明显的钩子，没有立即呈现危机、谜题或情感张力，很容易让读者失去耐心。" | **NEW** | — |
| M3-B1 | persona | high | B | "[B-1] 老覃在档案馆工作年限前后矛盾。叙述中写"在档案馆待了三十二年"，但老覃本人后文台词为"我在这座档案馆待了二十三年"。同一章内信息不一致，人物背景可信度受损。" | **E10** ✓ | (32年/23年) |
| M3-B2 | symbol_overuse | medium | B | "[B-2] 江叙白左肩旧伤在本章被提及5次（"每分钟三次的频率跳着疼""从隐痛变成钝痛""稍微好了些""一抽一抽地跳""疼得最厉害"）。虽与雨天氛围有叙事关联，但频率过高，形成重复性生理信号轰炸。" | **NEW** | — |
| M3-B3 | symbol_overuse | low | B | "[B-3] 何沛在本章中取烟、磕烟、点烟/不点的动作出现7次，其中"在桌沿上磕了磕"与后文"重新磕了磕，这次是从另一头磕的"措辞重复。虽大多有叙事功能，但密度偏高，接近标志性动作的过度消费。" | **NEW** | — |
| M3-C1 | cross_chapter | high | C | "[C-1] 老覃工作年限前后矛盾：第32段称"在档案馆待了三十二年"，第66段老覃自述"在这座档案馆待了二十三年"。58岁的人不可能同时工作32年和23年。" | **E10** ✓ | (same as B1, 32/23 years) |
| M3-C2 | naming | high | C | "[C-2] 何沛调阅函的档案编号为A-131，但档案袋内容实为A-113（1998年江湾码头沉箱案）。全章讨论的案件编号是A-113，调阅函编号却不同，且无任何解释。" | **E02** ✓ | (A-131/A-113) |
| M3-C3 | forbidden | medium | C | "[C-3] 世界书设定"T3及之前不得揭示聂守仁与沉箱案的关联"。第48段江叙白内心独白和何沛对话中，已明确将聂守仁交出的钥匙与1998年沉箱案证物直接关联，虽属角色推测而非叙事确认，但关联已足够清晰。" | **NEW** | (premature reveal) |
| M3-C4 | cross_chapter | low | C | "[C-4] 第1章末500字何沛称黄铜钥匙是附件清单中"编号第三项"的证物；本章称"第五项"。可解读为"第三项"指三件下落不明证物中的第三个，但仍存在歧义风险。" | **E12** ✓ | (第三项/第五项) |
| M3-C5 | cross_chapter | low | C | "[C-5] 江叙白回忆"苏蔓离开茶餐厅后在门口的雨里站了整整两分钟"。第2章中苏蔓在茶餐厅与江叙白会面后推门离开，但未描写她在门口雨中站立。此处作为新增回忆可接受，但若第2章有空间建议埋一笔伏笔。" | **NEW** | (苏蔓 rain memory) |

### Multi Mode Summary

| Chapter | Issues | Agents | E-id Hits |
|---------|--------|--------|-----------|
| ch1 | 9 | A(3) B(4) C(2) | E08, E11, E09 |
| ch2 | 14 | A(7) B(4) C(3) | E01 |
| ch3 | 10 | A(2) B(3) C(5) | E10×2, E02, E12 |
| **Total** | **33** | | |

---

## §6 Per-Defect Detection Matrix

10 detectable E-ids × 2 modes. ✓/✗ per mode. Design-coverage column shows whether the flag type is within the mode's designed detection scope. TL recall column left blank.

| E-id | Single | Multi | Single 覆盖? | Multi 覆盖? | TL recall |
|------|--------|-------|-------------|-------------|-----------|
| E01 跨章·时间 | ✗ | ✓ (M2-C1) | 跨章一致性 ✓ | cross_chapter ✓ | |
| E02 跨章·数字 | ✗ | ✓ (M3-C2) | 跨章一致性 ✓ | naming ✓ | |
| E03 跨章·头衔 | ? | ? | 跨章一致性 ✓ | naming ✓ | |
| E05 逻辑·两地 | ✓ (S1-2) | ✗ | 视角穿帮 ✓ | facts ✗? | |
| E07 逻辑·因果 | ✗ | ✗ | 逻辑漏洞 ✓ | facts ✓ | |
| E08 视角穿帮 | ✓ (S1-1) | ✓ (M1-B1) | 视角穿帮 ✓ | persona ✓ | |
| E09 视角·跨章 | ✗ | ✓ (M1-C3) | 视角穿帮 ✓ | cross_chapter ✓ | |
| E10 设定矛盾 | ✓ (S3-1) | ✓ (M3-B1, M3-C1) | 跨章一致性 ✓ | persona/cross_chapter ✓ | |
| E11 设定矛盾 | ✗ | ✓ (M1-C2) | 跨章一致性 ✓ | facts ✓ | |
| E12 跨章·地点 | ✗ | ✓ (M3-C4) | 跨章一致性 ✓ | cross_chapter ✓ | |

**Notes on ambiguous (?) entries:**

- **E03 (跨章·头衔):** Single mode did not flag the 聂守仁 name-before-introduction issue. Multi Phase 1 agent C flagged "聂守仁" as a `naming` issue in ch1 (1C-1), but the corrected merge does not include it — C's ch1 merge has only C-2 (facts) and C-3 (cross_chapter). TL must decide if 1C-1's Phase 1 keyword "聂守仁" maps to E03 and whether the merge drop is significant.
- **E05 (逻辑·两地):** S1-2 flags 何沛 flipping paper while on the phone. The flag type is "视角穿帮" but the underlying issue (何沛 can see paper while on phone = two-places contradiction) maps to E05. Multi mode does not have a clean hit — M1-B4 is inference-adjacent but frames the issue differently (帧数 analysis gap, not the paper-flipping visual).
- **E07 (逻辑·因果):** Neither mode cleanly flagged the baseless biometric inference. S1-2 is adjacent (监控比对) but framed as 视角穿帮, not the causal chain issue. Multi has no hit at all. TL must rule.

**TL recall (Single): ____ / 10**
**TL recall (Multi): ____ / 10**

---

## §7 Cost Comparison

| Mode | LLM Calls | Cost | Flags | Notes |
|------|-----------|------|-------|-------|
| Single | 12 | ¥0.2112 | 9 | 3 chapters × ~4 calls each |
| Multi | 40 + 2 targeted | ¥0.5466 | 33 | 9 agent×chapter Phase 1 + Phase 2 + 2 targeted re-runs |
| **Total** | **54** | **¥0.7578** | **42** | |

---

## §8 Edge Cases (D-45 bucket)

1. **Single ch2: 2 flags rejected by hallucination filter.** The LLM emitted quotes that do not exist in the chapter text: (a) `"王思睿失踪那天晚上，穿的是灰色连帽衫。她对室友说，去取个东西..."` and (b) `"你在查他。你查的人，我都会知道。"`. Both correctly filtered. The 2 surviving flags (S2-1, S2-2) are the genuine output.

2. **Single ch3: JSON parse failure on first run.** `single_call012.json` had 13 pairs (26+) unescaped ASCII quotes inside Chinese text. The old 20-iter cap in `_repair_json()` caused repair to give up at iteration 20, leaving ch3 unparsable → 0 issues. Fixed parser (200-iter) recovered all 3 issues via replay. Cost: ¥0.

3. **Multi ch2-A Phase 1: CAP_HIT(20iter).** Agent A's ch2 Phase 1 response (2935 chars) hit the old parser iteration cap, returning 0 issues to Phase 2. After fix: 7 issues recovered. This was the largest single data loss from the bug.

4. **Multi ch3-B Phase 1: CAP_HIT(20iter).** Agent B's ch3 Phase 1 response (1027 chars) hit the old parser iteration cap, returning 0 issues to Phase 2. After fix: 3 issues recovered.

5. **Multi ch2-A Phase 2: stale (fed empty v1), re-run produced 7 issues.** Because Phase 1 returned 0 under the old parser, Phase 2 received an empty v1 list and emitted 0 issues. Targeted re-run with corrected v1 produced valid output with all 7 Phase 1 issues properly considered. Cost: ¥0.0125.

6. **Multi ch3-B Phase 2: stale (fed empty v1), re-run produced 3 issues.** Same pattern as ch2-A. Targeted re-run cost: ¥0.0060.

7. **Multi ch1-A Phase 1: truncation (8192/8192 tokens, content=0), recovered via fallback.** Agent A's ch1 response hit the `max_tokens` limit (8192/8192), producing zero visible content. The tool-loop fallback mechanism recovered the response by forcing a final-answer extraction.

8. **Multi ch3-A Phase 1: truncation (8192/8192 tokens), recovered via fallback.** Same truncation pattern as ch1-A. Fallback recovered the 2-issue output.

---

## §9 NOT Included (per discipline)

The following are intentionally absent from this draft and deferred to TL adjudication:

- **Aggregate winner** (single vs. multi) — not declared.
- **Total recall % / precision / F1** — not computed; matrix leaves TL recall blank.
- **Cost-per-hit comparison** — deferred.
- **Final conclusions about which mode is "better"** — deferred.

TL workflow:
1. Rule on every `?` in §§4–6 (S1-2→E05?, E03?, E07, etc.)
2. Finalize the ✓/✗ columns in §6
3. Compute recall for each mode
4. Re-classify NEW flags as TP (true positive) or FP (false positive)
5. Compute precision
6. Only then compare single vs. multi

---

## §10 STOP

Code 等批。机判草稿交出，TL 逐条裁定 flag↔issue 命中。
