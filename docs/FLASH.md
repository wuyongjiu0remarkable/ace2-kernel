# 刷机步骤（一加 Ace 2 / SM8475）

> 前置：BL 已解锁；已用 `tools/probe_device.sh` 留档；已备份原厂四件套。
> 版本要求：手机系统需为 **16.0.3.501**（与源码分支一致），16.0.1.300 不要直刷。

## 0. 先备份（只做一次，务必做）

```bash
adb shell su -c 'dd if=/dev/block/bootdevice/by-name/boot$(getprop ro.boot.slot_suffix) of=/sdcard/boot_stock.img'
adb shell su -c 'dd if=/dev/block/bootdevice/by-name/vendor_boot$(getprop ro.boot.slot_suffix) of=/sdcard/vb_stock.img'
adb shell su -c 'dd if=/dev/block/bootdevice/by-name/dtbo$(getprop ro.boot.slot_suffix) of=/sdcard/dtbo_stock.img'
adb pull /sdcard/boot_stock.img .
adb pull /sdcard/vb_stock.img .
adb pull /sdcard/dtbo_stock.img .
```

`vendor_dlkm` 在动态分区里，用 `adb shell su -c 'ls -l /dev/block/mapper/'` 确认名字后同样 dd 出来。

## 1. 进 fastboot

```bash
adb reboot bootloader
fastboot devices
fastboot getvar current-slot     # 记下 a 还是 b
```

## 1.5 把 CI 产出的 Image 装回 boot.img

CI 给的是裸 `Image`，不能直接刷，要装回原厂 boot.img 的壳里（保留 ramdisk/cmdline）：

```bash
# 先看结构，确认 header_version 是 3 或 4
python3 tools/bootimg.py --image boot_stock.img --info

# 换内核重打包（signature 默认保留）
python3 tools/bootimg.py --image boot_stock.img --kernel Image --out boot_new.img

# 如果开机卡住，可试丢弃 boot signature
python3 tools/bootimg.py --image boot_stock.img --kernel Image --out boot_new.img --drop-signature
```

校验产物：`python3 tools/bootimg.py --image boot_new.img --info`，kernel_size 应该等于你的 Image 大小。

## 2. 刷入

```bash
# 按需替换为实际产物名
fastboot flash boot        boot.img
fastboot flash vendor_boot vendor_boot.img
fastboot flash dtbo        dtbo.img
fastboot flash vendor_dlkm vendor_dlkm.img

# 改了 vendor_dlkm 必须处理 verity，否则 /vendor 挂不上会卡开机
fastboot --disable-verity --disable-verification flash vbmeta vbmeta.img

fastboot reboot
```

## 3. 验证

```bash
adb shell uname -r                 # 应仍是 5.10.236（或带自定义后缀）
adb shell "cat /sys/class/thermal/thermal_zone0/trip_point_0_temp"   # 确认 patch 生效
adb shell "cat /sys/class/power_supply/battery/charge_full_design"   # 确认容量
```

## 4. 首次开机注意事项

- 首次启动会重新编译 dex/校验，5–15 分钟属正常；**卡第一屏超过 10 分钟再考虑回退**
- 指纹/相机/充电任一异常 → 立刻回退，不要继续用

## 5. 回退

见 `docs/ROLLBACK.md`。
