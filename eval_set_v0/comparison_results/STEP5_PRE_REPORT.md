# P6-13-D-PRE: Editor 输出契约修复 + 便宜闸报告

**日期**: 2026-06-10
**角色**: code (工程执行)
**任务**: 编辑输出契约修复 + 便宜闸（中枢已批；本轮 D 召回/成本结果作废）
**LLM 花费**: 零（本任务不烧钱，停在花钱重跑之前）

---

## 1. 三 Bug 修复（输出 emit 路径）

### Bug : max_tokens 适配 reasoning 模型

**问题**: V4-Pro 是 reasoning 模型，reasoning_tokens 计入 completion_tokens（共享 max_tokens 预算）。editor 硬编码 `max_tokens=4096`，导致 reasoning 吃完预算后 content 为空。D-47 证据：T2 call006 `reasoning_tokens=4028/4096`，content 仅 146 字符（截断的 JSON 开头）。

**修复**:
- `config/editor.yaml` 新增 `max_completion_tokens: 8192`
- `editor.py`: `_load_editor_max_tokens()` 从 config 读取，替换硬编码 4096
- `multi_agent.py`: Phase 1 和 Phase 2 都从 `config["max_completion_tokens"]` 读取

**验证**: 便宜闸 B 单测 `TestTokenBudgetConfig` — 3 个测试全过，确认 adapter.generate() 收到 max_tokens=8192。

### Bug : 最终 emit 用稳健 JSON 修复机制

**API 能力调查结果**:
- DeepSeek adapter (`src/biyu/llm/deepseek.py`) **不支持** `response_format` / JSON mode（payload 无此字段）
- 使用 `response_format` 对 reasoning 模型不稳定（reasoning 可能绕过约束）
- 采用方案：**JSON 修复 + 括号闭合**（先查 API 能力再定，不支持则退到修复）

**修复** (`src/biyu/editor/parser.py`):
- `_repair_json()`: 多轮修复，每轮根据 JSONDecodeError 位置定位问题
- `_fix_one_unescaped_quote()`: 利用错误位置定位未转义 ASCII `"`，替换为中文引号 `\u201c`/`\u201d`
- `_close_brackets()`: 截断 JSON 尝试闭合 `} ]`
- `_fuzzy_quote_match()`: 增强正则，统一去除 ASCII `"` 和中文引号（修复后 quote 不逐字匹配原文的问题）
- `multi_agent.py` 的 `_parse_agent_response()` 接入同样的修复

**验证**: 便宜闸 A — T3 single_call011 成功恢复 3 条 issues（含 E02）。

### Bug : tool loop 达上限强制出最终答案

**问题**: `for...else` 之后，最后一轮响应仍可能包含 tool_calls（DSML 格式），导致 final_text 不是 JSON。

**修复**:
- `editor.py`: `for...else` 中检测 `_extract_tool_calls(resp)`，日志告警；然后 `_looks_like_json(final_text)` 为 False 时追加 fallback 调用（不带 tools，明确要求 JSON）
- `multi_agent.py` Phase 1: 同样的 fallback 机制（原先完全没有）

**验证**: 便宜闸 B 单测 `TestToolLoopForceFinal::test_single_mode_loop_exhaust_forces_json` — tool loop 4 轮全返回 tool_calls，第 5 轮 fallback 强制出 JSON。

### 选用 emit 机制总结

| 机制 | 采用 | 原因 |
|------|------|------|
| 原生 response_format / JSON mode | 否 | adapter 不支持；reasoning 模型上不稳定 |
| 专门"提交 issues"工具 | 否 | 需要 API tool-call 校验，对 reasoning 模型不可靠 |
| **JSON 修复 + 括号闭合** | **是** | 处理未转义引号/markdown/截断，零 API 依赖 |

---

## 2. 便宜闸 A：D-47 回放（零成本）

### T3 恢复：成功

`single_call011.json` → 修复后恢复 **3 条 issues**:
1. **E02** (字面伪影, high): `A-131` 应为 `A-113` — auto_fixable
2. (跨章一致性, high): 黄铜钥匙"第五项" vs 第1章"第三项"编号矛盾
3. (逻辑漏洞, medium): 老覃工龄"三十二年" vs "二十三年"矛盾

修复方式：JSON 中 issue #2 的 quote/quoted_text 有未转义 ASCII `"` 包裹"黄铜钥匙（沉箱所用）"。`_fix_one_unescaped_quote` 定位错误位置，替换为中文引号，解析成功。

### T2 恢复：无法恢复（证明 Bug 必要）

`single_call006.json`:
- `finish_reason: "length"`, `completion_tokens: 4096`, `reasoning_tokens: 4028`
- content 仅 146 字符（截断的 JSON 开头，`quoted_text` 值未闭合）
- **E07 在 reasoning 里被明确识别**：所有 T2 响应的 reasoning 都引用了"六个人都做过同一种体检，同一家机构，同一台机器"并标注 "This conclusion appears out of nowhere"（逻辑·因果问题）
- JSON 修复无法恢复：截断发生在字符串值内部，无闭合引号

**结论**: 便宜闸"必要非充分"——
- JSON 修复 (bug ) 能恢复 T3 的 3 条
- T2 的 E07 无法恢复，证明 max_tokens 修复 (bug ) 是必要的
- tool-loop / 截断的真实端到端仍需花钱重跑确认

### 回放脚本

`scripts/replay_d47_cheap_gate.py` — 可重跑验证。

---

## 3. 便宜闸 B：单测（零成本）

`tests/test_editor_output_contract.py` — 11 个测试全过：

| 测试组 | 测试数 | 验证内容 |
|--------|--------|----------|
| TestJSONRepair | 4 | 未转义引号/markdown 剥离/截断闭合/位置定位 |
| TestToolLoopForceFinal | 2 | loop 耗尽强制 JSON / loop 正常退出不 fallback |
| TestTokenBudgetConfig | 3 | config 读取 max_tokens / single 传递 / multi Phase1 传递 |
| TestCharacterCardWiring | 2 | 角色卡可查 / 未知角色返回未找到 |

---

## 4. EV1 角色卡接线

**问题**: `eval_set_v0/test_book/characters.yaml` 用字典格式（顶层角色名），而 `look_up_character` 期望列表格式（`characters: [{name: ...}]`）。D-47 证据：所有角色查询返回"未找到角色"。

**修复**: 转为列表格式（夹具接线，不动检测逻辑）。5 个角色（江叙白/聂守仁/何沛/苏蔓/老覃）现在可查。单测 `TestCharacterCardWiring` 确认。

---

## 5. DEBT-Config-1 复核 + 里程碑

**复核结论**: `editor.yaml` 稳态 `mode: "single"`（P6-13-A 故意设置）。`run_comparison.py` 的 `run_multi()` 在运行时临时 override 为 `multi_agent` + `fallback_on_budget_exceed=false`，跑完在 `finally` 恢复原配置。

D-47 行为证实：multi-agent 模式跑了 36 calls = 21 Phase1-with-tools + 15 Phase2-no-tools（3 agents × 2 phases × 3 chapters）。**multi_agent 按配置端到端执行**。

**里程碑**: `multi_agent 首次确认按配置端到端执行`（D-47 STEP4 行为证实，2026-06-10）。

---

## 6. 重跑估价（13.18）

### D-47 实际花费（基准）

| 模式 | 调用数 | 花费 |
|------|--------|------|
| Single | 11 | ¥0.2081 |
| Multi | 36 | ¥0.3052 |
| **合计** | **47** | **¥0.5133** |

Token 用量: prompt=298,064; completion=61,491 (reasoning=56,356, 占 91.6%)

V4-Pro 定价: input ¥0.001/1k, output ¥0.0035/1k

### 重跑估价（max_tokens 4096 → 8192）

- **prompt_tokens**: 不变（~298K），成本 ≈ ¥0.298
- **completion_tokens**: reasoning 基本不变（~56K）；content 增加（之前被截断的 calls 现在能完整输出）
  - 现实估算: ~82K total → ¥0.287
- **重跑总估价**: **¥0.55 - ¥0.80**
- **保守上限**: ¥1.00

### 重跑硬前置三把

1. 编辑输出修好（本任务）: **完成**
2. Config-1 确认: **完成**（D-47 行为证实）
3. 角色卡接上 & Phase1 空级联消失: **角色卡完成**；Phase1 空级联是 emit 下游，修好后需端到端验证

三把验过 → TL 转老板批 → 批了才烧钱重跑。

---

## 7. STOP 点

- **停在花钱重跑之前**: 不跑真实 D 重跑。重跑需老板批。
- multi Phase1 空级联是否随 emit 修复自动消失: 需端到端验证（花钱），便宜闸无法确认。

---

## 附：修改文件清单

| 文件 | 改动 |
|------|------|
| `config/editor.yaml` | 新增 `max_completion_tokens: 8192` |
| `src/biyu/editor/parser.py` | JSON 修复层 + fuzzy match 增强 |
| `src/biyu/editor/editor.py` | config-driven max_tokens + tool loop fallback |
| `src/biyu/editor/multi_agent.py` | JSON 修复接入 + Phase1 fallback + max_tokens |
| `eval_set_v0/test_book/characters.yaml` | 角色卡转列表格式 |
| `scripts/replay_d47_cheap_gate.py` | 新增：便宜闸 A 回放脚本 |
| `tests/test_editor_output_contract.py` | 新增：便宜闸 B 单测（11 tests） |
