#!/usr/bin/env bash
# 把 patches/ 下的补丁按序打到 OnePlus SM8475 源码树上
# 用法: ./scripts/apply-patches.sh /path/to/src
set -euo pipefail

SRC="${1:-.}"
PATCHES="$(cd "$(dirname "$0")/../patches" && pwd)"

if [ ! -d "$SRC/kernel_platform" ]; then
  echo "错误: $SRC 下没有 kernel_platform，确认路径" >&2
  exit 1
fi

shopt -s nullglob
for p in "$PATCHES"/*.patch; do
  echo "==> applying $(basename "$p")"
  git -C "$SRC" apply --check "$p"
  git -C "$SRC" apply "$p"
done

echo "==> 全部补丁已应用"
git -C "$SRC" --no-pager diff --stat
