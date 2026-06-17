#!/usr/bin/env python3
"""P6-人味 A/B 改版生成: 反机械硬约束版 Writer prompt。

注入方式(§6 不改 prompt 文件/修复器): 运行时 monkey-patch
`biyu.prompts.chapter_writer.build_layer3_constraints` —— pipeline.py 在
`if prompt_version=='v4'` 内每次重新 from-import 该函数,故 patch 源模块即生效。
生成产物落 eval_set_v0/p6_humanity/variant/，不碰真书。

⚠ 控制变量(D-45): 除"Layer3 追加反机械约束"外全固定 —— 同 v4、同隔离书、
   同 temp/max_tokens、polish off、冻结 truth、同 Editor single。
⚠ n=2(改版 ×3章 ×2);成本先估(Task 7 硬停),批了才跑(Task 8)。
"""
from __future__ import annotations
import asyncio
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
OUT_DIR = PROJECT_ROOT / "eval_set_v0" / "p6_humanity" / "variant"

ANTI_MECHANICAL_BLOCK = """

# 反机械痕迹(本测试书专用约束 —— P6-人味 A/B 改版)
- 感叹号仅用于真正的情绪高潮或惊呼,整章不超过 2 处;其余一律不用
- 破折号"——"每章不超过 3 处,不为断句而断句
- 禁止四字成语/四字短语连续堆砌,同一段内不超过 2 个四字格
- 段落长度必须长短交错,不得连续 3 段以上字数接近
- 避免连续句子字数过于整齐的对仗/排比,句子应有自然的长短参差
"""


def install_anti_mechanical_patch() -> None:
    """wrap build_layer3_constraints,在 LAYER3_END 标记前插入(= Layer3 块末尾)。"""
    import biyu.prompts.chapter_writer as cw
    original = cw.build_layer3_constraints

    def patched(target_words: int = 5000) -> str:
        base = original(target_words)
        end = cw.LAYER3_END
        if end in base:
            return base.replace(end, ANTI_MECHANICAL_BLOCK.strip() + "\n\n" + end, 1)
        return base + "\n" + ANTI_MECHANICAL_BLOCK.strip()

    cw.build_layer3_constraints = patched  # pipeline 的 from-import 会取到它


_WRITER_MARKER = "反机械痕迹"  # 由 install_anti_mechanical_patch 注入 Layer3,只入 Writer


def _is_writer_request(body: dict) -> bool:
    """I-R1: 通过扫描消息体中是否含 "反机械痕迹" 标记来识别 Writer 请求。

    该标记由 install_anti_mechanical_patch 注入 Layer3,只进入 Writer 的请求体。
    Architect/Editor 的 DeepSeek chat-completions POST 不含该标记,返回 False。
    """
    for m in body.get("messages", []):
        content = m.get("content", "") or ""
        if isinstance(content, str) and _WRITER_MARKER in content:
            return True
    return False


def install_writer_capture(captured: dict) -> None:
    """捕获 Writer 首个请求体(D-47 取证) + writer-raw 文本。

    在 httpx.AsyncClient.post 类级别注入(参照 capture_d47_request_v2.py),
    这样无论哪个 registry/adapter 实例发起的 DeepSeek chat-completions POST
    都会被拦截。

    I-R1 防串台: 通过扫描消息体中是否含 "反机械痕迹" 标记(该标记由
    install_anti_mechanical_patch 注入 Layer3,只入 Writer 请求)来识别 Writer
    请求 —— Architect/Editor 的 DeepSeek POST 不含该标记,被跳过。
    """
    import httpx

    if "original" in captured:
        return  # 已安装,避免重复 wrap(I5: 显式短路)
    original_post = httpx.AsyncClient.post
    captured["original"] = original_post

    async def capturing_post(self, url, **kwargs):
        url_str = str(url)
        is_ds_chat = "deepseek" in url_str and "chat/completions" in url_str
        body = kwargs.get("json", {}) or {}

        # I-R1: 只捕获 Writer 请求 —— Writer 的消息体含 "反机械痕迹" 标记
        # (该标记由 install_anti_mechanical_patch 注入到 Layer3,只入 Writer)
        # Architect/Editor 的 DeepSeek 请求不含该标记,被跳过。
        if is_ds_chat and "request_body" not in captured and _is_writer_request(body):
            entry = {
                "url": url_str,
                "model": body.get("model", ""),
                "messages_count": len(body.get("messages", [])),
                "temperature": body.get("temperature"),
                "max_tokens": body.get("max_tokens"),
                "stream": body.get("stream"),
                "has_tools": bool(body.get("tools")),
            }
            msgs_summary = []
            for m in body.get("messages", []):
                content = m.get("content", "") or ""
                msgs_summary.append({
                    "role": m.get("role"),
                    "content_length": len(content),
                    "content_first_300": content[:300],
                })
            entry["messages"] = msgs_summary
            captured["request_body"] = entry
        # 调用真正的 httpx post
        result = await captured["original"](self, url, **kwargs)
        # 同样的标记过滤用于 writer_raw 提取
        if is_ds_chat and "writer_raw" not in captured and _is_writer_request(body):
            try:
                data = result.json()
                captured["writer_raw"] = data["choices"][0]["message"]["content"]
            except Exception:
                pass  # JSON 解析失败时不阻塞流程
        return result

    httpx.AsyncClient.post = capturing_post


def restore_writer_capture(captured: dict) -> None:
    """恢复 httpx.AsyncClient.post 到安装前的原始方法。"""
    import httpx
    if "original" in captured:
        httpx.AsyncClient.post = captured["original"]
        del captured["original"]


def assert_d45_controls() -> None:
    """D-45 控制变量启动断言(fail-fast 保持 A/B 干净)。

    检查 pipeline_config 中:
    - polish_enabled 必须为 False(改版只动 Layer3,不允许多变量)
    - editor_enabled 必须为 True(与基线一致)
    - editor.yaml 的 mode 必须为 "single"(与基线一致)

    任何不符 → 打印明确错误并 raise RuntimeError。
    不自动改 models.yaml(§6 no-touch)。
    """
    from biyu.config import get_registry
    from biyu.editor.multi_agent import load_editor_config

    registry = get_registry()
    pipeline_cfg = registry.get_pipeline_config()

    errors: list[str] = []

    polish_enabled = pipeline_cfg.get("polish_enabled", True)
    if polish_enabled is not False:
        errors.append(
            f"polish_enabled 必须为 False(当前: {polish_enabled!r},"
            f"缺省默认 True)。请在 config/models.yaml 的 pipeline 段设置 "
            f"polish_enabled: false。D-45 要求改版只动 Layer3,Polish 必须关。"
        )

    editor_enabled = pipeline_cfg.get("editor_enabled", True)
    if editor_enabled is not True:
        errors.append(
            f"editor_enabled 必须为 True(当前: {editor_enabled!r})。"
            f"基线启用了 Editor,A/B 要求一致。"
        )

    ed_config = load_editor_config()
    ed_mode = ed_config.get("mode", "single")
    if ed_mode != "single":
        errors.append(
            f"editor mode 必须为 'single'(当前: {ed_mode!r})。"
            f"请在 config/editor.yaml 中设 mode: single。基线用 single,A/B 要求一致。"
        )

    if errors:
        print("=" * 60)
        print("[D-45 控制变量断言失败] A/B 干净性无法保证,中止:")
        for e in errors:
            print(f"  - {e}")
        print("=" * 60)
        raise RuntimeError("D-45 控制变量断言失败: " + "; ".join(errors))


async def generate_one(chapter_key: str, run: int) -> dict:
    from biyu.pipeline import generate_chapter
    from scripts.generate_baseline import setup_book_dir, get_truth_source, BOOK_DIR
    chapter_num = int(chapter_key[1:])  # C2: 兼容 T10+(多章号)
    setup_book_dir(BOOK_DIR, chapter_key, get_truth_source(chapter_key))
    captured: dict = {}
    # I4: install_writer_capture 按章调用 —— 每章需要独立的 captured dict + restore;
    # 而 install_anti_mechanical_patch 在 main() 中只调一次(模块级 rebind 持久)
    install_writer_capture(captured)
    t0 = time.time()
    boundary = []
    result = None
    try:
        result = await generate_chapter(book_dir=BOOK_DIR, chapter_num=chapter_num,
                                        prompt_version="v4")
    except Exception as e:
        import traceback
        boundary.append({"type": "RUN_FAIL", "chapter": chapter_key, "run": run,
                         "error": str(e), "traceback": traceback.format_exc()})
    restore_writer_capture(captured)
    elapsed = time.time() - t0
    if result is not None:
        for w in result.warnings:
            boundary.append({"type": "WARNING", "detail": w})
        if result.word_count < 3000:
            boundary.append({"type": "SHORT_CHAPTER", "word_count": result.word_count})
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if result and result.final_text:
        (OUT_DIR / f"run{run}_{chapter_key}_final.md").write_text(
            result.final_text, encoding="utf-8")
    if captured.get("writer_raw"):
        (OUT_DIR / f"run{run}_{chapter_key}_writer_raw.md").write_text(
            captured["writer_raw"], encoding="utf-8")
    return {"chapter": chapter_key, "run": run,
            "word_count": result.word_count if result else 0,
            "cost_cny": result.cost_cny if result else 0.0,
            "elapsed_s": elapsed, "boundary_events": boundary,
            "had_writer_raw": bool(captured.get("writer_raw")),
            "request_body": captured.get("request_body")}


async def main(runs: int = 2) -> None:
    # I4: install_anti_mechanical_patch 在 main() 调一次 —— 模块级 rebind
    # (cw.build_layer3_constraints = patched) 对所有后续章节持久生效,
    # 不需要每章重装;install_writer_capture 则每章独立(见 generate_one)。
    install_anti_mechanical_patch()
    # D-45 控制变量启动断言(fail-fast)
    assert_d45_controls()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("P6-人味 A/B 改版生成(反机械硬约束版)")
    print(f"runs={runs}, chapters=T1/T2/T3, prompt=v4+反机械patch")
    print("=" * 60)
    all_res = []
    total_cost = 0.0
    for run in range(1, runs + 1):
        for ch in ["T1", "T2", "T3"]:
            print(f"--- run{run} {ch} ---")
            r = await generate_one(ch, run)
            total_cost += r["cost_cny"]
            all_res.append(r)
            print(f"  cost CNY{r['cost_cny']:.4f}, {r['elapsed_s']:.0f}s, "
                  f"writer_raw={r['had_writer_raw']}")
    summary = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "variant": "anti_mechanical_hard_constraints",
               "runs": runs, "total_cost_cny": total_cost, "results": all_res}
    (OUT_DIR / "variant_runs.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=" * 60)
    print(f"完成。总成本 CNY{total_cost:.4f}。边界事件 {sum(len(r['boundary_events']) for r in all_res)} 个")
    print(f"→ {OUT_DIR / 'variant_runs.json'}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    asyncio.run(main(runs=n))
