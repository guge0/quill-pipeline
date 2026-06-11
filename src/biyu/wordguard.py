"""字数守门员 — CJK 字数下限检查与一次性续写。

铁律: 续写最多一次,不循环。
"""
from __future__ import annotations

from dataclasses import dataclass


def count_cjk_chars(text: str) -> int:
    """Count CJK Unified Ideographs in text."""
    return sum(1 for c in text if '\u4e00' <= c <= '\u9fff')


@dataclass
class WordGuardResult:
    """Result of word guard enforcement."""
    text: str
    word_count: int
    continued: bool = False
    continuation_word_count: int = 0
    warning: str = ""


async def enforce_floor(
    text: str,
    target: int,
    floor: int,
    continuation_fn,
) -> WordGuardResult:
    """Check if text meets the floor word count, request one continuation if not.

    Args:
        text: The current text.
        target: Target word count for the chapter.
        floor: Minimum acceptable word count.
        continuation_fn: Async callable(text, remaining_words) -> str|None
            Returns the continuation text, or None on failure.

    Returns:
        WordGuardResult with the final text and metadata.

    Rules:
        - text >= floor: return as-is, no intervention
        - text < floor: call continuation_fn ONCE, concatenate
        - continuation fails or still < floor: return with warning, NO retry
    """
    current_count = count_cjk_chars(text)

    if current_count >= floor:
        return WordGuardResult(text=text, word_count=current_count)

    remaining = target - current_count
    try:
        continuation = await continuation_fn(text, remaining)
    except Exception as e:
        return WordGuardResult(
            text=text,
            word_count=current_count,
            warning=f"续写异常: {e}",
        )

    if not continuation:
        return WordGuardResult(
            text=text,
            word_count=current_count,
            warning="续写返回空文本",
        )

    final_text = text + "\n\n" + continuation
    final_count = count_cjk_chars(final_text)
    cont_count = count_cjk_chars(continuation)

    warning = ""
    if final_count < floor:
        warning = (
            f"续写后仍不达标: {final_count} < {floor} "
            f"(续写 {cont_count} 字)"
        )

    return WordGuardResult(
        text=final_text,
        word_count=final_count,
        continued=True,
        continuation_word_count=cont_count,
        warning=warning,
    )
