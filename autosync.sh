#!/usr/bin/env bash
# ============================================================================
# 每日自动备份：把本项目的改动提交并推送到 GitHub
#
# 设计三原则：
#   1. 幂等    —— 没有改动就静默退出，绝不产生空提交
#   2. 不交互  —— 凭证失效时立即失败，不会挂在那里等密码输入
#   3. 有护栏  —— 大文件 / 海量文件直接中止，避免把视频误传上仓库
#
# 退出码：0 = 成功或无改动   1 = 失败（原因见输出）
# ============================================================================
set -u
cd "$(dirname "$0")" || exit 1

BRANCH="main"
LIMIT_MB=50        # 单个文件上限
LIMIT_FILES=200    # 单次改动文件数上限

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1"; }

# ---------- 0. 环境检查 ----------
command -v git >/dev/null 2>&1 || { log "失败：找不到 git"; exit 1; }
[ -d .git ] || { log "失败：当前目录不是 git 仓库"; exit 1; }

# 关键：禁止 git 弹交互式密码框，否则定时任务会永久挂起
export GIT_TERMINAL_PROMPT=0

# ---------- 1. 有没有改动 ----------
git add -A 2>/dev/null
if git diff --cached --quiet; then
    log "没有改动，跳过"
    exit 0
fi

COUNT=$(git diff --cached --name-only | wc -l | tr -d ' ')

# ---------- 2. 护栏 ----------
if [ "$COUNT" -gt "$LIMIT_FILES" ]; then
    log "中止：本次改动 $COUNT 个文件（上限 $LIMIT_FILES），可能有整目录被误放入"
    git reset -q
    exit 1
fi

BIG=$(git diff --cached --name-only -z | while IFS= read -r -d '' f; do
        [ -f "$f" ] || continue
        SZ=$(wc -c < "$f" 2>/dev/null | tr -d ' ')
        if [ "${SZ:-0}" -gt $((LIMIT_MB * 1024 * 1024)) ]; then
            echo "    $f  ($((SZ / 1024 / 1024))MB)"
        fi
      done)

if [ -n "$BIG" ]; then
    log "中止：以下文件超过 ${LIMIT_MB}MB，不该进仓库："
    echo "$BIG"
    git reset -q
    exit 1
fi

# ---------- 3. 提交 ----------
MSG="chore: 每日自动备份 $(date '+%Y-%m-%d %H:%M')"
if ! git commit -q -m "$MSG"; then
    log "失败：git commit 出错"
    exit 1
fi
SHA=$(git rev-parse --short HEAD)
log "已提交 $SHA（$COUNT 个文件）"

# ---------- 4. 推送 ----------
if OUT=$(git push origin "$BRANCH" 2>&1); then
    log "已推送 $SHA -> origin/$BRANCH"
    exit 0
else
    log "推送失败（提交 $SHA 已安全保存在本地，下次会一起推上去）"
    printf '%s\n' "$OUT" | tail -5
    exit 1
fi
