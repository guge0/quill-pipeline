"""biyu serve — 启动 Web UI。"""
from __future__ import annotations

import sys

import typer
from rich.console import Console

console = Console()


def serve_command(
    port: int = typer.Option(8080, "--port", "-p", help="监听端口"),
) -> None:
    """启动笔驭 Web UI。"""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    import uvicorn

    console.print(f"[bold cyan]笔驭 Web UI 启动中...[/bold cyan]")
    console.print(f"  地址: http://localhost:{port}")

    uvicorn.run(
        "biyu.web.app:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
