#!/usr/bin/env bash
# 组装 OnePlus SM8475 源码树并编译 GKI Image
#
# 目录约定（OnePlus 官方布局）：
#   <root>/kernel_platform/{build,oplus,qcom,common}
#   <root>/vendor/{oplus,qcom}
#
# 关键事实：common/build.config.msm.waipio 是指向 ../msm-kernel/ 的软链接，
# 而 msm-kernel 未开源 —— 所以走 GKI 通用配置，只出 boot.img 用的 Image。
set -euo pipefail

ROOT="${1:-$PWD}"
BRANCH="${BRANCH:-oneplus/sm8475_b_16.0.0_ace_2}"
COMMON_REPO="${COMMON_REPO:-https://github.com/OnePlusOSS/android_kernel_common_oneplus_sm8475.git}"
MODDT_REPO="${MODDT_REPO:-https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8475.git}"
JOBS="${JOBS:-$(nproc)}"

mkdir -p "$ROOT"
cd "$ROOT"
mkdir -p kernel_platform

echo "==> [1/4] 拉取源码（浅克隆）"
if [ ! -d kernel_platform/build ]; then
  git clone --depth 1 -b "$BRANCH" "$MODDT_REPO" .moddt.tmp
  # modules 仓库根目录就是 kernel_platform + vendor
  cp -a .moddt.tmp/. .
  rm -rf .moddt.tmp
fi
if [ ! -d kernel_platform/common/arch ]; then
  git clone --depth 1 -b "$BRANCH" "$COMMON_REPO" kernel_platform/common
fi

echo "==> [2/4] 校验内核版本（必须与手机 uname -r 一致）"
grep -E '^(VERSION|PATCHLEVEL|SUBLEVEL)' kernel_platform/common/Makefile

if [ "${ASSEMBLE_ONLY:-0}" = "1" ]; then
  echo "==> ASSEMBLE_ONLY=1，源码已就绪，跳过编译"
  exit 0
fi

echo "==> [3/4] 选择 build config"
CFG=""
for c in "common/build.config.gki.aarch64" "common/build.config.gki"; do
  if [ -e "kernel_platform/$c" ]; then CFG="$c"; break; fi
done
if [ -z "$CFG" ]; then
  echo "!! 没有现成的完整 config（msm-kernel 未开源），使用合成配置"
  cp "$(cd "$(dirname "$0")/.." && pwd)/configs/build.config.ace2" \
     kernel_platform/build.config.ace2
  CFG="build.config.ace2"
fi
echo "使用 BUILD_CONFIG=$CFG"

echo "==> [4/4] 编译"
cd kernel_platform
OUT_DIR="${OUT_DIR:-$ROOT/out}" DIST_DIR="${DIST_DIR:-$ROOT/out/dist}" \
BUILD_CONFIG="$CFG" ./build/build.sh -j"$JOBS" 2>&1 | tee "$ROOT/out/build.log"

echo "==> 产物"
ls -la "$ROOT/out/dist" 2>/dev/null || true
find "$ROOT/out" -maxdepth 4 -type f \( -name 'Image' -o -name 'Image.lz4' -o -name 'Image.gz' \) -print 2>/dev/null || true
