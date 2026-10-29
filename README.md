# ACE2-Kernel — 一加 Ace 2（PJE110 / SM8475）GKI 内核改造

解容（更换大电池后放开容量限制）+ 移除 SoC 温控降频 + KernelSU/SUSFS 隐藏 root。

## 目标机

| 项 | 值 |
|---|---|
| 机型 | 一加 Ace 2（PJE110，项目代号 udon / 22803，平台 cape = SM8475） |
| 系统 | ColorOS 16.0.1.300 → **建议升级到 16.0.3.501**（与源码对齐） |
| 内核 | 5.10.236（GKI 2.0） |
| BL | 已解锁 |

## 源码基线

- `OnePlusOSS/android_kernel_common_oneplus_sm8475` @ `oneplus/sm8475_b_16.0.0_ace_2`（GKI 内核，Makefile 5.10.236）
- `OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8475` @ 同分支（vendor 模块 + 设备树）
- 本地已校验：分支内 `kernel_platform/qcom/proprietary/devicetree/oplus/oplus_chg/oplus-chg-22803.dtsi` 含 Ace 2 的电池/充电参数

## 进度

| 项 | 状态 | 说明 |
|---|---|---|
| 源码定位与版本校验 | ✅ 完成 | 5.10.236 与本机 `uname -r` 一致 |
| 解容参数定位 | ✅ 完成 | `batt_capacity_mah` / vfloat 表 / 电量计基准 |
| 温控参数定位 | ✅ 完成 | `cape-thermal.dtsi` 的 `tj_cfg` 是真正降频点 |
| 温控补丁（源码级） | ✅ 已验证可应用 | `patches/0001-thermal-raise-soc-throttle-trips.patch` |
| 温控/解容（二进制级） | ✅ 自测通过 | [`tools/dtbo_thermal.py`](tools/dtbo_thermal.py)，支持 dtbo / vendor_boot / 裸 DTB，见 [`docs/DTBO-PATCH.md`](docs/DTBO-PATCH.md) |
| boot.img 重打包 | ✅ 自测通过 | [`tools/bootimg.py`](tools/bootimg.py)，v3/v4 拆包 + 换 Image |
| 解容参数生成器 | ✅ 已出并测试 | `scripts/apply-battery-profile.py`，带 `--cell-max-mv` 过充保护 |
| 解容补丁 | ⛔ 等参数 | 你把容量/电压填进 Actions 输入即可自动生成 |
| KernelSU + SUSFS | ✅ 脚本已写 | `scripts/integrate-root.sh`（版本需匹配，未实测） |
| 构建流水线 | ⚠️ 降级 Plan B | 只编 GKI Image；dtbo 改走"改原厂 dtbo.img"路线 |
| 刷机/回退文档 | ✅ 完成 | `docs/FLASH.md` / `docs/ROLLBACK.md` |

## 目录

```
patches/     内核补丁（git apply，已在源码树上验证）
scripts/     补丁应用脚本
.github/     Actions 构建工作流
docs/        勘察记录 / 刷机 / 回退
tools/       设备现场探测脚本
src/         本地源码副本（modules_and_devicetree，仅用于分析/出补丁）
out/         构建产物、日志
```

## 三条铁律

1. **先出原厂等价包（baseline）并刷入验证能开机**，再叠加补丁。一次只加一个变量。
2. **四件套必须同源同一次编译**（boot / vendor_boot / dtbo / vendor_dlkm），不能混搭。
3. **刷机前先备份**，9008 不是计划内的退路。

## 已知限制

- 解锁后 `verifiedbootstate=orange`，Play Integrity STRONG / 银行级 TEE 校验过不去——这是硬边界
- 用户态 thermal HAL 会在运行期重写 trip 点，光改 DTS 不够，需要配套的 root 层处理
- 工程结构：解容/温控在 vendor（DTS + oplus_chg），root 在 GKI 内核（common 树），两者必须分别出包
