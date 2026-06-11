# P6-13-D Step 4 Results: Editor Recall Comparison

Date: 2026-06-09
Model: deepseek-v4-pro (v4_pro)

## 1. Test Setup

- Effective test set: **10 detectable issues** (of 14 total)
- Excluded: E04 (truth_files only), E06 (fact not in text), E13 (truth_files only) — structurally undetectable
- `look_up_history` returns CLEAN chapters (not seeded) — cross-chapter reference is fair
- `prev_tail` (500 chars) from CLEAN previous chapter
- Multi-agent: fallback disabled (`fallback_on_budget_exceed: false`)
- Characters/worldbook in test_book: minimal (no voice_examples, no detailed cards)

## 2. Raw Results

### Single Mode (1 editor, 5 issue types)
| Chapter | Issues Returned | LLM Calls | Cost (CNY) | Failure Mode |
|---------|----------------|-----------|------------|--------------|
| T1 | 0 | 3 | 0.0651 | Tool loop: exhausted rounds calling tools, never produced JSON |
| T2 | 0 | 3 | 0.0563 | Token truncation: finish_reason="length" at 4096 tokens |
| T3 | 0 | 5 | 0.0867 | JSON parse error: unescaped ASCII `"` in string values |
| **Total** | **0** | **11** | **0.2081** | |

### Multi-Agent Mode (3 editors × 2 phases, fallback=False)
| Chapter | Issues Returned | LLM Calls | Cost (CNY) | Fallback |
|---------|----------------|-----------|------------|----------|
| T1 | 0 | 12 | 0.0869 | False |
| T2 | 0 | 12 | 0.0978 | False |
| T3 | 0 | 12 | 0.1205 | False |
| **Total** | **0** | **36** | **0.3052** | **No** |

D-47 proof: 21 with-tools (Phase 1) + 15 no-tools (Phase 2) = 36 calls. Full 3 agents × 2 phases confirmed.

## 3. What the LLM Actually Found (Lost to Pipeline Failures)

Despite reporting 0 issues, the LLM DID identify defects in single mode:

| Chapter | What LLM Found | Where Lost | Pipeline Bug |
|---------|---------------|------------|--------------|
| T1 | Never reached JSON output stage | Tool loop exhaustion | LLM kept calling tools for 3 rounds, never transitioned to JSON |
| T2 | **E07** (baseless biometric inference) identified in reasoning | Token truncation | max_tokens=4096; reasoning consumed most tokens, JSON output truncated mid-write |
| T3 | **E02** (A-131 typo), plus 2 extra issues (第五项 vs 第三项; 老覃工龄 32年 vs 23年) | JSON parse error | LLM used unescaped ASCII `"` (U+0022) inside JSON string values |

Multi-agent: All Phase 1 editors returned empty arrays. Editor-C DID call `look_up_history` (verified in calls 017, 029, 031) but got stuck in tool call loops and never produced final JSON.

## 4. Per-Issue Recall

| ID | Category | Tier | Detectable? | Single | Multi | LLM Output Exists? |
|----|----------|------|-------------|--------|-------|-------------------|
| E01 | 跨章·时间 | B (cross) | Yes | — | — | No (T3 JSON parse error) |
| E02 | 跨章·数字 | B (cross) | Yes | **FOUND** (parse error) | — | Single: yes, in broken JSON |
| E03 | 跨章·头衔 | A (intra) | Yes | — | — | No |
| E05 | 逻辑·两地 | A (intra) | Yes | — | — | No (T1 tool loop) |
| E07 | 逻辑·因果 | A (intra) | Yes | **FOUND** (truncated) | — | Single: in reasoning content |
| E08 | 视角穿帮 | A (intra) | Yes | — | — | No (T1 tool loop) |
| E09 | 视角·跨章 | B (weak) | Yes | — | — | No |
| E10 | 设定矛盾 | A (intra) | Yes | — | — | No (T1 tool loop) |
| E11 | 设定矛盾 | A (intra) | Yes | — | — | No |
| E12 | 跨章·地点 | B (cross) | Yes | — | — | No (T3 JSON parse error) |
| E04 | 跨章·约定 | — | **No** (truth_files) | N/A | N/A | — |
| E06 | 逻辑·数字 | — | **No** (N/A) | N/A | N/A | — |
| E13 | 跨章·时间 | — | **No** (truth_files) | N/A | N/A | — |

**Official recall: Single 0/10, Multi 0/10**
**Sub rosa: Single found E02+E07 (lost to pipeline), Multi found nothing**

## 5. Precision

Both modes returned 0 flags. Precision is undefined (0/0).

## 6. Coverage Gap Analysis

| Issue | Single Type Coverage | Multi Agent Coverage | In-scope? |
|-------|---------------------|---------------------|-----------|
| E01 跨章·时间 | 跨章一致性 ✓ | Editor-C cross_chapter ✓ | Both in scope |
| E02 跨章·数字 | 跨章一致性 ✓ | Editor-C naming ✓ | Both in scope |
| E03 跨章·头衔 | 跨章一致性 ✓ | Editor-C facts ✓ | Both in scope |
| E05 逻辑·两地 | 逻辑漏洞 ✓ | Editor-C facts ✓ | Both in scope |
| E07 逻辑·因果 | 逻辑漏洞 ✓ | Editor-C facts ✓ | Both in scope |
| E08 视角穿帮 | 视角穿帮 ✓ | Editor-C facts ✓ | Both in scope |
| E09 视角·跨章 | 视角穿帮 ✓ | Editor-C facts ✓ | Both in scope |
| E10 设定矛盾 | 跨章一致性 ✓ | Editor-C visual_clash ✓ | Both in scope |
| E11 设定矛盾 | 跨章一致性 ✓ | Editor-C visual_clash ✓ | Both in scope |
| E12 跨章·地点 | 跨章一致性 ✓ | Editor-C cross_chapter ✓ | Both in scope |

All 10 detectable issues are within both modes' declared type coverage. Recall failure is not a coverage gap — it's a pipeline robustness failure.

## 7. Cost

| Mode | Actual Cost (CNY) | Calls | Avg Cost/Chapter |
|------|-------------------|-------|-----------------|
| Single | 0.2081 | 11 | 0.0694 |
| Multi | 0.3052 | 36 | 0.1017 |
| **Total** | **0.5133** | **47** | — |

Budget: 2.0 CNY. Actual: 0.51 CNY (25.7% of budget).

## 8. Critical Pipeline Bugs Identified

1. **Token truncation** (T2): max_tokens=4096 is insufficient. LLM uses tokens for reasoning, leaving too few for JSON output. The T2 response was cut off at 146 chars of content after 13716 chars of reasoning.
   - Fix: Increase max_tokens for editor, or use separate reasoning/output budgets.

2. **No JSON repair** (T3): LLM frequently generates malformed JSON (unescaped quotes, markdown wrapping, DSML format). The parser has no retry/repair mechanism.
   - Fix: Add JSON repair (handle unescaped quotes, strip markdown, retry on parse failure).

3. **Tool call loops** (T1, Multi all): LLMs get stuck calling tools round after round without transitioning to the final JSON output. The loop limit (3 rounds) is hit but the last response is still tool calls, not JSON.
   - Fix: Reduce max_tool_rounds, or force JSON output on the last round by not passing tools.

4. **Multi-agent Phase 1 → Phase 2 cascade**: When ALL Phase 1 agents return empty arrays, Phase 2 has nothing to reflect on, producing trivially empty results. No mechanism to detect and retry.
   - Fix: Add Phase 1 empty-check; if all empty, re-run with simplified prompt.

5. **Missing character cards**: `look_up_character` returns "未找到角色" for all characters, causing editors to waste tool calls and lose confidence. The test_book's characters.yaml has minimal entries.
   - This is a test setup issue, not a pipeline bug — but it significantly impacts multi-agent performance.

## 9. Files

- Seeded chapters: `eval_set_v0/baseline/T{1,2,3}_seeded.md`
- Clean chapters (in test_book for look_up_history): `eval_set_v0/test_book/chapters/ch{1,2,3}.md`
- D-47 single request/response: `eval_set_v0/comparison_results/d47_single/` (11 files)
- D-47 multi request/response: `eval_set_v0/comparison_results/d47_multi/` (36 files)
- Summary JSON: `eval_set_v0/comparison_results/comparison_results.json`
- Dry run script: `scripts/dry_run_editor.py`
- Comparison script: `scripts/run_comparison.py`
- This report: `eval_set_v0/comparison_results/STEP4_REPORT.md`
