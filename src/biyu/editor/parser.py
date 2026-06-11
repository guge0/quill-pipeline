"""解析 Editor LLM 返回的 JSON — 含幻觉校验。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

VALID_TYPES = {"字面伪影", "视角穿帮", "跨章一致性", "逻辑漏洞", "人设守恒"}
VALID_SUBTYPES = {"主角戏份", "维基百科化", "符号过度", "语气漂移", None}
VALID_SEVERITIES = {"high", "medium", "low"}

# Suggestions that indicate no real guidance was given
_VAGUE_SUGGESTIONS = {"manual_review", "需要修改", "建议调整", "请检查", "需修改", "建议修改"}


@dataclass
class EditorIssue:
    """Editor 标出的一条问题。"""
    line: int
    quote: str
    type: str
    subtype: str | None
    explanation: str
    fix_suggestion: str
    auto_fixable: bool
    severity: str = "medium"
    quoted_text: str = ""  # 问题段落原文片段，用于 Reviser 定位
    hallucination_filtered: bool = False  # 是否因幻觉被过滤

    def to_dict(self) -> dict:
        d = {
            "line": self.line,
            "quote": self.quote,
            "quoted_text": self.quoted_text,
            "type": self.type,
            "explanation": self.explanation,
            "fix_suggestion": self.fix_suggestion,
            "auto_fixable": self.auto_fixable,
            "severity": self.severity,
        }
        if self.subtype:
            d["subtype"] = self.subtype
        return d


@dataclass
class EditorResult:
    """Editor 审稿结果。"""
    issues: list[EditorIssue] = field(default_factory=list)
    queries_used: list[str] = field(default_factory=list)
    confidence: str = "medium"
    raw_response: str = ""
    parse_errors: list[str] = field(default_factory=list)
    cost: float = 0.0

    @property
    def auto_fixable_issues(self) -> list[EditorIssue]:
        return [i for i in self.issues if i.auto_fixable]

    @property
    def manual_review_issues(self) -> list[EditorIssue]:
        return [i for i in self.issues if not i.auto_fixable]

    def to_dict(self) -> dict:
        return {
            "issues": [i.to_dict() for i in self.issues],
            "queries_used": self.queries_used,
            "confidence": self.confidence,
        }


def parse_editor_response(raw_text: str, chapter_text: str) -> EditorResult:
    """解析 Editor LLM 的返回文本。

    1. 提取 JSON（支持被 ```json ... ``` 包裹的情况）
    2. 校验每个 issue 的 quote 在原文中存在（防幻觉）
    3. 校验 type 是 5 类之一
    4. 校验只有字面伪影类 auto_fixable=true

    Args:
        raw_text: LLM 返回的原始文本。
        chapter_text: 原始章节文本（用于 quote 校验）。

    Returns:
        EditorResult
    """
    result = EditorResult(raw_response=raw_text)

    # 1. 提取 JSON
    json_str = _extract_json(raw_text)
    if not json_str:
        result.parse_errors.append("无法从 Editor 返回中提取 JSON")
        return result

    # 2. 尝试直接解析
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        result.parse_errors.append(f"JSON 解析失败: {e}")
        return result

    # 2. 解析 issues
    raw_issues = data.get("issues", [])
    if not isinstance(raw_issues, list):
        result.parse_errors.append("issues 不是列表")
        return result

    for raw in raw_issues:
        if not isinstance(raw, dict):
            continue

        issue = _parse_single_issue(raw)
        if issue is None:
            continue

        # 幻觉校验：quote 必须在原文中
        if issue.quote and issue.quote not in chapter_text:
            # 尝试模糊匹配（允许少许偏差）
            if not _fuzzy_quote_match(issue.quote, chapter_text):
                issue.hallucination_filtered = True
                result.parse_errors.append(
                    f"幻觉过滤: type={issue.type}, quote='{issue.quote[:30]}...' 不在原文中"
                )
                continue

        # type 校验
        if issue.type not in VALID_TYPES:
            result.parse_errors.append(f"未知 type: {issue.type}")
            continue

        # auto_fixable 校验：只有字面伪影类可以为 true
        if issue.auto_fixable and issue.type != "字面伪影":
            issue.auto_fixable = False

        # suggestion 质量检查：非字面伪影类的 fix_suggestion 不应是空话
        if issue.type != "字面伪影":
            suggestion = issue.fix_suggestion.strip()
            if suggestion in _VAGUE_SUGGESTIONS or len(suggestion) < 10:
                result.parse_errors.append(
                    f"suggestion 质量不足: type={issue.type}, "
                    f"fix_suggestion='{suggestion[:30]}'"
                )

        result.issues.append(issue)

    # 3. 限制最多 8 个 issue
    if len(result.issues) > 8:
        result.issues = result.issues[:8]

    # 4. 其他字段
    result.queries_used = data.get("queries_used", [])
    result.confidence = data.get("confidence", "medium")

    return result


def _extract_json(text: str) -> str | None:
    """从 LLM 返回中提取 JSON 字符串。"""
    # 尝试直接解析
    text = text.strip()
    if text.startswith("{"):
        return text

    # 尝试提取 ```json ... ``` 包裹
    m = re.search(r'```(?:json)?\s*(\{.*\})\s*```', text, re.DOTALL)
    if m:
        return m.group(1)

    # 尝试找第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start:end + 1]

    return None


def _parse_single_issue(raw: dict) -> EditorIssue | None:
    """解析单个 issue dict。"""
    try:
        severity = str(raw.get("severity", "medium"))
        if severity not in VALID_SEVERITIES:
            severity = "medium"
        return EditorIssue(
            line=int(raw.get("line", 0)),
            quote=str(raw.get("quote", "")),
            type=str(raw.get("type", "")),
            subtype=raw.get("subtype"),
            explanation=str(raw.get("explanation", "")),
            fix_suggestion=str(raw.get("fix_suggestion", "manual_review")),
            auto_fixable=bool(raw.get("auto_fixable", False)),
            severity=severity,
            quoted_text=str(raw.get("quoted_text", "")),
        )
    except (ValueError, TypeError):
        return None


def _fuzzy_quote_match(quote: str, text: str) -> bool:
    """模糊匹配：允许 quote 中有少许标点差异。

    特别处理：JSON 修复会将 ASCII " 替换为中文引号，所以匹配时统一去除
    ASCII 引号和中文引号。
    """
    # 去除标点后比较（含 ASCII " 和中文引号 \u201c\u201d）
    strip_chars = r'[，。！？、；：\u201c\u201d\u2018\u2019\u0022\u0027（）\s]'
    clean_quote = re.sub(strip_chars, '', quote)
    clean_text = re.sub(strip_chars, '', text)
    return clean_quote in clean_text
