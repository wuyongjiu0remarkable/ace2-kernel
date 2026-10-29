# 一加 Ace 2 内核改造 —— 源码勘察记录

- 目标机：一加 Ace 2（PJE110），ColorOS 16.0.1.300，内核 5.10.236，已解 BL
- 源码仓库：`OnePlusOSS/android_kernel_common_oneplus_sm8475` + `..._modules_and_devicetree_oneplus_sm8475`
- 分支：`oneplus/sm8475_b_16.0.0_ace_2`（Android 16 / Baklava）
- 本地已拉取：modules_and_devicetree @ `3c9f7075`（commit 说明对应 `PHK110_16.0.3.501(CN01)`）
- 内核版本校验：common 仓库 Makefile `VERSION=5 PATCHLEVEL=10 SUBLEVEL=236` → 与你 `uname -r` = 5.10.236 **完全一致**

## 0. 一句话结论

三个需求里，**温控**和**root** 的技术路径已经锁定且可落地；**解容**的代码位置也已找到，
但必须先知道新电芯的规格（容量、充电截止电压）才能动参数，否则有安全风险。

## 1. 源码结构

```
modules_and_devicetree/
├── kernel_platform/
│   ├── build/           # GKI 构建脚本 build.sh / build.config
│   ├── gki/             # GKI 相关
│   ├── oplus/           # OPLUS 构建配置 (build/config/dts_check)
│   └── qcom/proprietary/devicetree/
│       ├── qcom/        # 平台 DTS：cape-*.dtsi (SM8475) / waipio / ukee ...
│       └── oplus/       # 项目 overlay：udon-22803-cape-overlay.dts 等
└── vendor/
    ├── oplus/kernel/    # OPLUS 驱动：charger / cpu / power / oplus_performance_5.10 ...
    └── qcom/            # 高通 vendor 模块 (audio/camera/display devicetree)
```

项目代号映射：

| 代号 | 平台 | 项目号 | 对应机型 | 依据 |
|---|---|---|---|---|
| **udon** | **cape = SM8475** | **22803 / 22881** | **一加 Ace 2（本机）** | 屏幕 `1240×2772`、overlay 名 `udon-22803-cape-overlay.dts`，charger `oplus-chg-22803.dtsi` |
| ovaltine | cape | 21841 / 21845 | 一加 Ace Pro / 10T | `ovaltine-21841-cape-overlay.dts` |
| wly | waipio (SM8450) | 20845 / 2084A | 一加 10 Pro 系 | `wly-20846-waipio-overlay.dts` |

> 注意：commit 说明写的是 `PHK110_16.0.3.501`，而分支名是 `ace_2`、项目号 22803。
> 刷机前请用「设置 → 关于手机 → 型号」核对一次机型代码。

## 2. 解容（容量 / 截止电压）

文件：`kernel_platform/qcom/proprietary/devicetree/oplus/oplus_chg/oplus-chg-22803.dtsi`（1007 行）

### 2.1 容量与电压（`&battery_charger` 节点）

| 属性 | 当前值 | 含义 |
|---|---|---|
| `qcom,batt_capacity_mah` | **5000** | 标称设计容量（旁边 `4870` 是 rated 容量，已注释） |
| `qcom,temp_normal_vfloat_mv` | **4465** | 常温充电截止电压 4.465V |
| `qcom,temp_warm_vfloat_mv` | 4130 | 温升后降到的截止电压 |
| `qcom,ffc_temp_normal_vfloat_mv` / `ffc1` / `ffc2` | **4540** | 快充（FFC）阶段截止 4.54V |
| `qcom,ffc_normal_vfloat_sw_limit` | 4480 | FFC 软件上限 |
| `qcom,vooc_1time_full_voltage` | 4530 | VOOC 首次满充判定电压 |
| `qcom,vooc_ntime_full_voltage` | 4520 | VOOC 后续满充判定电压 |
| `qcom,normal_vfloat_sw_limit` | 4415 | 普通充电软件上限 |

### 2.2 电量计（`oplus,track-charge`）

| 属性 | 当前值 |
|---|---|
| `track,nominal_qmax1` | 2480 |
| `track,nominal_fcc1` | 2300 |
| `track,external_gauge_num` | 1 |

### 2.3 结论

- 这是一颗 **4.5V 级高压电芯**（常温 4.465V、快充 4.54V）。换装的"更大电池"如果是普通
  4.4V 电芯，**原厂参数会直接过充**——这是本项目最大的安全隐患，必须先确认新电芯规格书。
- 解容的软件动作面：`batt_capacity_mah`（让系统按新容量计 100%）+ 满充判定电压 +
  `nominal_qmax1/fcc1`（电量计学习基准）。三处必须一起改，否则会出现"显示 100% 但只充进
  5000mAh"或"20% 突然关机"。

## 3. 温控

文件：`kernel_platform/qcom/proprietary/devicetree/qcom/cape-thermal.dtsi`（1464 行）

每个 thermal zone 有 4 个 trip，分工明确：

| trip 名 | 温度 | 作用 |
|---|---|---|
| `thermal-engine-config` | 125℃ | 老 thermal-engine 用（占位） |
| `thermal-hal-config` | 125℃ | 用户态 thermal HAL 用（**运行时会重写**） |
| `reset-mon-cfg` | 115℃ | 复位监控 |
| **`tj_cfg`** | **95℃** | **真正的降频点**，配 `cooling-maps` 绑到 `msm_gpu` / `cpufreq_hw` |

例（`gpuss-0`，GPU 热区）：

```dts
gpu0_tj_cfg: tj_cfg { temperature = <95000>; hysteresis = <5000>; type = "passive"; };
cooling-maps { gpu0_cdev { trip = <&gpu0_tj_cfg>; cooling-device = <&msm_gpu 0 THERMAL_NO_LIMIT>; }; };
```

CPU 侧同构（`cpu0-0-0` … `cpu7-0-0`），冷却设备是 `cpufreq_hw` 或 `cpu-isolate`。

**关键判断**：`thermal-hal-config` 只是占位，用户态 `android.hardware.thermal-service.qti`
会在启动后按 vendor 配置重写 trip 点。所以只改 DTS 不一定能彻底关掉降频，
必须同时处理用户态 thermal HAL（KSU 模块替换 `/vendor` 配置或停服务）。

充电侧限流：`oplus-chg-22803.dtsi` 里的 `qcom,temp_*_current_ma` 表（按电池温度分档），
与性能降频是两回事，游戏场景一般不受影响，但会影响边充边玩。

## 4. 隐藏 root

需要 `android_kernel_common_oneplus_sm8475`（5.10.236 GKI 树）：
KernelSU(-Next) + SUSFS 补丁 + `CONFIG_KSU=y`，用户态配 Zygisk Next / Shamiko。
天花板：解锁后 `verifiedbootstate=orange`，Play Integrity STRONG 与银行级 TEE 校验过不去。

## 5. 编译环境

- 本机：Win11 家庭版 / 15.7GB RAM / 32 线程 / D 盘余 240GB / **未装 WSL** / 无 clang
- 到 GitHub 的实际带宽约 **50 KB/s**（本次 37MB 源码拉了约 20 分钟）
- 结论：**本地编译不可行**（内核树 2.4GB + 工具链 1GB+）。走 GitHub Actions 编译，
  产物下载回来刷机。

## 6. 构建入口（勘察补充）

官方脚本：`kernel_platform/oplus/build/`

| 文件 | 作用 |
|---|---|
| `oplus_build.sh` | 唯一入口，用法 `./oplus_build.sh waipio consolidate thin all true` |
| `oplus_setup.sh` | 解析参数、设置 `variants_platform`（SM8475 用 `waipio`）、工具链路径 |
| `oplus_build_kernel.sh` | 内核 + vendor 模块，内部调 `build/android/prepare_vendor.sh` |
| `oplus_build_boot.sh` / `_dtbo.sh` / `_ko.sh` | 分别产出 boot / dtbo / 模块 |
| `oplus_build_repack_bootimg.sh` | 拿原厂 boot 重打包（说明官方也是"替换内核"思路） |

⚠️ **阻塞点**：`oplus_build_kernel.sh` 第 17 行 `source vendor/oplus/kernel/prebuilt/vendorsetup.sh`，
而该路径在 `modules_and_devicetree` 仓库里**不存在** —— 说明官方编译还需要第三个仓库
（prebuilt 工具链/闭源产物），或者必须放进完整 ColorOS 源码树。

这意味着：**两个仓库拼起来不足以直接编译**。CI 首次运行大概率会在这一步报错，
届时需要补 prebuilt 仓库，或改为"只编 GKI Image + 用原厂 dtbo 重打包"的简化路线。

⚠️ **决定性发现（第 2 轮）**：`common` 仓库根目录的 `build.config.msm.waipio`
是一个软链接，指向 `../msm-kernel/build.config.msm.waipio` —— 即整个平台期望的布局是：

```
kernel_platform/
├── build/        ← modules_and_devicetree 提供
├── common/       ← android_kernel_common_oneplus_sm8475
└── msm-kernel/   ← 厂商内核树，**未开源**
```

`msm-kernel` 不在 OnePlusOSS 的任何仓库里（已用 `q=prebuilt`、`q=sm8475` 搜过）。
`prepare_vendor.sh` 开头也写明 "assumes running after lunch w/Android build environment
variables available"，即它是给**完整 ColorOS/AOSP 源码树**用的，不是独立编译。

结论：**用公开仓库无法完整编译 vendor 侧（dtbo / vendor_boot / vendor_dlkm）**。
可行路线降级为 Plan B：

| 目标 | Plan B 做法 | 可行性 |
|---|---|---|
| GKI Image（boot.img） | 只用 `common` + `build/build.sh` + GKI 通用 config | ✅ 可独立编译 |
| 温控（dtbo） | 反编译原厂 dtbo.img → 改 trip → 重打包，或运行期 sysfs | ✅ 绕开编译 |
| 解容（充电参数） | 同样是 DTS，走同一条 dtbo 路线；或运行期写 sysfs | ⚠️ 待验证节点可写性 |
| root 隐藏 | 打进 GKI Image | ✅ |

这直接决定了 `scripts/build-gki.sh` 只出 `Image`，不出 dtbo。

补充（第 7 轮）：`common/arch/arm64/configs/gki_defconfig` **确认存在**（17,954 字节），
因此合成的 `configs/build.config.ace2` 里 `DEFCONFIG=gki_defconfig` 是有效的。
（此前两次 404 是调用 API 时漏了 `Accept: application/vnd.github+json` 头导致的，不是文件缺失。）

## 7. 待确认

1. 新电池型号 / 标称容量 / **最高充电电压** / 最大充电电流
2. 当前 `charge_full_design` 读数（root 后 `cat /sys/class/power_supply/battery/charge_full_design`）
3. 是否愿意把系统升到 16.0.3.501（与源码对齐）
