# 直接改 dtbo.img（绕开无法编译的 vendor 侧）

msm-kernel 未开源 → 编不出 dtbo。但"把某个 u32 属性从 A 改成 B"是同长度改动，
可以直接在二进制 DTB 里原地改，不反编译、不重编译、不改节点顺序和长度。

工具：[`tools/dtbo_thermal.py`](../tools/dtbo_thermal.py)（纯 Python，无依赖）

## 1. 从手机取出原厂 dtbo

```bash
adb shell su -c 'dd if=/dev/block/bootdevice/by-name/dtbo_a of=/sdcard/dtbo_stock.img'
adb pull /sdcard/dtbo_stock.img .
```

## 2. 先看里面有什么

```bash
python3 tools/dtbo_thermal.py --image dtbo_stock.img --list
```

应该能看到若干条目（每个对应一组机型的 overlay）。

## 3. 干跑，确认命中

```bash
# 温控：95℃ -> 105℃
python3 tools/dtbo_thermal.py --image dtbo_stock.img --from 95000 --to 105000
```

输出形如：

```
扫描 N 个 DTB，命中 5 处
  #3 /thermal-zones/gpuss-0/trips/tj_cfg: 95000 -> 105000
  ...
```

命中数为 0 说明热区不在 dtbo 里（可能在 vendor_boot 的 DTB）。工具已支持直连 vendor_boot：

```bash
python3 tools/dtbo_thermal.py --vendor-boot --image vendor_boot_stock.img \
        --from 95000 --to 105000 --out vendor_boot_patched.img
```

它会自己算出 dtb 段在镜像里的偏移（header 一页 + vendor_ramdisk 页对齐），只改那一小段，
ramdisk 区域保证零改动（自测里有这条断言）。

## 4. 落盘

```bash
python3 tools/dtbo_thermal.py --image dtbo_stock.img --out dtbo_patched.img \
        --from 95000 --to 105000
```

## 5. 解容同样可以走这条路

```bash
python3 tools/dtbo_thermal.py --image dtbo_stock.img --out dtbo_patched.img \
        --prop qcom,batt_capacity_mah --from 5000 --to 5500
```

> ⚠️ 只改容量时**不要**同时改电压。要改 `qcom,temp_normal_vfloat_mv` 必须先在
> `apply-battery-profile.py` 里过一遍 `--cell-max-mv` 校验，确认不超过电芯规格书。

## 6. 刷入

```bash
fastboot flash dtbo dtbo_patched.img
fastboot reboot
```

## 限制

- 只支持「同宽度、同值类型」的替换（u32 → u32）。字符串、数组长度变化不支持
- 不支持新增/删除节点
- 改完不校验 DTB 结构（DTB 本身无校验和），但**刷错 dtbo 会直接开不了机**，务必留原厂件
- AVB 未做处理：解 BL 后刷 dtbo 不校验，但会被 Play Integrity 看到
