"""一次性脚本:扫描并修复 ch1-6 中 wenyan_fixer 引入的字符 bug。

修复:
1. "已经经" → "已经"
2. "他/她" → "他"(评审说读者读不懂,直接选"他",这是工程妥协)
3. "她/他" → "她"(同上)

每个文件备份到 _archive_T-P3-B.1_round/
"""
from pathlib import Path

book_dir = Path("data/EXAMPLE_PROTAGONIST_T-P3-A验证")
backup_dir = book_dir / "_archive_T-P3-B.1_round"
backup_dir.mkdir(parents=True, exist_ok=True)

REPLACEMENTS = {
    "已经经": "已经",
    "他/她": "他",
    "她/他": "她",
}

for ch_path in sorted((book_dir / "chapters").glob("ch*.md")):
    text = ch_path.read_text(encoding="utf-8")
    backup_path = backup_dir / ch_path.name
    backup_path.write_text(text, encoding="utf-8")

    fixed = text
    fix_log = []
    for bad, good in REPLACEMENTS.items():
        if bad in fixed:
            count = fixed.count(bad)
            fixed = fixed.replace(bad, good)
            fix_log.append(f"  {bad} → {good} ({count}x)")

    if fix_log:
        ch_path.write_text(fixed, encoding="utf-8")
        print(f"{ch_path.name}: 已修复")
        for line in fix_log:
            print(line)
    else:
        print(f"{ch_path.name}: 无需修复")
