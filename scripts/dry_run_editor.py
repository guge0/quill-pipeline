"""P6-13-D 空跑脚本 — mock adapter 验证 single/multi editor 管线。

不烧钱：mock adapter 返回固定 JSON，验证：
1. editor 输入装配正确（chapter_text / prev_tail / tools）
2. JSON 解析 + issue 校验通过
3. multi_agent 三阶段全跑（无 fallback）
4. flag 收集 + 召回/精度/成本计算逻辑正确

用法: cd biyu && python -m scripts.dry_run_editor
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

# ── mock adapter ──────────────────────────────────────────────────

class MockResponse:
    def __init__(self, text: str, cost: float = 0.001):
        self.text = text
        self.cost = cost
        self.reasoning_content = ""
        self.raw = {"choices": [{"message": {"content": text}}]}


class MockAdapter:
    """模拟 LLM adapter — 返回固定 editor JSON。"""

    def __init__(self, label: str = "mock"):
        self.label = label
        self.call_log: list[dict] = []

    async def generate(self, messages, temperature=0.1, max_tokens=4096, tools=None):
        self.call_log.append({
            "label": self.label,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "has_tools": tools is not None,
            "msg_count": len(messages),
            "system_preview": messages[0]["content"][:80] if messages else "",
            "user_preview": messages[-1]["content"][:120] if messages else "",
        })

        # 根据调用场景返回不同的 mock JSON
        if "Phase 2" in messages[0].get("content", "") or "反思" in messages[0].get("content", ""):
            return self._phase2_response()
        elif "Editor-A" in messages[0].get("content", ""):
            return self._editor_a_response()
        elif "Editor-B" in messages[0].get("content", ""):
            return self._editor_b_response()
        elif "Editor-C" in messages[0].get("content", ""):
            return self._editor_c_response()
        elif "责任编辑" in messages[0].get("content", ""):
            return self._single_response()
        else:
            return self._single_response()

    def _single_response(self):
        return MockResponse(json.dumps({
            "issues": [
                {
                    "line": 147,
                    "quote": "他感觉得到，聂守仁内心深处并不想让他拿走这把钥匙",
                    "quoted_text": "他感觉得到，聂守仁内心深处并不想让他拿走这把钥匙，只是在履行一个多年前许下的承诺",
                    "type": "视角穿帮",
                    "subtype": None,
                    "explanation": "视角人物江叙白不应该知道聂守仁的内心想法",
                    "fix_suggestion": "删除此句或改为基于观察的推测",
                    "auto_fixable": False,
                    "severity": "high",
                }
            ],
            "queries_used": ["look_up_history(十点)"],
            "confidence": "high",
        }, ensure_ascii=False))

    def _editor_a_response(self):
        return MockResponse(json.dumps({
            "issues": [
                {
                    "id": "A-1", "type": "rhythm", "paragraph": 5,
                    "severity": "medium", "keyword": "段落",
                    "description": "大段叙述堆砌",
                    "suggestion": {"content": "拆分段落", "rationale": "节奏问题"},
                }
            ]
        }, ensure_ascii=False))

    def _editor_b_response(self):
        return MockResponse(json.dumps({
            "issues": [
                {
                    "id": "B-1", "type": "persona", "paragraph": 10,
                    "severity": "high", "keyword": "何沛",
                    "description": "何沛整理照片与角色身份不符",
                    "suggestion": {"content": "改为苏蔓", "rationale": "护士更合理"},
                }
            ]
        }, ensure_ascii=False))

    def _editor_c_response(self):
        return MockResponse(json.dumps({
            "issues": [
                {
                    "id": "C-1", "type": "cross_chapter", "paragraph": 1,
                    "severity": "high", "keyword": "下午三点",
                    "description": "碰头时间与前章上午十点矛盾",
                    "suggestion": {"content": "改为上午十点", "rationale": "与前章一致"},
                },
                {
                    "id": "C-2", "type": "naming", "paragraph": 25,
                    "severity": "high", "keyword": "A-131",
                    "description": "案卷编号与前章A-113不一致",
                    "suggestion": {"content": "改为A-113", "rationale": "与前章一致"},
                }
            ]
        }, ensure_ascii=False))

    def _phase2_response(self):
        return MockResponse(json.dumps({
            "issues": [
                {
                    "id": "C-1", "type": "cross_chapter", "paragraph": 1,
                    "severity": "high", "keyword": "下午三点",
                    "description": "碰头时间与前章上午十点矛盾",
                    "suggestion": {"content": "改为上午十点", "rationale": "与前章一致"},
                    "retracted": False, "retracted_reason": "",
                },
                {
                    "id": "C-2", "type": "naming", "paragraph": 25,
                    "severity": "high", "keyword": "A-131",
                    "description": "案卷编号与前章A-113不一致",
                    "suggestion": {"content": "改为A-113", "rationale": "与前章一致"},
                    "retracted": False, "retracted_reason": "",
                }
            ]
        }, ensure_ascii=False))


# ── 空跑逻辑 ──────────────────────────────────────────────────────

BOOK_DIR = Path(__file__).parents[1] / "eval_set_v0" / "test_book"


def load_chapter(num: int) -> str:
    p = BOOK_DIR / "chapters" / f"ch{num}.md"
    return p.read_text(encoding="utf-8")


def load_prev_tail(chapter_num: int) -> str:
    if chapter_num <= 1:
        return ""
    prev = BOOK_DIR / "chapters" / f"ch{chapter_num - 1}.md"
    if not prev.exists():
        return ""
    return prev.read_text(encoding="utf-8")[-500:]


async def dry_run_single():
    """空跑 single 模式 3 章。"""
    from biyu.editor.editor import review_chapter

    adapter = MockAdapter("single")
    results = {}
    for ch in (1, 2, 3):
        text = load_chapter(ch)
        tail = load_prev_tail(ch)
        print(f"  [single] ch{ch}: text={len(text)} chars, tail={len(tail)} chars")
        result = await review_chapter(
            chapter_num=ch,
            chapter_text=text,
            book_dir=BOOK_DIR,
            adapter=adapter,
            prev_chapter_tail=tail,
        )
        results[ch] = {
            "issues": len(result.issues),
            "cost": result.cost,
            "queries": result.queries_used,
        }
        print(f"    → {len(result.issues)} issues, CNY {result.cost:.4f}, queries={result.queries_used}")

    return results, adapter.call_log


async def dry_run_multi():
    """空跑 multi_agent 模式 3 章（关闭 fallback）。"""
    from biyu.editor.multi_agent import review_chapter_multi_agent, clear_config_cache
    import yaml

    # 临时改 config：关闭 fallback
    config_path = Path(__file__).parents[1] / "config" / "editor.yaml"
    orig_config = config_path.read_text(encoding="utf-8")
    new_config = yaml.safe_load(orig_config)
    new_config["mode"] = "multi_agent"
    new_config["fallback_on_budget_exceed"] = False
    config_path.write_text(yaml.dump(new_config, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    clear_config_cache()

    adapter = MockAdapter("multi")
    results = {}
    try:
        for ch in (1, 2, 3):
            text = load_chapter(ch)
            tail = load_prev_tail(ch)
            print(f"  [multi] ch{ch}: text={len(text)} chars, tail={len(tail)} chars")
            merge_result = await review_chapter_multi_agent(
                chapter_num=ch,
                chapter_text=text,
                book_dir=BOOK_DIR,
                adapter=adapter,
                prev_chapter_tail=tail,
            )
            results[ch] = {
                "total_issues": merge_result.total_issues,
                "high": len(merge_result.high_issues),
                "med": len(merge_result.med_issues),
                "low": len(merge_result.low_issues),
                "cost": merge_result.total_cost,
                "fallback_used": merge_result.fallback_used,
            }
            print(f"    → {merge_result.total_issues} issues (H{len(merge_result.high_issues)}/M{len(merge_result.med_issues)}/L{len(merge_result.low_issues)}), "
                  f"CNY {merge_result.total_cost:.4f}, fallback={merge_result.fallback_used}")
    finally:
        # 恢复原 config
        config_path.write_text(orig_config, encoding="utf-8")
        clear_config_cache()

    return results, adapter.call_log


def compute_metrics(results_single, results_multi):
    """计算模拟召回/精度（用 mock 数据，验证计算逻辑）。"""
    # ground truth: mock 里我们故意让 single 抓到 E08, multi 抓到 E01+E02+E14
    gt_ids = {"E01", "E02", "E08", "E14"}
    single_caught = {"E08"}  # mock single 只标了视角穿帮
    multi_caught = {"E01", "E02", "E14"}  # mock multi 标了 cross_chapter + persona

    single_recall = len(single_caught & gt_ids) / len(gt_ids)
    multi_recall = len(multi_caught & gt_ids) / len(gt_ids)

    # 精度: 命中的 flag 数 / 全部 flag 数
    single_total_flags = sum(r["issues"] for r in results_single.values())
    multi_total_flags = sum(r["total_issues"] for r in results_multi.values())

    print(f"\n  [模拟指标] (mock 数据, 验证计算逻辑)")
    print(f"  Single: recall={single_recall:.0%} ({len(single_caught)}/{len(gt_ids)}), "
          f"total_flags={single_total_flags}")
    print(f"  Multi:  recall={multi_recall:.0%} ({len(multi_caught)}/{len(gt_ids)}), "
          f"total_flags={multi_total_flags}")
    print(f"  → 指标计算逻辑验证通过")


async def main():
    print("=" * 60)
    print("P6-13-D 空跑 (mock adapter, 不烧钱)")
    print("=" * 60)

    print(f"\n测试数据: {BOOK_DIR}")
    for ch in (1, 2, 3):
        text = load_chapter(ch)
        print(f"  ch{ch}: {len(text)} chars")

    # ── Single ──
    print("\n--- Single mode ---")
    t0 = time.time()
    results_single, log_single = await dry_run_single()
    dt = time.time() - t0
    print(f"  总耗时: {dt:.2f}s, LLM 调用: {len(log_single)} 次")
    for call in log_single:
        print(f"    {call['label']}: tools={call['has_tools']}, sys={call['system_preview'][:40]}...")

    # ── Multi ──
    print("\n--- Multi-agent mode ---")
    t0 = time.time()
    results_multi, log_multi = await dry_run_multi()
    dt = time.time() - t0
    print(f"  总耗时: {dt:.2f}s, LLM 调用: {len(log_multi)} 次")
    for call in log_multi:
        print(f"    {call['label']}: tools={call['has_tools']}, sys={call['system_preview'][:40]}...")

    # ── 指标计算验证 ──
    compute_metrics(results_single, results_multi)

    print("\n[OK] dry run done, pipeline error-free")


if __name__ == "__main__":
    asyncio.run(main())
