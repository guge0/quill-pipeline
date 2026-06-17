"""¥0 集成自检: install_writer_capture 真的拦截 httpx POST(无真实 HTTP)。

验证 C1 修复(httpx 类级拦截替代 registry.adapter monkey-patch)在
wire 级别正确捕获 DeepSeek chat-completions 请求体与 writer-raw 文本。
不发起任何真实 HTTP 调用 —— 通过把 captured["original"] 替换成 fake_post
让 capturing_post 调到桩函数。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import httpx  # noqa: E402
from scripts.p6_humanity_generate_variant import (  # noqa: E402
    install_writer_capture,
    restore_writer_capture,
)


def test_capture_intercepts_deepseek_post():
    """验证 install_writer_capture 在 httpx.AsyncClient.post 类级别注入,
    且只对 deepseek chat-completions URL 生效。"""
    captured: dict = {}
    install_writer_capture(captured)
    try:
        # 模拟一次 deepseek chat-completions POST
        async def fake_post(self, url, **kwargs):
            # 返回一个假的 httpx.Response 风格对象
            class FakeResp:
                def json(self_inner):
                    return {"choices": [{"message": {"content": "WRITER_RAW_TEXT"}}]}

                status_code = 200

            return FakeResp()

        # 临时把 original_post 替换成 fake_post, 让 capturing_post 调它
        captured["original"] = fake_post

        body = {
            "model": "deepseek-v4-pro",
            "messages": [
                {"role": "system", "content": "S" * 500},
                # I-R1: Writer 请求含 "反机械痕迹" 标记
                {"role": "user", "content": "【Layer 1 硬规则】...\n\n# 反机械痕迹\n- 感叹号 ≤2 处"},
            ],
            "temperature": 0.8,
            "max_tokens": 16384,
            "stream": False,
        }
        client = httpx.AsyncClient()
        asyncio.run(
            client.post(
                "https://api.deepseek.com/v1/chat/completions",
                json=body,
            )
        )

        # 验证 capture 命中
        assert "request_body" in captured
        assert captured["request_body"]["model"] == "deepseek-v4-pro"
        assert captured["request_body"]["messages_count"] == 2
        assert captured["request_body"]["temperature"] == 0.8
        assert captured["writer_raw"] == "WRITER_RAW_TEXT"
    finally:
        restore_writer_capture(captured)


def test_capture_ignores_non_deepseek_post():
    """非 deepseek URL 不被捕获。"""
    captured: dict = {}
    install_writer_capture(captured)
    try:
        async def fake_post(self, url, **kwargs):
            class FakeResp:
                def json(self):
                    return {"choices": [{"message": {"content": "X"}}]}

            return FakeResp()

        captured["original"] = fake_post

        client = httpx.AsyncClient()
        asyncio.run(client.post("https://other.api.com/foo", json={}))

        assert "request_body" not in captured
        assert "writer_raw" not in captured
    finally:
        restore_writer_capture(captured)


def test_capture_skips_non_writer_deepseek_post():
    """I-R1: Architect/Editor 的 DeepSeek POST(无 "反机械痕迹" 标记)不被捕获。"""
    captured: dict = {}
    install_writer_capture(captured)
    try:
        async def fake_post(self, url, **kwargs):
            class FakeResp:
                def json(self_inner):
                    return {"choices": [{"message": {"content": "ARCHITECT_PLAN"}}]}

            return FakeResp()

        captured["original"] = fake_post

        body = {
            "model": "deepseek-v4-pro",
            "messages": [{"role": "user", "content": "Planning prompt for architect"}],
        }
        client = httpx.AsyncClient()
        asyncio.run(
            client.post(
                "https://api.deepseek.com/v1/chat/completions",
                json=body,
            )
        )

        # 非 Writer 请求不被捕获
        assert "request_body" not in captured
        assert "writer_raw" not in captured
    finally:
        restore_writer_capture(captured)
