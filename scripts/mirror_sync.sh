#!/usr/bin/env bash
# mirror_sync.sh — 白名单制同步脚本 (P6-13-D54 加固版)
# 用法: bash scripts/mirror_sync.sh <主仓路径> <镜像仓路径>
# 只搬白名单内容,其余一律不搬。镜像仓无历史,一次性快照。
#
# 加固 (D-54): 推前硬闸
#   - 命中 FORBIDDEN_PATTERNS → 拒推并报错
#   - 文件数 > MAX_FILES 或总体积 > MAX_SIZE_KB → 拒推并报错
#   - git diff --cached 检查,在任何 commit 前拦截
set -euo pipefail

MAIN="${1:?用法: mirror_sync.sh <主仓路径> <镜像仓路径>}"
MIRROR="${2:?用法: mirror_sync.sh <主仓路径> <镜像仓路径>}"

echo "=== mirror_sync.sh (D-54 加固版) ==="
echo "主仓: $MAIN"
echo "镜像: $MIRROR"

# ---------- 白名单定义 ----------
SYNC_DIRS=("src")
SYNC_PROMPTS=("prompts")
SYNC_TOOLS=("tools")
SYNC_SCRIPTS=("scripts")
SYNC_EVAL=("eval_set_v0")
SYNC_ROOT_FILES=("pyproject.toml")
SYNC_TESTS=("tests")

CONFIG_YAMLS=(
    "config/auditor.yaml"
    "config/default.yaml"
    "config/editor.yaml"
    "config/models.yaml.example"
)

# ---------- 推前硬闸: 禁止路径模式 ----------
# 注意: eval_set_v0/ 是公开测试集(EV1 回声巷),允许包含
# worldbook/characters/truth_files 等。禁止模式排除 eval_set_v0/。
FORBIDDEN_PATTERNS=(
    "data/"
    "outputs/"
    "sub_md/"
    ".env"
    "models.yaml"
    "secrets"
)

# eval_set_v0 外部的禁止文件名 (书内容泄漏)
FORBIDDEN_FILENAMES_OUTSIDE_EVAL=(
    "worldbook.yaml"
    "characters.yaml"
    "truth_files/"
    "chapters/"
    "book.db"
    "book.json"
    "polished.md"
    "skeleton.md"
    "skeleton_raw.md"
    "skeleton_dashfixed.md"
)

# 硬闸阈值
MAX_FILES=500
MAX_SIZE_KB=16384  # 16MB (eval_set_v0 含 .db 章节占 ~10MB)

# ---------- 黑名单 .gitignore 内容 ----------
GITIGNORE_CONTENT='# === 黑名单 (02_开源镜像规范 §3) ===
# 真实 key / token / .env
.env
.env.*
*.key
*.pem
**/secrets.*

# 现书全部产出
data/
outputs/

# docs 与报表
docs/

# 个人信息
*.lnk
*.zip

# 本机路径配置 (只用 .example)
config/models.yaml
config/*.yaml
!config/*.yaml.example

# Python 缓存
__pycache__/
*.pyc
*.pyo
.venv/

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db
'

# ---------- 开始同步 ----------
echo "[1/8] 清空镜像工作区..."
cd "$MIRROR"
find . -maxdepth 1 ! -name '.' ! -name '.git' -exec rm -rf {} + 2>/dev/null || true
cd "$MAIN"

echo "[2/8] 同步 src/ (管线源代码)..."
cp -r "$MAIN/src/" "$MIRROR/src/"

echo "[3/8] 同步 prompts/ ..."
if [ -d "$MAIN/prompts" ]; then
    cp -r "$MAIN/prompts/" "$MIRROR/prompts/"
fi

echo "[4/8] 同步 tools/ ..."
if [ -d "$MAIN/tools" ]; then
    cp -r "$MAIN/tools/" "$MIRROR/tools/"
fi

echo "[5/8] 同步 scripts/ (含本脚本)..."
cp -r "$MAIN/scripts/" "$MIRROR/scripts/"

echo "[6/8] 同步 eval_set_v0/ (评估测试集)..."
if [ -d "$MAIN/eval_set_v0" ]; then
    cp -r "$MAIN/eval_set_v0/" "$MIRROR/eval_set_v0/"
    echo "  eval_set_v0/ 已同步"
else
    echo "  eval_set_v0/ 不存在,跳过"
fi

echo "[7/8] 同步 tests/ ..."
cp -r "$MAIN/tests/" "$MIRROR/tests/"

echo "[8/8] 同步根文件 + 配置模板..."
for f in "${SYNC_ROOT_FILES[@]}"; do
    if [ -f "$MAIN/$f" ]; then
        cp "$MAIN/$f" "$MIRROR/$f"
    fi
done

# 配置模板化
mkdir -p "$MIRROR/config"
for yaml in "${CONFIG_YAMLS[@]}"; do
    if [ -f "$MAIN/$yaml" ]; then
        if [[ "$yaml" == *.example ]]; then
            cp "$MAIN/$yaml" "$MIRROR/$yaml"
        else
            dest="$MIRROR/${yaml}.example"
            cp "$MAIN/$yaml" "$dest"
            sed -i 's/api_key:.*/api_key: "YOUR_API_KEY"/g' "$dest" 2>/dev/null || \
                sed -i '' 's/api_key:.*/api_key: "YOUR_API_KEY"/g' "$dest"
            sed -i 's|/[A-Za-z]:/[^ "]*|YOUR_PATH|g; s|/home/[^ "]*|YOUR_PATH|g; s|/Users/[^ "]*|YOUR_PATH|g' "$dest" 2>/dev/null || true
        fi
    fi
done

# 写入 .gitignore
echo "$GITIGNORE_CONTENT" > "$MIRROR/.gitignore"

# 清理构建产物与 Python 缓存
find "$MIRROR" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
find "$MIRROR" -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true

# ---------- 推前硬闸检查 ----------
echo ""
echo "=== 推前硬闸检查 ==="
cd "$MIRROR"

VIOLATIONS=()

# 层 1: 绝对禁止路径 (data/, outputs/, sub_md/ 等)
for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
    matches=$(find . -path "./$pattern" -o -path "./*/$pattern" 2>/dev/null | head -5 || true)
    if [ -n "$matches" ]; then
        VIOLATIONS+=("FORBIDDEN: $pattern → $matches")
    fi
done

# 层 2: eval_set_v0/ 外的书内容文件
for pattern in "${FORBIDDEN_FILENAMES_OUTSIDE_EVAL[@]}"; do
    # 只检查不在 eval_set_v0/ 下的匹配
    matches=$(find . -not -path './eval_set_v0/*' -not -path './.git/*' \
              \( -name "$pattern" -o -path "*/$pattern" \) 2>/dev/null | head -5 || true)
    if [ -n "$matches" ]; then
        VIOLATIONS+=("FORBIDDEN (outside eval): $pattern → $matches")
    fi
done

FILE_COUNT=$(find . -not -path './.git/*' -type f 2>/dev/null | wc -l || echo 0)
TOTAL_KB=$(du -sk --exclude='.git' . 2>/dev/null | cut -f1 || du -sk . 2>/dev/null | cut -f1)

echo "文件数: $FILE_COUNT (上限 $MAX_FILES)"
echo "总体积: ${TOTAL_KB}KB (上限 ${MAX_SIZE_KB}KB)"

if [ ${#VIOLATIONS[@]} -gt 0 ]; then
    echo ""
    echo "❌ 硬闸失败 — 命中禁止路径:"
    for v in "${VIOLATIONS[@]}"; do
        echo "  $v"
    done
    echo ""
    echo "拒推。请检查同步内容。"
    exit 1
fi

if [ "$FILE_COUNT" -gt "$MAX_FILES" ]; then
    echo "❌ 硬闸失败 — 文件数 $FILE_COUNT > 上限 $MAX_FILES"
    exit 1
fi

if [ "$TOTAL_KB" -gt "$MAX_SIZE_KB" ]; then
    echo "❌ 硬闸失败 — 体积 ${TOTAL_KB}KB > 上限 ${MAX_SIZE_KB}KB"
    exit 1
fi

echo "✅ 硬闸通过"
echo "=== 同步完成 ==="
echo "镜像文件列表:"
find . -not -path './.git/*' -type f | sort
