"""biyu configuration and book directory utilities."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from biyu.llm import ModelRegistry


def get_project_root() -> Path:
    """Return the biyu project root directory."""
    return Path(__file__).resolve().parents[2]


def get_config_path() -> Path:
    """Return path to models.yaml."""
    return get_project_root() / "config" / "models.yaml"


def get_data_root() -> Path:
    """Return the data directory root."""
    return get_project_root() / "data"


def get_registry() -> ModelRegistry:
    """Create a ModelRegistry from the default config."""
    return ModelRegistry(get_config_path())


class BookConfig:
    """Represents a single book's configuration and directory structure."""

    def __init__(self, book_dir: Path):
        self.book_dir = book_dir
        self._meta: dict[str, Any] | None = None

    @property
    def meta_path(self) -> Path:
        return self.book_dir / "book.json"

    @property
    def characters_path(self) -> Path:
        return self.book_dir / "characters.yaml"

    @property
    def outlines_dir(self) -> Path:
        return self.book_dir / "outlines"

    @property
    def chapters_dir(self) -> Path:
        return self.book_dir / "chapters"

    @property
    def logs_dir(self) -> Path:
        return self.book_dir / "logs"

    @property
    def cost_log_path(self) -> Path:
        return self.logs_dir / "cost_log.csv"

    def outline_path(self, chapter_num: int) -> Path:
        return self.outlines_dir / f"ch{chapter_num}.md"

    def chapter_path(self, chapter_num: int) -> Path:
        return self.chapters_dir / f"ch{chapter_num}.md"

    def chapter_log_dir(self, chapter_num: int) -> Path:
        d = self.logs_dir / f"ch{chapter_num}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def load_meta(self) -> dict[str, Any]:
        if self._meta is not None:
            return self._meta
        with open(self.meta_path, encoding="utf-8") as f:
            self._meta = json.load(f)
        return self._meta

    def save_meta(self, meta: dict[str, Any]) -> None:
        self._meta = meta
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    @property
    def title(self) -> str:
        return self.load_meta().get("title", "")

    @property
    def genre(self) -> str:
        return self.load_meta().get("genre", "")

    @property
    def chapter_target_words(self) -> int:
        return self.load_meta().get("chapter_target_words", 5000)

    @property
    def chapter_min_words(self) -> int:
        return self.load_meta().get("chapter_min_words", 4250)


def load_characters_yaml(book_dir: Path) -> list[dict[str, Any]]:
    """Load characters from characters.yaml.

    Returns:
        List of character dicts with all fields from yaml.
    """
    yaml_path = book_dir / "characters.yaml"
    if not yaml_path.exists():
        return []
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("characters", [])


def resolve_book_dir(book: str | None = None) -> Path:
    """Resolve a book name to its directory path.

    If book is None, auto-detect the only book in data/.
    """
    data_root = get_data_root()
    if book:
        book_dir = data_root / book
    else:
        books = [d for d in data_root.iterdir()
                 if d.is_dir() and (d / "book.json").exists()]
        if len(books) == 0:
            raise FileNotFoundError("No books found in data/. Run `biyu init` first.")
        if len(books) > 1:
            raise ValueError(
                f"Multiple books found: {[b.name for b in books]}. "
                "Specify --book."
            )
        book_dir = books[0]
    if not book_dir.exists():
        raise FileNotFoundError(f"Book directory not found: {book_dir}")
    if not (book_dir / "book.json").exists():
        raise FileNotFoundError(f"No book.json in {book_dir}")
    return book_dir
