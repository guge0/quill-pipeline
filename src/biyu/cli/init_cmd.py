"""biyu init — create a new book directory structure."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import typer
import yaml
from rich.console import Console

console = Console()


def init_command(
    title: str = typer.Option(..., "--title", "-t", help="书名"),
    genre: str = typer.Option(..., "--genre", "-g", help="题材 (xuanhuan/dushi/kehuan)"),
) -> None:
    """初始化一本新书。"""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from biyu.config import get_data_root

    data_root = get_data_root()
    book_dir = data_root / title

    if book_dir.exists():
        console.print(f"[red]目录已存在: {book_dir}[/red]")
        raise typer.Exit(1)

    # Create directory structure
    book_dir.mkdir(parents=True)
    (book_dir / "outlines").mkdir()
    (book_dir / "chapters").mkdir()
    (book_dir / "logs").mkdir()

    # Truth files (设定三件套)
    from biyu.truth_files import init_truth_files
    init_truth_files(book_dir)

    # book.json
    meta = {
        "title": title,
        "genre": genre,
        "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "biyu_version": "phase1-0.1",
        "chapter_target_words": 5000,
        "chapter_min_words": 4250,
        "context_mode": "long_context",
    }
    (book_dir / "book.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # characters.yaml
    characters = {
        "characters": [
            {
                "name": "主角姓名",
                "role": "protagonist",
                "status": "alive",
                "personality": "",
                "speaking_style": "",
                "background": "",
                "abilities": "",
                "current_location": "",
                "current_power_level": "",
                "current_emotional_state": "",
                "sample_lines": ["", "", ""],
            },
            {
                "name": "配角1",
                "role": "major",
                "status": "alive",
                "personality": "",
                "speaking_style": "",
                "background": "",
                "abilities": "",
                "current_location": "",
                "current_power_level": "",
                "current_emotional_state": "",
                "sample_lines": ["", "", ""],
            },
            {
                "name": "配角2",
                "role": "minor",
                "status": "alive",
                "personality": "",
                "speaking_style": "",
                "background": "",
                "abilities": "",
                "current_location": "",
                "current_power_level": "",
                "current_emotional_state": "",
                "sample_lines": ["", "", ""],
            },
        ]
    }
    (book_dir / "characters.yaml").write_text(
        yaml.dump(characters, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )

    console.print(f"[green]书 '{title}' 初始化完成[/green]")
    console.print(f"  目录: {book_dir}")
    console.print(f"  题材: {genre}")
    console.print(f"  目标字数: 5000/章 (下限 4250)")

    # Initialize SQLite
    from biyu.db import init_db
    db_path = init_db(book_dir)
    console.print(f"  数据库: {db_path}")

    console.print(f"\n  下一步: 编辑 {book_dir / 'outlines' / 'ch1.md'} 写大纲, 然后 biyu write --chapter 1")
