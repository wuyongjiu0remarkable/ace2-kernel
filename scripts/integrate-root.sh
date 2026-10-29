#!/usr/bin/env bash
# 在 GKI 源码树里集成 KernelSU-Next（+ 可选 SUSFS）
#
# 做法对照上游 KernelSU-Next/kernel/setup.sh（已核对源码）：
#   1) 把仓库克隆到 $GKI_ROOT/KernelSU-Next
#   2) ln -s KernelSU-Next/kernel -> drivers/kernelsu
#   3) drivers/Makefile 追加 obj-$(CONFIG_KSU) += kernelsu/
#   4) drivers/Kconfig endmenu 前插入 source "drivers/kernelsu/Kconfig"
# 区别：上游脚本内含 git pull / git stash，在浅克隆 + tag 场景会因 set -e 中断，
#       这里直接做等价改动，网络依赖更少、可重复执行。
#
# 用法: ./scripts/integrate-root.sh <gki_kernel_dir> [--no-susfs]
set -euo pipefail

SRC="${1:?用法: integrate-root.sh <gki_kernel_dir> [--no-susfs]}"
NO_SUSFS=0
[ "${2:-}" = "--no-susfs" ] && NO_SUSFS=1

KSU_REPO="${KSU_REPO:-https://github.com/KernelSU-Next/KernelSU-Next.git}"
KSU_REF="${KSU_REF:-v1.0.5}"
SUSFS_REPO="${SUSFS_REPO:-https://github.com/ShirkNeko/susfs4ksu.git}"
SUSFS_REF="${SUSFS_REF:-master}"

cd "$SRC"
[ -d drivers ] || { echo "错误: $SRC 下没有 drivers/，不是内核源码根目录" >&2; exit 1; }

echo "==> [1/4] KernelSU-Next @ $KSU_REF"
rm -rf KernelSU-Next
git clone --depth 1 -b "$KSU_REF" "$KSU_REPO" KernelSU-Next \
  || git clone --depth 1 "$KSU_REPO" KernelSU-Next
[ -d KernelSU-Next/kernel ] || { echo "克隆结果里没有 kernel/ 目录" >&2; exit 1; }

echo "==> [2/4] 接入 drivers/"
ln -sfn "$SRC/KernelSU-Next/kernel" drivers/kernelsu
grep -q 'kernelsu' drivers/Makefile || echo 'obj-$(CONFIG_KSU) += kernelsu/' >> drivers/Makefile
grep -q 'drivers/kernelsu/Kconfig' drivers/Kconfig \
  || sed -i '/^endmenu/i source "drivers/kernelsu/Kconfig"' drivers/Kconfig
echo "  drivers/kernelsu -> $(readlink drivers/kernelsu)"

if [ "$NO_SUSFS" -eq 0 ]; then
  echo "==> [3/4] SUSFS @ $SUSFS_REF"
  TMP="$(mktemp -d)"
  git clone --depth 1 -b "$SUSFS_REF" "$SUSFS_REPO" "$TMP/susfs"
  PATCHES="$(find "$TMP/susfs" -name '*.patch' | grep -E '50_add_susfs|susfs' | head -5 || true)"
  [ -n "$PATCHES" ] || { echo "SUSFS 仓库里没找到补丁，检查 SUSFS_REF=$SUSFS_REF" >&2; exit 1; }
  for p in $PATCHES; do
    echo "  applying $(basename "$p")"
    patch -p1 --forward < "$p" || echo "  跳过（可能已应用）"
  done
  rm -rf "$TMP"
else
  echo "==> [3/4] 跳过 SUSFS"
fi

echo "==> [4/4] 打开配置"
CFG=arch/arm64/configs/gki_defconfig
[ -f "$CFG" ] || CFG="$(ls arch/arm64/configs/*defconfig 2>/dev/null | head -1)"
[ -n "$CFG" ] || { echo "找不到 defconfig" >&2; exit 1; }
for opt in CONFIG_KSU=y CONFIG_KSU_SUSFS=y CONFIG_KSU_SUSFS_SUS_PATH=y \
           CONFIG_KSU_SUSFS_SUS_MOUNT=y CONFIG_KSU_SUSFS_SUS_KSTAT=y; do
  grep -q "^${opt%%=*}=y" "$CFG" || echo "$opt" >> "$CFG"
done
echo "  $CFG:"
grep -n 'CONFIG_KSU' "$CFG" | tail -6

echo "==> 完成。KSU 与 SUSFS 版本必须配对，升级时同步改 KSU_REF / SUSFS_REF"
