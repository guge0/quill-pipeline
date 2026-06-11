# P6-13-D: Editor Recall Re-run + Bug ② Iteration-Limit Follow-up

**日期**: 2026-06-10
**角色**: code (工程执行)
**任务**: D 重跑（已批预算 ¥0.55–0.80，硬上限 ¥1.00）+ 评分草稿 + D-50 归档
**实际花费**: ¥0.7392（single ¥0.2112 + multi ¥0.5280）
**STOP 点**: 停在 TL adjudicate flag↔issue hits 之前；停在 multi Phase 2 重跑决策之前

---

## 1. 重跑执行结果

### 1.1 Single mode（ch1+ch2+ch3, max_tokens=8192, tools, parser 修复已上）

| Chapter | Final Call | Content Chars | Issues (raw emit) | Issues (corrected via replay) | Cost (CNY) |
|---------|------------|---------------|-------------------|-------------------------------|------------|
| ch1 | single_call003 | 2749 | 4 | 4 | 0.0573 |
| ch2 | single_call008 | 2018 | 2 | 2 | 0.0720 |
| ch3 | single_call012 | 1528 | **0 (parse fail)** | **3 (recovered after fix)** | 0.0819 |
| **Total** | — | — | **6** | **9** | **0.2112** |

**Bug ② 真值披露**: ch3 single 在重跑当下产生 0 issues，因为 `_repair_json` 的 20-iteration 上限不够。详见 §2。

### 1.2 Multi mode（3 agents × 2 phases × 3 chapters, fallback_on_budget_exceed=false）

| Chapter | Phase 1 issues (corrected via replay) | Phase 2 issues (stale v1) | Merge issues (stale) | Cost (CNY) |
|---------|---------------------------------------|---------------------------|----------------------|------------|
| ch1 | A=3, B=4, C=3 (=10) | A=3, B=4, C=3 (=10) | 9 | 0.1545 |
| ch2 | A=7, B=4, C=3 (=14) | **A=0** (stale), B=4, C=3 (=7) | 7 | 0.1680 |
| ch3 | A=2, B=3, C=5 (=10) | A=2, **B=0** (stale), C=5 (=7) | 7 | 0.2054 |
| **Total** | **34 raw** | **24 (2 agents stale)** | **23** | **0.5280** |

**Stale v1 cascade 披露**: ch2 AgentA、ch3 AgentB 的 Phase 2 在重跑当下被喂入空 v1（因为旧 parser cap 失败），Phase 2 因此吐 0 issues。详见 §2。

---

## 2. Bug ② Follow-up: Iteration-Limit Defect（TDD 已修）

### 2.1 缺陷描述

`_repair_json` 在 `src/biyu/editor/parser.py` 的循环上限是 20。每轮修复 1 处未转义 ASCII `"`。当 LLM 输出含 25+ 处未转义引号时，20 轮不够，repair 在第 20 轮放弃，返回仍是坏 JSON，下游解析失败。

**实测证据**:
- single ch3 (`single_call012`): 内容含 13 对（=26 处）未转义 `"`, 实际需要 26 轮修复才能解析
- multi ch2-A Phase 1 (`multi_call021`): 类似，需要 >20 轮
- multi ch3-B Phase 1 (`multi_call033`): 类似

### 2.2 触发面

| 路径 | 调用 | 是否被影响 |
|------|------|-----------|
| Single mode `parse_editor_response` | parser.py 内部 `_repair_json` | 是 |
| Multi Phase 1 → `_parse_agent_response` | multi_agent.py 内调用 `_repair_json` | 是 |
| Multi Phase 1 → Phase 2 v1 提取 | `_parse_agent_response` 失败 → 空 AgentIssueList → Phase 2 看到 `"issues": []` v1 | **是（cascade）** |
| Multi Phase 2 → merge | Phase 2 输出已经基于坏 v1 → merge 输出错 | **是（cascade）** |

### 2.3 TDD 修复

**RED**: 加测试 `test_repair_jsonWithMany_unescaped_quotes`（合成 9 issues × 4 处 = 36 未转义引号），原 20-iter 实现必然失败。验证 fail：
```
FAILED tests/test_editor_output_contract.py::TestJSONRepair::test_repair_jsonWithMany_unescaped_quotes
json.decoder.JSONDecodeError: Expecting ',' delimiter: line 19 column 36 (char 459)
```

**GREEN**: 把 `for _ in range(20)` 改为 `for _ in range(200)`，附来源注释。12/12 tests pass：
```
tests/test_editor_output_contract.py::TestJSONRepair::test_repair_jsonWithMany_unescaped_quotes PASSED
... (其余 11 个旧 test 也 pass)
```

### 2.4 Replay 验证（零 LLM 花费）

写 `scripts/replay_d47_fixed_parser.py`，把已 capture 的 D 重跑响应过新 parser：

| 数据点 | 旧 parser | 新 parser (200-iter) | 差异 |
|--------|-----------|----------------------|------|
| single ch1 | 4 | 4 | — |
| single ch2 | 2 | 2 | — |
| single ch3 | **0 (parse fail)** | **3** | +3 |
| multi ch1 Phase 1 (A/B/C) | 3/4/3 | 3/4/3 | — |
| multi ch2 Phase 1 (A/B/C) | **0**/4/3 | **7**/4/3 | +7 (但 Phase 2 已跑) |
| multi ch3 Phase 1 (A/B/C) | 2/**0**/5 | 2/**3**/5 | +3 (但 Phase 2 已跑) |

**Replay 不能修的**: multi Phase 2 的 stale v1 是用旧 parser 在重跑当下产生的。Replay 能让 Phase 1 解出对的 v1，但 Phase 2 的 capture 是基于错 v1 跑出来的，capture 里的 Phase 2 响应本身已"污染"。要拿到对的 Phase 2 输出，**必须用新 parser 重跑 Phase 2**（烧钱，预算约 ¥0.01 — 2 个 agent × 1 call）。

---

## 3. 四个硬成功判据核对

| # | 判据 | 结果 | 证据 |
|---|------|------|------|
| ① | T2 的 E07 进得了 content | **FAIL** | single ch2 final emit (`single_call008`) 的 content 不含 E07 markers（生物识别/体检/同一台机器）。Multi ch2 Phase 1 也不含。**max_tokens 修复有效**（无 truncation，finish=stop），但 LLM 自身没把 E07 当 defect 标。 |
| ② | multi Phase 1 不再空级联 | **PARTIAL** | Phase 1 解析全 9 个 agent×chapter 都拿到 issues（无空级联）。但 **2 个 agent 的 Phase 2 仍丢输出**（ch2-A、ch3-B），因为 Phase 2 的 v1 输入仍是被旧 parser cap 污染的空数组。Bug ② follow-up 修复后，需 Phase 2 重跑才能彻底修。 |
| ③ | 三章都要干净 emit | **PARTIAL** | ch1/ch2 single 干净，ch1/ch2/ch3 multi Phase 1 干净。**ch3 single 在重跑当下 parse 失败**（已用 follow-up 修复并 replay 验证，但 LLM 重跑当下产生的是 0 issues）。 |
| ④ | T1 的 tool-loop 强制出答案生效 | **PASS** | Multi 重跑日志多次出现 "Phase1 agent-X: tool loop exhausted but last response has tool_calls; forcing JSON fallback"。Single ch2 也有 fallback 调用（call007 → call008）。机制工作正常。 |

### STOP 触发

按 P6-13-D 任务规约："任一章仍丢输出（还截断/解析失败/空转）→ STOP 报 TL"。

**触发 STOP 的事件**:
- single ch3 在重跑当下 parse 失败（已 follow-up 修，但当时是 0）
- multi ch2-A Phase 2 / ch3-B Phase 2 stale v1 cascade（已被污染的 Phase 2 capture）

**已采取的"不烧钱"补救**:
- TDD 修了 `_repair_json` iter cap，跑了 12 tests pass
- Replay-verify（零 LLM 花费）证明修复有效
- D-50 prompt archive 完成
- STEP6 scoring draft 完成（不结论）

**未做的（按 STOP 规约）**:
- **没有**自作主张重跑 LLM
- **没有**改设计（仍是 JSON repair 路线，没切到 tool-bearing 式）
- **没有**继续烧钱

---

## 4. TL 决策点

| 决策 | 选项 | 估价 |
|------|------|------|
| A | 接受当前 multi 数据（stale Phase 2，但 Phase 1 全对）作为 D 重跑结果 | ¥0 |
| B | 重跑 multi Phase 2 仅 ch2-A、ch3-B（用新 parser 已修过的 v1 输入） | ~¥0.01 |
| C | 整体重跑 multi（ch1+ch2+ch3 × 全 agent × Phase 1+2，用新 parser） | ~¥0.53 |
| D | 整体重跑 single + multi（用新 parser，得到完整干净对照） | ~¥0.74 |

**Code 的非约束建议**: 选 B — 单点补救最便宜，且只 ch2-A、ch3-B 这两条线被污染；其余 Phase 1+2 数据干净。Code 等批。

---

## 5. E07 (生物识别因果) 专项核查

按硬判据①要求专项核查 E07：

- **ch2 seeded 原文** (从 `single_call004` 用户消息中确认):
  > 他忽然明白了——那六个人不是失踪，是被同一张网络筛选出来的。筛选标准不是随机的，而是基于他们各自的**生物识别数据**。六个人都做过同一种**体检**，**同一家机构**，**同一台机器**。

- **D-47 (旧) single ch2**: E07 出现在 reasoning_content（明确标注 "this conclusion appears out of nowhere"），但 content 被 4096 max_tokens 截断为 146 字符。 → 证明 max_tokens bug 必要

- **D 重跑 (新) single ch2**:
  - finish_reason=stop（未截断）
  - content 2018 字符（完整 JSON）
  - 2 issues 全是日期/年龄矛盾，**没有 E07**
  - 检查 reasoning_content: 同样不含 E07 marker words

- **D 重跑 (新) multi ch2 Phase 1**: A/B/C 三个 agent 的 final emit 也不含 E07 marker words

**结论**: max_tokens 修复（bug ①）**技术上有效**（不再 truncation），但**该 LLM 在该 prompt 下自身不视 E07 为缺陷**。这是 prompt/模型能力问题，不是 pipeline bug。**TL 需在 P6-13-E（或下一轮 prompt tuning）考虑是否改 prompt 引导检测这类无中生有的因果 leap**。

---

## 6. D-50 归档

`eval_set_v0/archives/D50_single_mode_editor_prompt.md` — single-mode editor system prompt 的 frozen 副本，附 source commit (`a1970b0`)、HEAD (`5d3a777`)、provenance 链接。

Multi-mode 的 3 个 agent prompt（A/B/C）**未归档**——若日后稳定，可作 D-50-multi。

---

## 7. 评分草稿（不结论）

`eval_set_v0/comparison_results/STEP6_SCORING_DRAFT.md` — 机器判决草稿。包含：

- 单 mode flag 表（ch1=4 / ch2=2 / ch3=3，附 E-id best-guess）
- Multi mode flag 表（Phase 1 only, 9 agent×chapter, 34 flags, 附 E-id best-guess）
- 10 个 detectable E-ids × 2 modes 的检测矩阵（✓/✗/?）
- **不**含 aggregate winner / 总 recall % / precision 数。等 TL adjudicate。

---

## 8. 修改文件清单

| 文件 | 改动 | 备注 |
|------|------|------|
| `src/biyu/editor/parser.py` | `_repair_json` 循环上限 20 → 200（附来源注释） | bug ② follow-up |
| `tests/test_editor_output_contract.py` | 加 `test_repair_jsonWithMany_unescaped_quotes`（RED→GREEN 已验证） | TDD |
| `scripts/replay_d47_fixed_parser.py` | 新增：用新 parser replay 已 capture 响应 | 零成本验证 |
| `scripts/run_comparison.py` | MergedIssue serialization（keyword/description → merged_description/voters）+ SKIP_SINGLE env var | 重跑必备修复 |
| `scripts/replay_d47_cheap_gate.py` | D47_DIR 路径改为 d47_pre_single | backup 后路径修 |
| `eval_set_v0/comparison_results/d47_pre_single/` | 备份（原 d47_single 重命名） | 保留 D-47 原始 |
| `eval_set_v0/comparison_results/d47_pre_multi/` | 备份（原 d47_multi 重命名） | 保留 D-47 原始 |
| `eval_set_v0/comparison_results/d47_single/` | D 重跑 single captures (12 calls) | 新 |
| `eval_set_v0/comparison_results/d47_multi/` | D 重跑 multi captures (40 calls) | 新 |
| `eval_set_v0/comparison_results/d47_replay_summary.json` | Replay 后的 corrected 数据 | 新 |
| `eval_set_v0/comparison_results/comparison_results.json` | D 重跑 combined 结果（注意 multi 含 stale Phase 2） | 重跑生成 |
| `eval_set_v0/comparison_results/STEP6_SCORING_DRAFT.md` | 评分草稿 | 新 |
| `eval_set_v0/archives/D50_single_mode_editor_prompt.md` | D-50 prompt 归档 | 新 |
| `eval_set_v0/comparison_results/STEP6_RERUN_REPORT.md` | 本报告 | 新 |

---

## 9. STOP 点（再次强调）

- **停在 TL adjudicate flag↔issue hits 之前**（评分草稿交出，等 TL 判）
- **停在 multi Phase 2 重跑决策之前**（§4 选项 A/B/C/D，等 TL 批）
- **没有**自作主张烧钱
- **没有**改设计（仍 JSON repair 路线，没切 tool-bearing 式）

Code 等批。
