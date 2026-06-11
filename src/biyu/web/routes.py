"""API 路由 — 所有 REST + SSE 端点。"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncGenerator

import yaml
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from biyu.config import BookConfig, get_data_root, load_characters_yaml, resolve_book_dir
from biyu.truth_files import read_all_truth_files, truth_dir
from biyu.web.sse import make_event, sse_generator

router = APIRouter()


# ── 辅助 ────────────────────────────────────────────────────────────────────

def _book_dir(book: str) -> Path:
    try:
        return resolve_book_dir(book)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── 书列表 / 新建 ───────────────────────────────────────────────────────────

@router.get("/api/books")
def list_books():
    """扫描 data/ 下所有 book.json，返回书列表。"""
    data_root = get_data_root()
    books = []
    for d in sorted(data_root.iterdir()):
        if d.is_dir() and (d / "book.json").exists():
            try:
                meta = json.loads((d / "book.json").read_text(encoding="utf-8"))
                books.append({"name": d.name, **meta})
            except Exception:
                books.append({"name": d.name})
    return books


@router.post("/api/books")
def create_book(payload: dict):
    """新建书（调用 init_command 核心逻辑）。"""
    title = payload.get("title")
    genre = payload.get("genre", "xuanhuan")
    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    from biyu.cli.init_cmd import init_command
    import typer

    try:
        init_command(title=title, genre=genre)
    except SystemExit:
        raise HTTPException(status_code=400, detail="init failed")
    return {"status": "ok", "name": title}


# ── 章节列表 ────────────────────────────────────────────────────────────────

@router.get("/api/books/{book}/chapters")
def list_chapters(book: str):
    """返回章节列表（含大纲、正文状态）。"""
    bd = _book_dir(book)
    bk = BookConfig(bd)
    chapters = []

    # 扫描大纲和正文
    outline_nums = set()
    for p in sorted(bk.outlines_dir.glob("ch*.md")):
        try:
            n = int(p.stem.replace("ch", ""))
            outline_nums.add(n)
        except ValueError:
            pass

    content_nums = set()
    for p in sorted(bk.chapters_dir.glob("ch*.md")):
        try:
            n = int(p.stem.replace("ch", ""))
            content_nums.add(n)
        except ValueError:
            pass

    all_nums = sorted(outline_nums | content_nums)
    for n in all_nums:
        # 读取 meta.json
        meta_path = bk.chapter_log_dir(n) / "meta.json"
        meta = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        chapters.append({
            "chapter": n,
            "has_outline": n in outline_nums,
            "has_content": n in content_nums,
            **meta,
        })

    return chapters


# ── 大纲读写 ────────────────────────────────────────────────────────────────

@router.get("/api/books/{book}/chapters/{n}/outline")
def get_outline(book: str, n: int):
    bd = _book_dir(book)
    bk = BookConfig(bd)
    path = bk.outline_path(n)
    if not path.exists():
        raise HTTPException(status_code=404, detail="outline not found")
    return {"chapter": n, "content": path.read_text(encoding="utf-8")}


@router.put("/api/books/{book}/chapters/{n}/outline")
def put_outline(book: str, n: int, payload: dict):
    bd = _book_dir(book)
    bk = BookConfig(bd)
    bk.outlines_dir.mkdir(parents=True, exist_ok=True)
    path = bk.outline_path(n)
    path.write_text(payload.get("content", ""), encoding="utf-8")
    return {"status": "ok"}


# ── 生成章节 (SSE) ─────────────────────────────────────────────────────────

@router.post("/api/books/{book}/chapters/{n}/generate")
async def generate_chapter_api(book: str, n: int):
    """生成单章，SSE 推送进度。"""
    bd = _book_dir(book)

    queue = asyncio.Queue()

    async def _run():
        from biyu.pipeline import generate_chapter

        def on_progress(stage: str, msg: str):
            queue.put_nowait(make_event("progress", chapter=n, stage=stage, message=msg))

        on_progress("start", f"开始生成第 {n} 章")
        try:
            result = await generate_chapter(bd, n)
            queue.put_nowait(make_event(
                "done", chapter=n, word_count=result.word_count,
                cost_cny=result.cost_cny, warnings=result.warnings,
            ))
        except Exception as e:
            queue.put_nowait(make_event("error", chapter=n, error=str(e)))
        finally:
            queue.put_nowait(None)

    asyncio.create_task(_run())
    return StreamingResponse(sse_generator(queue), media_type="text/event-stream")


# ── 正文 ─────────────────────────────────────────────────────────────────────

@router.get("/api/books/{book}/chapters/{n}/content")
def get_content(book: str, n: int):
    bd = _book_dir(book)
    bk = BookConfig(bd)
    path = bk.chapter_path(n)
    if not path.exists():
        raise HTTPException(status_code=404, detail="content not found")
    return {"chapter": n, "content": path.read_text(encoding="utf-8")}


# ── 一致性检查 ──────────────────────────────────────────────────────────────

@router.post("/api/books/{book}/chapters/{n}/check")
def check_chapter_api(book: str, n: int):
    bd = _book_dir(book)
    from biyu.db import init_db, sync_characters_from_yaml
    init_db(bd)
    sync_characters_from_yaml(bd)
    from biyu.consistency import check_chapter
    issues = check_chapter(bd, n)
    return {
        "chapter": n,
        "issues": [
            {"rule": i.rule, "severity": i.severity, "character": i.character,
             "location": i.location, "suggestion": i.suggestion}
            for i in issues
        ],
    }


# ── 刷新设定 ────────────────────────────────────────────────────────────────

@router.post("/api/books/{book}/chapters/{n}/refresh")
async def refresh_chapter_api(book: str, n: int):
    bd = _book_dir(book)
    from biyu.refresh import refresh_chapter
    from biyu.config import get_registry

    registry = get_registry()
    observer_alias = registry.get_pipeline_config().get("writer", "v3")
    adapter = registry.get_adapter_for_stage("writer", override=observer_alias)

    ok = refresh_chapter(bd, n, adapter)
    return {"chapter": n, "success": ok}


# ── 成本汇总 ────────────────────────────────────────────────────────────────

@router.get("/api/books/{book}/cost")
def get_cost(book: str):
    bd = _book_dir(book)
    bk = BookConfig(bd)
    cost_path = bk.cost_log_path
    if not cost_path.exists():
        return {"total": 0, "entries": []}

    import csv
    entries = []
    total = 0.0
    with open(cost_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cost = float(row.get("cost_cny", 0))
            total += cost
            entries.append(row)

    return {"total": round(total, 4), "entries": entries}


# ── 角色 yaml ───────────────────────────────────────────────────────────────

@router.get("/api/books/{book}/characters")
def get_characters(book: str):
    bd = _book_dir(book)
    chars = load_characters_yaml(bd)
    return {"characters": chars}


@router.put("/api/books/{book}/characters")
def put_characters(book: str, payload: dict):
    bd = _book_dir(book)
    yaml_path = bd / "characters.yaml"
    data = {"characters": payload.get("characters", [])}
    yaml_path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    # 重新同步 SQLite
    from biyu.db import init_db, sync_characters_from_yaml
    init_db(bd)
    sync_characters_from_yaml(bd)
    return {"status": "ok"}


# ── 真相文件 ────────────────────────────────────────────────────────────────

@router.get("/api/books/{book}/truth_files")
def get_truth_files(book: str):
    bd = _book_dir(book)
    return read_all_truth_files(bd)


# ── 批量生成 (SSE) ─────────────────────────────────────────────────────────

@router.post("/api/books/{book}/auto")
async def auto_generate_api(book: str, payload: dict):
    """批量生成，SSE 推送每章进度。"""
    bd = _book_dir(book)
    from_ch = payload.get("from")
    to_ch = payload.get("to")
    if from_ch is None or to_ch is None:
        raise HTTPException(status_code=400, detail="from and to are required")

    queue = asyncio.Queue()

    async def _run():
        from biyu.auto import auto_generate

        def on_progress(ch_num, done, result):
            queue.put_nowait(make_event(
                "chapter_done", chapter=ch_num, done=done,
                word_count=result.word_count, cost_cny=result.cost_cny,
            ))

        try:
            results = await auto_generate(bd, from_ch, to_ch, on_progress=on_progress)
            total_cost = sum(r.cost_cny for r in results)
            queue.put_nowait(make_event(
                "all_done", total=len(results), total_cost=total_cost,
            ))
        except Exception as e:
            queue.put_nowait(make_event("error", error=str(e)))
        finally:
            queue.put_nowait(None)

    asyncio.create_task(_run())
    return StreamingResponse(sse_generator(queue), media_type="text/event-stream")


# ── 回退 ─────────────────────────────────────────────────────────────────────

@router.post("/api/books/{book}/rollback")
def rollback_api(book: str, payload: dict):
    bd = _book_dir(book)
    to_ch = payload.get("to_chapter")
    if to_ch is None:
        raise HTTPException(status_code=400, detail="to_chapter is required")

    from biyu.refresh import rollback_to_chapter
    ok = rollback_to_chapter(bd, to_ch)
    return {"success": ok, "to_chapter": to_ch}
