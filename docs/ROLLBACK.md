# 回退与救砖

## A. 能进 fastboot（最常见）

```bash
adb reboot bootloader            # 或关机后 音量下+电源
fastboot devices

fastboot flash boot        boot_stock.img
fastboot flash vendor_boot vb_stock.img
fastboot flash dtbo        dtbo_stock.img
fastboot --disable-verity --disable-verification flash vbmeta vbmeta_stock.img
fastboot reboot
```

如果刷完仍卡开机：`fastboot -w` 清数据（会丢数据，最后手段）。

## B. 能进 fastboot 但刷不进去

切槽再试（A/B 机型两边独立）：

```bash
fastboot getvar current-slot
fastboot --set-active=a          # 或 b，切到没被动过的那一边
fastboot reboot
```

原厂 OTA 通常只更新当前槽，另一个槽往往还是干净系统——这是最省事的救命手段。

## C. 进不了 fastboot，只能 9008/EDL

- 一加/OPPO 的高通 9008 需要签名 firehose，官方工具链路上有授权限制
- 社区"免授权 9008"方案时有时无，且官方会持续封堵，**不要把它当计划内的退路**
- 所以真正的保险是：**刷机前必须备份四件套**（见 FLASH.md 第 0 步）

## D. 绝对不要做的事

| 禁止 | 原因 |
|---|---|
| 跨 anti-rollback 版本降级 | 直接变砖，且 9008 也救不回 |
| 刷入非本机型（PJE110/11R 之外的）镜像 | 分区表/DTB 不匹配 |
| 只换 boot.img 而保留原 vendor_dlkm | vermagic/符号 CRC 不匹配，模块加载失败 |
| 在 16.0.1.300 上刷 16.0.3.501 的包 | 充电/相机 DTS 不匹配 |

## E. 判断"是不是真砖"

- 能进 fastboot → 软砖，A/B 基本都能救
- 黑屏 + 无 fastboot + 电脑无 9008 端口 → 硬砖，只能售后
- 有 9008 端口但无授权 → 需要官方售后
