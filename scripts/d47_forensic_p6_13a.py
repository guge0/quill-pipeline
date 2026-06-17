"""P6-13-A Step 4: D-47 取证 — multi_agent 配置驱动真跑。

通过 pipeline 正常路径触发 Editor (review_chapter_multi_agent)，
使用 P6-0-PRE 的 110 字已知 issue 文本，不动真书。

输出三样证据到 outputs/P6-13-A/：
① 运行时日志显示 load_editor_config 解析出的真实 config_path 与 mode
② Phase 1 首个 LLM 请求体落盘(tools 字段非空)
③ 三阶段完整走完、未触发 fallback 的证据
"""
import asyncio
import json
import logging
import time
from pathlib import Path

# 确保项目根在 sys.path
import sys
PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from biyu.config import get_registry
from biyu.editor.multi_agent import load_editor_config, clear_config_cache, review_chapter_multi_agent

# P6-0-PRE 的 110 字已知 issue 文本
TEST_TEXT = (
    "陈风今年二十五岁，修炼的是烈火诀。他站在青石镇的街头，望着远处的矿脉。"
    "手中的长剑泛着火红色的光芒。赵天行走过来拍了拍他的肩膀："
    "\"陈兄，你的烈火诀又有突破了。\"陈风微微一笑：\"运气好而已。\""
    "他收起长剑，转身往矿场走去。"
)

# 用一个最小化的 book_dir 来提供工具查询
BOOK_DIR = PROJECT_ROOT  # 工具查询需要 characters.yaml 等，但取证不需要真书

OUTPUT_DIR = PROJECT_ROOT / "outputs" / "P6-13-A"


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(OUTPUT_DIR / "forensic_run.log", encoding="utf-8"),
        ],
    )
    logger = logging.getLogger("d47_forensic")

    # ---- 证据 ①: config_path 与 mode ----
    clear_config_cache()
    config = load_editor_config()
    ed_mode = config.get("mode", "single")

    from biyu.editor import multi_agent as ma_module
    module_file = Path(ma_module.__file__)
    resolved_config_path = module_file.parents[3] / "config" / "editor.yaml"

    logger.info("=== D-47 取证开始 ===")
    logger.info("config_path resolved to: %s", resolved_config_path)
    logger.info("config_path exists: %s", resolved_config_path.exists())
    logger.info("editor mode: %s", ed_mode)
    logger.info("fallback_on_budget_exceed: %s", config.get("fallback_on_budget_exceed"))
    logger.info("fallback_threshold: %s", config.get("fallback_threshold_yuan_per_chapter"))

    config_evidence = {
        "config_path": str(resolved_config_path),
        "config_exists": resolved_config_path.exists(),
        "mode": ed_mode,
        "fallback_on_budget_exceed": config.get("fallback_on_budget_exceed"),
        "fallback_threshold_yuan_per_chapter": config.get("fallback_threshold_yuan_per_chapter"),
    }
    (OUTPUT_DIR / "evidence_1_config.json").write_text(
        json.dumps(config_evidence, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ---- 准备 adapter ----
    registry = get_registry()
    editor_adapter = registry.get_adapter_for_stage("writer")

    # ---- Monkey-patch adapter.generate 来捕获请求体 (证据 ②) ----
    original_generate = editor_adapter.generate
    captured_requests = []

    async def capturing_generate(messages, **kwargs):
        # 只捕获第一个请求体（Phase 1 首轮）
        if not captured_requests:
            request_body = {
                "messages": [
                    {
                        "role": m.get("role", "unknown"),
                        "content": m.get("content", "")[:200] if m.get("content") else "",
                    }
                    for m in messages
                ],
                "tools": kwargs.get("tools"),
                "temperature": kwargs.get("temperature"),
                "max_tokens": kwargs.get("max_tokens"),
            }
            captured_requests.append(request_body)
        return await original_generate(messages, **kwargs)

    editor_adapter.generate = capturing_generate

    # ---- 运行 multi_agent 审稿 ----
    logger.info("开始 review_chapter_multi_agent...")
    t0 = time.time()
    try:
        merge_result = await review_chapter_multi_agent(
            chapter_num=999,  # 不对应真书章节
            chapter_text=TEST_TEXT,
            book_dir=BOOK_DIR,
            adapter=editor_adapter,
            prev_chapter_tail="",
        )
        elapsed = time.time() - t0
        logger.info("review_chapter_multi_agent 完成: %.1fs, CNY%.4f", elapsed, merge_result.total_cost)
    except Exception as e:
        logger.error("review_chapter_multi_agent 失败: %s", e, exc_info=True)
        elapsed = time.time() - t0
        merge_result = None

    # ---- 证据 ②: Phase 1 首个 LLM 请求体 ----
    if captured_requests:
        req_evidence = captured_requests[0]
        (OUTPUT_DIR / "evidence_2_request_body.json").write_text(
            json.dumps(req_evidence, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tools_field = req_evidence.get("tools")
        logger.info("证据②: tools 字段存在=%s, 非空=%s, 工具数=%s",
                     tools_field is not None,
                     bool(tools_field) if tools_field is not None else False,
                     len(tools_field) if tools_field else 0)
    else:
        logger.warning("未捕获到任何请求体")

    # ---- 证据 ③: 三阶段完整走完 ----
    if merge_result:
        phase3_evidence = {
            "total_cost": merge_result.total_cost,
            "total_issues": merge_result.total_issues,
            "high_issues_count": len(merge_result.high_issues),
            "med_issues_count": len(merge_result.med_issues),
            "low_issues_count": len(merge_result.low_issues),
            "fallback_used": merge_result.fallback_used,
            "elapsed_seconds": elapsed,
            "issues": merge_result.to_dict(),
        }

        (OUTPUT_DIR / "evidence_3_phases.json").write_text(
            json.dumps(phase3_evidence, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        logger.info("证据③: fallback_used=%s, total_issues=%d, high=%d",
                     merge_result.fallback_used, merge_result.total_issues,
                     len(merge_result.high_issues))
        if not merge_result.fallback_used:
            logger.info("三阶段完整走完，未触发 fallback ✓")
        else:
            logger.warning("触发了 fallback！")

    # 恢复 adapter
    editor_adapter.generate = original_generate

    # ---- 汇总 ----
    summary = {
        "task": "P6-13-A D-47 forensic run",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "test_text_length": len(TEST_TEXT),
        "elapsed_seconds": elapsed,
        "total_cost": merge_result.total_cost if merge_result else None,
        "fallback_used": merge_result.fallback_used if merge_result else None,
        "evidence_1_config": "evidence_1_config.json",
        "evidence_2_request": "evidence_2_request_body.json",
        "evidence_3_phases": "evidence_3_phases.json",
        "boundary_events": [],
    }
    (OUTPUT_DIR / "forensic_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logger.info("=== D-47 取证完成 ===")
    logger.info("总花费: CNY%.4f", merge_result.total_cost if merge_result else 0)
    logger.info("输出目录: %s", OUTPUT_DIR)


if __name__ == "__main__":
    asyncio.run(main())
