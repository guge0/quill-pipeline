"""一次性脚本:对 ch1.md 跑 dash_fixer。

不重跑 Auditor、不重跑 Observer,只替换正文。
原始版本备份到 _archive_T-P3-A.1_round/ch1_pre_dashfix.md
"""
from pathlib import Path
from biyu.postproc.dash_fixer import fix_dashes

book_dir = Path("data/EXAMPLE_PROTAGONIST_T-P3-A验证")
ch1_path = book_dir / "chapters" / "ch1.md"
backup_path = book_dir / "_archive_T-P3-A.1_round" / "ch1_pre_dashfix.md"
backup_path.parent.mkdir(parents=True, exist_ok=True)

text = ch1_path.read_text(encoding="utf-8")
backup_path.write_text(text, encoding="utf-8")

result = fix_dashes(text)
ch1_path.write_text(result.fixed_text, encoding="utf-8")

print(f"ch1 破折号: {result.original_count} → {result.fixed_count}")
print(f"修复规则触发: {result.replacements}")
