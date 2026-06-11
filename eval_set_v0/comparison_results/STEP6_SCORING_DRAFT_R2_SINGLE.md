# P6-13-D-R2 Step 6: Round 2 Single-Mode Scoring DRAFT

Date: 2026-06-11
Model: deepseek-v4-pro (v4_pro)
Config: identical to R1 (temperature=0.1, max_tokens=8192, tool set, fallback disabled)
Status: **DRAFT — R2 single only; multi crashed (boundary doc §8); TL adjudicates all flag↔issue hits**

---

## §0 数据来源

| Mode / Phase | Source | Cost |
|---|---|---|
| R2 Single (all 3 chapters) | `d47_r2_single/` captures, 14 calls | ¥0.2680 |
| R2 Multi | **NOT scored** — crashed at ch1-AgentC (6 partial captures only) | ¥0.0469 (wasted) |

**R2 vs R1 config**: identical. Same model, temperature, token budget, tool schema, chapter seeds. No code changes between rounds. Only output dir prefix differed (`D47_PREFIX=d47_r2_`).

**Cost summary:**

| Item | Cost |
|---|---|
| R1 all modes (single + multi + targeted) | ¥0.7578 |
| R2 single (complete) | ¥0.2680 |
| R2 multi partial (crashed, ch1 only) | ¥0.0469 |
| **Cumulative** | **¥1.0727** |
| Hard cap | ¥4.50 |

---

## §1 R2 Single Mode Flags

Source: `d47_r2_single/` final emit calls: `single_call005.json` (ch1), `single_call010.json` (ch2), `single_call014.json` (ch3). All parsed through `_repair_json` (200-iter cap). Zero parse errors.

### Chapter 1 (3 issues; R1 had 4)

| Flag | Type | Severity | Quote Preview | Quote in Text? | Best-guess E-id |
|------|------|----------|---------------|----------------|-----------------|
| R2-S1-1 | 视角穿帮 | high | "他感觉得到，聂守仁内心深处并不想让他拿走这把钥匙，只是在履行一个多年前许下的承诺。那种被迫的克制藏在翻书页的手指动作里，藏得并不深。" | Composite (key phrases: "翻书页"✓ "承诺"✗) | **E08** |
| R2-S1-2 | 逻辑漏洞 | medium | "取出手机查看刚才录下的店内环境音。录音时长七分二十四秒" | ✓ FOUND | **NEW** (录音笔→手机设备跳跃) |
| R2-S1-3 | 跨章一致性 | medium | "对了，苏皓的手机相册我重新整理了一遍，按时间排好文件夹发你邮箱了。" | Composite (key phrase "手机相册"✓ "发你邮箱"✗) | **NEW** (何沛/苏蔓重复整理同一份相册) |

**vs R1 ch1 (4 issues):**
- R1-S1-1 (E08) → **R2-S1-1** 再次命中 ✓ (stable)
- R1-S1-2 (E05 何沛翻纸) → **DROPPED** — R2 未标何沛电话中翻纸的视角穿帮
- R1-S1-3 (握紧钥匙回忆) → **DROPPED**
- R1-S1-4 (今晚有雨) → **DROPPED**
- R2 新增: R2-S1-2 (录音笔/手机) + R2-S1-3 (相册重复)

### Chapter 2 (5 issues; R1 had 2+2 hallucinated)

| Flag | Type | Severity | Quote Preview | Quote in Text? | Best-guess E-id |
|------|------|----------|---------------|----------------|-----------------|
| R2-S2-1 | 逻辑漏洞 | medium | "会报警你刚才就报过了。"女人说，"你站门外那会儿我就知道你在。你呼吸声变了。"" | Composite (key phrase "呼吸声变了"✓) | **NEW** (章凝通过门缝听呼吸声不现实) |
| R2-S2-2 | 逻辑漏洞 | medium | ""你换锁太多次了，江老师。"她的声音不高，带一点沙哑，像是刚从干燥的地方回来。"这次我找人配的。"" | Composite (key phrase "换锁太多次"✓) | **NEW** (频繁换锁仍被配钥匙的逻辑缺口) |
| R2-S2-3 | 人设守恒 | high | "她叫章凝。四年前在一桩土地转让纠纷的案子里跟江叙白打过交道..." | ✓ FOUND | **NEW** (紧张场景中info dump角色档案) |
| R2-S2-4 | 逻辑漏洞 | low | "他把笔重新拔开，在空白纸上画了个表格" | ✓ FOUND | **NEW** ("拔开"措辞歧义) |
| R2-S2-5 | 人设守恒 | medium | ""你查到什么了。"章凝问。" | Composite (key phrase "你查到什么了"✓) | **NEW** (闯入者语气过于平淡) |

**vs R1 ch2 (2 surviving + 2 hallucinated):**
- R1-S2-1 (E01 partial: 苏皓失踪日期 11/19 vs 1/16) → **DROPPED** — R2 未标跨章时间矛盾
- R1-S2-2 (苏皓年龄 23 vs 22) → **DROPPED**
- R1 hallucinated ×2 → R2 无额外幻觉被拒（但 R2 的 5 条中 key phrases 均可验证）
- R2 新增 5 条: 全部围绕**章凝**这个新出场角色（逻辑缺口×2 + 人设守恒×2 + 措辞×1），无一条命中 ground truth

### Chapter 3 (1 issue; R1 had 3)

| Flag | Type | Severity | Quote Preview | Quote in Text? | Best-guess E-id |
|------|------|----------|---------------|----------------|-----------------|
| R2-S3-1 | 字面伪影 | high | ""A-131，"他把调阅函还给何沛，转身往走廊更深处的一扇铁门走，"在恒温间最里面的架子上。你们在这等。"" | Hallucinated (text says "A-113" at this location) | **E02** |

**vs R1 ch3 (3 issues):**
- R1-S3-1 (E10: 老覃 32年/23年) → **DROPPED** — R2 未标老覃工龄矛盾
- R1-S3-2 (四个取件 cross-chapter knowledge leak) → **DROPPED**
- R1-S3-3 (档案袋重复放回) → **DROPPED**
- R2 新增: R2-S3-1 (A-131/A-113) → **E02** — R1 single 未命中 E02，R2 命中但 quote 是幻觉

### R2 Single Summary

| Chapter | R1 Issues | R2 Issues | R2 Dropped | R2 New | Quote Status |
|---------|-----------|-----------|------------|--------|--------------|
| ch1 | 4 | 3 | E05, +2 NEW | +2 NEW | 1 FOUND, 2 composite |
| ch2 | 2 (+2 hallucinated) | 5 | E01 partial, +1 NEW | +5 NEW | 2 FOUND, 3 composite |
| ch3 | 3 | 1 | E10, +2 NEW | 0 | 1 hallucinated |
| **Total** | **9** | **9** | | | |

**总 flag 数巧合同为 9，但组成完全不同。**

---

## §2 Per-Defect Detection Matrix: R1 vs R2 Single

10 detectable E-ids. R1 single column from §6 of `STEP6_SCORING_DRAFT.md`. R2 single from this draft.

| E-id | R1 Single | R2 Single | Δ | Note |
|------|-----------|-----------|---|------|
| E01 跨章·时间 | ✓ partial (S2-1) | ✗ | **dropped** | R1 命中苏皓失踪日期不一致；R2 完全未标 |
| E02 跨章·数字 | ✗ | ✓ (R2-S3-1) | **new hit** | R1 single 未命；R2 命中但 quote 幻觉（文本写A-113，LLM改成A-131） |
| E03 跨章·头衔 | ? | ✗ | — | 两轮均未明确命中 |
| E05 逻辑·两地 | ✓ (S1-2) | ✗ | **dropped** | **E05 这轮没有命中** — R1 命中何沛电话中翻纸，R2 跳过 |
| E07 逻辑·因果 | ✗ | ✗ | stable miss | **E07 两轮均未命中** — 六人体检/生物识别推断无中生有，single mode 两轮都未检出 |
| E08 视角穿帮 | ✓ (S1-1) | ✓ (R2-S1-1) | **stable** | 两轮均命中聂守仁读心视角穿帮 ✓ |
| E09 视角·跨章 | ✗ | ✗ | stable miss | 两轮均未标勿配刻字矛盾 |
| E10 设定矛盾 | ✓ (S3-1) | ✗ | **dropped** | R1 命中老覃工龄32/23年；R2 跳过 |
| E11 设定矛盾 | ✗ | ✗ | stable miss | 两轮均未标证物数量矛盾 |
| E12 跨章·地点 | ✗ | ✗ | stable miss | 两轮均未标黄铜钥匙编号第三/第五 |

**R2 single ground truth hits: E08, E02 = 2 / 10**
**R1 single ground truth hits: E08, E05, E10 = 3 / 10** (E01 partial)

**R2 比 R1 少命中 1 个 ground truth (E05, E10 dropped), 新增命中 1 个 (E02). 净变化: −1.**

---

## §3 ch2 多出 3 条分析

R1 ch2 surviving = 2; R2 ch2 = 5; 净多 3 条。逐条对标：

| Extra Flag | Content | 匹配 Ground Truth? | 性质 |
|---|---|---|---|
| R2-S2-1 | 章凝通过 15cm 门缝听辨呼吸声变化 | ✗ | 逻辑合理性审查 — 有价值但非 planted error |
| R2-S2-2 | 频繁换锁仍被配钥匙的逻辑缺口 | ✗ | 同上 |
| R2-S2-5 | 闯入者"你查到什么了"语气平淡 | ✗ | 人设守恒审查 |

**结论**: ch2 多出的 3 条全部指向**章凝**这个 R2 新出场角色的逻辑/人设审查，均属合理的编辑观察，但无一条匹配 planted ground truth (E01, E07)。反而 R1 命中的 E01 (苏皓失踪日期矛盾) 在 R2 中丢失。

---

## §4 E07/E05 命中变化

**E07 (逻辑·因果: 六人体检/生物识别因果推断无中生有)**:
- R1 single: ✗ 未命中
- R2 single: ✗ 未命中
- **稳定丢失。** 两轮 single mode 均未检出六人档案中"体检→生物识别→因果推断"这一无中生有的逻辑跳跃。R1 multi 也未检出。该埋点可能需要跨段落因果链推理，超出当前 single mode 的能力。

**E05 (逻辑·两地: 何沛电话中翻纸/视觉穿帮)**:
- R1 single: ✓ 命中 (S1-2, 标为"视角穿帮")
- R2 single: ✗ 丢失
- **不稳定。** R1 检出了何沛在电话中"翻了一页纸"的视觉穿帮（人在电话对面不应看到翻纸动作），R2 跳过了这一条，转而标了录音笔/手机设备跳跃（R2-S1-2）。

---

## §5 Cost Comparison: R1 vs R2 Single

| Metric | R1 Single | R2 Single | Δ |
|---|---|---|---|
| LLM calls | 12 | 14 | +2 |
| Cost | ¥0.2112 | ¥0.2680 | +¥0.0568 (+27%) |
| Ground truth hits | 3 (E08,E05,E10) | 2 (E08,E02) | −1 |
| Total flags | 9 | 9 | 0 |
| ch1 flags | 4 | 3 | −1 |
| ch2 flags | 2 | 5 | +3 |
| ch3 flags | 3 | 1 | −2 |

R2 贵 27%，ground truth 少 1 hit。Flag 数相同但分布和内容完全不同。

---

## §6 Quote Accuracy

| Category | R2 Count | Description |
|---|---|---|
| FOUND (verbatim in chapter text) | 3 (R2-S1-2, R2-S2-3, R2-S2-4) | Quote is exact substring of chapter text |
| Composite (key phrases found, full quote conflated) | 5 (R2-S1-1, R2-S1-3, R2-S2-1, R2-S2-2, R2-S2-5) | Individual phrases exist but LLM combined them into a single quote that doesn't match verbatim |
| Hallucinated (key content fabricated) | 1 (R2-S3-1) | Quote claims "A-131" but text says "A-113" at that location — LLM hallucinated the error representation |

Note: R1 ch2 had 2 hallucinated flags rejected by filter. R2 had 0 rejections but 5 composite quotes and 1 hallucinated quote that passed through.

---

## §7 R2 Single Tool Loop Behavior

| Chapter | Tool Rounds | DSML Fallback | Final Emit |
|---|---|---|---|
| ch1 | 3 tool rounds (call001-003) → 1 fallback (call004 DSML) → 1 final (call005) | call004: `look_up_visual(黑色手套)`, `look_up_character(江叙白)` | 3 issues |
| ch2 | 3 tool rounds (call006-008) → 1 fallback (call009 DSML) → 1 final (call010) | call009: `look_up_visual(左肩)`, `look_up_visual(钥匙)` | 5 issues |
| ch3 | 3 tool rounds (call011-013) → 1 final (call014) | None (no DSML fallback) | 1 issue |

Pattern: ch1 and ch2 both used 3 tool rounds + 1 DSML fallback + 1 final emit = 5 calls each. ch3 used 3 tool rounds + 1 direct emit = 4 calls. Total: 14 calls.

---

## §8 R2 Multi Crash — 边界留档

**NOT scored.** 6 partial captures in `d47_r2_multi/`:

| Call | Agent | Phase | Tools | Finish | Notes |
|---|---|---|---|---|---|
| 002 | ch1-B | P1 r0 | Yes | tool_calls (4) | Normal |
| 003 | ch1-C | P1 r0 | Yes | tool_calls (4) | Normal |
| 004 | ch1-C | P1 r1 | Yes | tool_calls (8) | Normal |
| 005 | ch1-B | P1 r1 | Yes | tool_calls (3) | Normal |
| 007 | ch1-C | P1 r2 | Yes | tool_calls (7) | Normal |
| **008** | **ch1-C** | **P1 r3 (force-fallback)** | **No** | **stop** | **CRASH** |

**崩溃原因**: ch1-AgentC Phase 1 tool loop 第 3 轮 (round_num=3, `tools=None`), LLM 输出 DSML 文本工具调用而非 JSON。`_extract_tool_calls` 解析 DSML 后, `execute_tool` 执行 `look_up_history(chapter_num=0)`, 但代码期望参数名 `chapter_or_keyword` → `KeyError`。

**第 5 种输出坏法**: LLM 在无 tools schema 时输出 DSML 工具调用，且参数名偏离 schema 定义（`chapter_num` vs `chapter_or_keyword`）。

**R1 同场景**: R1 multi 有 3 次 DSML fallback (call007/020/035), 全部参数名正确。R2 首次出现参数名偏移。

**工程债**: `execute_tool` 硬编码参数名查询, `DSML` 解析后不做 schema 校验 → 工具链脆弱性。归 `emit/tool-loop` 脆弱性，待中枢结构决策定向，当前不修。

---

## §9 NOT Included

- **R2 multi scoring** — 未完成，不评
- **Aggregate winner** (R1 vs R2, single vs multi) — 不宣告
- **Recall % / precision / F1** — 不计算, TL 逐条裁定
- **Cost-per-hit** — 推迟
- **代码改动** — 零。不动 `emit`/`tool`/`parse`

---

## §10 STOP

Code 等批。R2 single 评分草稿交出，R2 multi 崩溃点留档为第 5 种输出坏法证据。零 LLM 花费，零代码改动。等中枢结构决策定向。
