"""FastAPI 主应用 — 挂载路由和静态文件。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from biyu.web.routes import router

app = FastAPI(title="笔驭 BiYu", version="0.1.0")

# 挂载 API 路由
app.include_router(router)

# 挂载静态文件
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
