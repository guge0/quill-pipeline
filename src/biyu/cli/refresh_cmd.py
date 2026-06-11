"""biyu refresh / rollback — 改稿同步命令。"""
from __future__ import annotations

import sys

import typer
from rich.console import Console

console = Console()


def refresh_command(
    chapter: int = typer.Option(None, "--chapter", "-c", help="单章刷新"),
    from_ch: int = typer.Option(None, "--from", help="起始章节(范围刷新)"),
    to_ch: int = typer.Option(None, "--to", help="结束章节(范围刷新)"),
    book: str = typer.Option(None, "--book", "-b", help="书名(省略则自动检测)"),
) -> None:
    """重跑 Observer 刷新设定文件。支持 --chapter N 或 --from X --to Y。"""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from biyu.config import resolve_book_dir
    from biyu.refresh import refresh_chapter, refresh_range

    try:
        book_dir = resolve_book_dir(book)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if chapter is not None:
        ok = refresh_chapter(book_dir, chapter)
        if ok:
            console.print(f"[green]ch{chapter} 刷新成功[/green]")
        else:
            console.print(f"[red]ch{chapter} 刷新失败[/red]")
            raise typer.Exit(1)
    elif from_ch is not None and to_ch is not None:
        results = refresh_range(book_dir, from_ch, to_ch)
        success = sum(1 for _, ok in results if ok)
        console.print(f"[green]{success}/{len(results)} 章刷新成功[/green]")
    else:
        console.print("[red]请指定 --chapter N 或 --from X --to Y[/red]")
        raise typer.Exit(1)


def rollback_command(
    to_chapter: int = typer.Option(..., "--to-chapter", "-t", help="回退到的目标章节号"),
    book: str = typer.Option(None, "--book", "-b", help="书名(省略则自动检测)"),
) -> None:
    """回退 truth_files 到指定章节的历史状态，并归档后续章节。"""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from biyu.config import resolve_book_dir
    from biyu.refresh import rollback_to_chapter

    try:
        book_dir = resolve_book_dir(book)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    ok = rollback_to_chapter(book_dir, to_chapter)
    if ok:
        console.print(f"[green]已回退到 ch{to_chapter} 状态[/green]")
    else:
        console.print(f"[red]回退失败[/red]")
        raise typer.Exit(1)
