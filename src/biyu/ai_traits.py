"""AI 痕迹机械度量引擎 — 纯确定性规则/正则, 零 LLM。

本模块提供一系列"机械式"痕迹度量, 全部基于纯文本规则(正则/字符统计/字数),
完全确定性, 相同输入必然产生相同输出。

**重要声明**: 所有度量均为"代理指标"(proxy), 仅反映文本的表面统计特征,
不能据此判断文本"是否为 AI 生成"或"是否为人类创作"。人类写手也可能产出高密度
感叹/破折号/长段落; AI 也可能输出短句少感叹。这些指标仅用于描述文本的机械特征,
供编辑参考。

阈值常量(来自 TL 要求):
- LONG_PARAGRAPH_CHARS = 150 (长段落阈值)
- LONG_SENTENCE_CHARS = 60 (长句阈值)
- PARALLEL_RANGE_CHARS = 3 (平行结构检测范围)
"""
from __future__ import annotations

import re
import statistics
from typing import Any


# ---------------------------------------------------------------------------
# 常量阈值
# ---------------------------------------------------------------------------
LONG_PARAGRAPH_CHARS = 150  # 长段落阈值(CJK 字符数)
LONG_SENTENCE_CHARS = 60  # 长句阈值(CJK 字符数)
PARALLEL_RANGE_CHARS = 3  # 平行结构检测范围


# ---------------------------------------------------------------------------
# 代理词列表 (Task 2 使用, Task 1 预定义)
# ---------------------------------------------------------------------------
MODIFIER_WORDS = frozenset([
    "冰冷", "滚烫", "苍白", "漆黑", "锋利", "沉重", "寂静", "刺耳",
    "模糊", "清晰", "剧烈", "微微", "缓缓", "静静", "默默", "淡淡",
    "幽幽", "冷冷", "森森", "凛冽", "刺骨", "空荡", "低沉", "尖锐",
    "湿润", "干燥", "浑浊", "清冽", "斑驳", "陡峭", "绵密",
])


# 常见四字成语/固定搭配(Task 2 使用, Task 1 预定义)
IDIOMS = frozenset([
    "不动声色", "若有所思", "意味深长", "不可名状", "悄无声息", "心不在焉",
    "了如指掌", "顺理成章", "心照不宣", "若有若无", "不疾不徐", "漫不经心",
    "心领神会", "不动声息", "似笑非笑", "隐隐约约", "清清楚楚", "明明白白",
    "整整齐齐", "干干净净",
])


# ---------------------------------------------------------------------------
# 正则表达式
# ---------------------------------------------------------------------------
_SENT_SPLIT = re.compile(r"[。！？!?…]+")
_EXCLAIM = re.compile(r"[！!]")
_DASH = re.compile(r"——|--|──|—{2,}|–{2,}")
_INTERNAL_PUNCT = "，,、；;：:·"
_FOUR_CJK = re.compile(r"[\u4e00-\u9fff]{4}")
_CJK = re.compile(r"[\u4e00-\u9fff]")


# ---------------------------------------------------------------------------
# 基础工具函数
# ---------------------------------------------------------------------------
def split_paragraphs(text: str) -> list[str]:
    """按空行分段, 去除空段落。

    Args:
        text: 输入文本

    Returns:
        段落列表(非空段落)
    """
    paragraphs = text.split("\n\n")
    return [p.strip() for p in paragraphs if p.strip()]


def split_sentences(text: str) -> list[str]:
    """按句末标点分句。

    Args:
        text: 输入文本

    Returns:
        句子列表(按 。！？!?… 分割)
    """
    if not text:
        return []
    sentences = _SENT_SPLIT.split(text)
    return [s.strip() for s in sentences if s.strip()]


def cjk_char_count(text: str) -> int:
    """统计 CJK 字符数。

    Args:
        text: 输入文本

    Returns:
        CJK 字符数(\\u4e00-\\u9fff)
    """
    return len(_CJK.findall(text))


def _per_1k(count: int, cjk: int) -> float:
    """计算每千字密度。

    Args:
        count: 某特征的出现次数
        cjk: 总 CJK 字符数

    Returns:
        每 1000 CJK 字符的密度, 如果 cjk<=0 返回 0.0
    """
    if cjk <= 0:
        return 0.0
    return (count / cjk) * 1000


# ---------------------------------------------------------------------------
# 段落长度度量 (Task 1)
# ---------------------------------------------------------------------------
def measure_paragraph_lengths(text: str) -> dict[str, Any]:
    """度量段落长度分布。

    Args:
        text: 输入文本

    Returns:
        dict with keys:
        - count: 段落总数
        - mean: 平均长度(CJK 字符数)
        - median: 中位数长度
        - max: 最长段落长度
        - long_para_ratio: 长段落比例(>LONG_PARAGRAPH_CHARS)
    """
    paragraphs = split_paragraphs(text)
    lengths = [cjk_char_count(p) for p in paragraphs]
    n = len(lengths)

    if n == 0:
        return {
            "count": 0,
            "mean": 0.0,
            "median": 0.0,
            "max": 0,
            "long_para_ratio": 0.0,
        }

    long_count = sum(1 for L in lengths if L > LONG_PARAGRAPH_CHARS)
    return {
        "count": n,
        "mean": statistics.mean(lengths),
        "median": statistics.median(lengths),
        "max": max(lengths),
        "long_para_ratio": long_count / n,
    }


# ---------------------------------------------------------------------------
# 感叹号密度 (Task 1)
# ---------------------------------------------------------------------------
def exclaim_density(text: str) -> float:
    """度量感叹号密度。

    Args:
        text: 输入文本

    Returns:
        每 1000 CJK 字符的感叹号密度(float)
    """
    count = len(_EXCLAIM.findall(text))
    cjk = cjk_char_count(text)
    return _per_1k(count, cjk)


# ---------------------------------------------------------------------------
# 破折号密度 (Task 1)
# ---------------------------------------------------------------------------
def dash_density(text: str) -> float:
    """度量破折号密度。

    Args:
        text: 输入文本

    Returns:
        每 1000 CJK 字符的破折号密度(float)
    """
    count = len(_DASH.findall(text))
    cjk = cjk_char_count(text)
    return _per_1k(count, cjk)


# ---------------------------------------------------------------------------
# Task 2 实现函数
# ---------------------------------------------------------------------------
def long_unpunct_sentence_ratio(text: str) -> float:
    """无内部标点的连续长句(> LONG_SENTENCE_CHARS CJK)占总句比(§3.1 超长句比例)。

    切句后,句内若不含任何内部标点(逗号/顿号/分号/冒号)且 CJK 字数 > 阈值 → 计入。
    """
    sents = split_sentences(text)
    n = len(sents)
    if n == 0:
        return 0.0
    hit = 0
    for s in sents:
        if any(ch in _INTERNAL_PUNCT for ch in s):
            continue
        if cjk_char_count(s) > LONG_SENTENCE_CHARS:
            hit += 1
    return hit / n


def modifier_proxy(text: str) -> dict[str, Any]:
    """描饰词密度代理(⚠ proxy,§3.1): 内置小词表 MODIFIER_WORDS 子串命中 / 千字。"""
    cjk = cjk_char_count(text)
    count = sum(text.count(w) for w in MODIFIER_WORDS)
    return {"count": count, "density_per_1k": _per_1k(count, cjk), "proxy": True}


def parallelism_proxy(text: str) -> dict[str, Any]:
    """对仗/排比代理(⚠ proxy,§3.2a):
    (a) uniform_run_ratio: 处于"连续 ≥3 句、字数极差 ≤ PARALLEL_RANGE_CHARS"整齐串中的句 / 总句
    (b) same_start_count: 连续句以同字开头的次数(≥2 连续才算)
    只算机械整齐度,不判"是不是好排比"。
    """
    sents = split_sentences(text)
    n = len(sents)
    if n < 3:
        return {"uniform_run_ratio": 0.0, "same_start_count": 0, "proxy": True}
    lengths = [cjk_char_count(s) for s in sents]
    in_run = [False] * n
    i = 0
    while i <= n - 3:
        window = lengths[i:i + 3]
        if max(window) - min(window) <= PARALLEL_RANGE_CHARS:
            in_run[i] = in_run[i + 1] = in_run[i + 2] = True
            j = i + 3
            while j < n and abs(lengths[j] - lengths[j - 1]) <= PARALLEL_RANGE_CHARS:
                in_run[j] = True
                j += 1
            i = j
        else:
            i += 1
    uniform_ratio = sum(1 for x in in_run if x) / n
    same_start = 0
    run_len = 1
    for k in range(1, n):
        if sents[k][:1] and sents[k][:1] == sents[k - 1][:1]:
            run_len += 1
        else:
            if run_len >= 2:
                same_start += run_len - 1
            run_len = 1
    if run_len >= 2:
        same_start += run_len - 1
    return {"uniform_run_ratio": uniform_ratio, "same_start_count": same_start,
            "proxy": True}


def four_char_proxy(text: str) -> dict[str, Any]:
    """四字格代理(⚠ proxy,§3.2 字数游戏):
    idiom_hits: 内置小成语表 IDIOMS 子串命中次数(每次出现计一次)
    raw_four_cjk_count: 任意连续 4 个 CJK 汉字原始匹配数(更粗,含非成语)
    idiom_density = idiom_hits / 千字。
    """
    cjk = cjk_char_count(text)
    idiom_hits = sum(text.count(idm) for idm in IDIOMS)
    raw = len(_FOUR_CJK.findall(text or ""))
    return {
        "idiom_hits": idiom_hits,
        "raw_four_cjk_count": raw,
        "idiom_density_per_1k": _per_1k(idiom_hits, cjk),
        "raw_density_per_1k": _per_1k(raw, cjk),
        "proxy": True,
    }


def number_rhythm_placeholder() -> dict[str, Any]:
    """数字节奏占位接口(§3.2)。

    v1 占位实现,未实现具体度量。待 TL 明确数字节奏定义后补充。

    Returns:
        dict with keys:
        - implemented: False (占位)
        - note: 说明文字
    """
    return {
        "implemented": False,
        "note": "v1 占位接口,未实现;待 TL 定节律口径后补",
    }


# ---------------------------------------------------------------------------
# 聚合度量函数 (Task 3, Task 1 提供基础实现)
# ---------------------------------------------------------------------------
def measure_all(text: str) -> dict[str, Any]:
    """运行所有 AI 痕迹度量, 返回聚合结果。

    完全确定性函数: 相同输入必然产生完全相同的输出(包括浮点数)。

    Args:
        text: 输入文本

    Returns:
        dict with keys:
        - char_count_cjk: CJK 字符总数
        - char_count_total: 总字符数(含标点/空格/字母)
        - paragraph_lengths: 段落长度度量(调用 measure_paragraph_lengths)
        - exclaim_density_per_1k: 感叹号密度(调用 exclaim_density)
        - dash_density_per_1k: 破折号密度(调用 dash_density)
        - long_unpunct_sentence_ratio: 长无标句比例(Task 2)
        - modifier_proxy: 修饰词代理(Task 2)
        - parallelism_proxy: 平行结构代理(Task 3)
        - four_char_proxy: 四字成语代理(Task 2)
        - number_rhythm: 数字节奏占位(Task 3)
        - degenerate: 是否退化输入(cjk==0)
        - notes: 说明文字(免责声明)
    """
    cjk = cjk_char_count(text)
    total = len(text)

    # 调用各个度量函数
    para_lengths = measure_paragraph_lengths(text)
    exclaim_density_per_1k = exclaim_density(text)
    dash_density_per_1k = dash_density(text)

    # Stub 函数(Task 2/3 实现)
    long_unpunct = long_unpunct_sentence_ratio(text)
    modifier = modifier_proxy(text)
    parallelism = parallelism_proxy(text)
    four_char = four_char_proxy(text)
    number_rhythm = number_rhythm_placeholder()

    return {
        "char_count_cjk": cjk,
        "char_count_total": total,
        "paragraph_lengths": para_lengths,
        "exclaim_density_per_1k": exclaim_density_per_1k,
        "dash_density_per_1k": dash_density_per_1k,
        "long_unpunct_sentence_ratio": long_unpunct,
        "modifier_proxy": modifier,
        "parallelism_proxy": parallelism,
        "four_char_proxy": four_char,
        "number_rhythm": number_rhythm,
        "degenerate": cjk == 0,
        "notes": "AI痕迹机械度量: 全部为代理指标, 不代表人类/AI判定, 仅供参考。",
    }
