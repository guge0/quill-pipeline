# Prompts 变更日志

## T-P3-A (2026-05-01)

### 新增: STYLE_BLACKLIST 句式级黑名单
- **文件**: `src/biyu/prompts/v3_opening.py`
- **变更**: 新增 `STYLE_BLACKLIST` 常量（21 条高频 AI 句式模板）
- **注入位置**: `build_planning_prompt` (Architect) + `build_writer_user_prompt` (Writer)
- **原因**: 30 章评审反馈硬伤之一——AI 味浓，大量重复使用"不是X而是Y""仿佛..."等句式

### 新增: worldbook prompt 注入
- **文件**: `src/biyu/worldbook.py` (新建)
- **注入位置**: Architect prompt 顶部（worldbook 覆盖其他注入）+ Writer prompt 顶部
- **原因**: 角色名字漂移（秦烈→EXAMPLE_ALLY）、修炼体系/数字设定不一致

### 新增: 衔接锚点（上一章末尾注入）
- **文件**: `src/biyu/pipeline.py` (`_load_prev_chapter_tail`)
- **注入位置**: Writer prompt 中 `<上一章末尾>` 标签
- **原因**: 章节衔接断裂、角色蒸发

### 新增: 在场角色锁
- **文件**: `src/biyu/pipeline.py` (`_parse_present_characters`)
- **注入位置**: Writer prompt 中 `<在场角色>` 标签
- **原因**: 章节衔接断裂时角色蒸发，无名角色突然出现

### 新增: 章节号自动修正
- **文件**: `src/biyu/pipeline.py` (`_fix_chapter_number`)
- **位置**: Writer 输出后、WordGuard 前
- **原因**: 章节号 vs 文件名不一致

### build_writer_user_prompt 新增参数
- `worldbook_prompt: str` — worldbook 注入字符串
- `prev_tail: str` — 上一章末尾 500 字
- `present_characters: list[str]` — 在场角色列表
