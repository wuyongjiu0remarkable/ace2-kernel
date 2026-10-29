#!/usr/bin/env python3
"""
按新电芯规格生成/应用解容改动（一加 Ace 2 / oplus-chg-22803.dtsi）

设计原则：
  1. 默认只做「容量对齐」，不动电压 —— 最安全。换的电芯只要和原厂同为 4.465V 级，
     改容量即可让系统按新容量计满、不再提前跳 100%。
  2. 只有显式给 --vfloat-mv 才会动电压，且必须同时给 --cell-max-mv（电芯规格书上限），
     任何一项超过 cell_max 直接拒绝执行。
  3. 默认 dry-run，加 --write 才落盘。

用法示例：
  # 只看改动
  python3 scripts/apply-battery-profile.py --dtsi oplus-chg-22803.dtsi --capacity 5500
  # 落盘（同电压级电芯）
  python3 scripts/apply-battery-profile.py --dtsi ... --capacity 5500 --write
  # 换电压级（必须给 cell-max）
  python3 scripts/apply-battery-profile.py --dtsi ... --capacity 5500 \
      --vfloat-mv 4465 --ffc-mv 4540 --cell-max-mv 4540 --write
"""
import argparse
import difflib
import re
import sys

BASE_CAPACITY = 5000
BASE_QMAX = 2480
BASE_FCC = 2300

CAP_PROPS = ["qcom,batt_capacity_mah"]
QMAX_PROPS = ["track,nominal_qmax1"]
FCC_PROPS = ["track,nominal_fcc1"]
VFLOAT_PROPS = [
    "qcom,temp_normal_vfloat_mv",
    "qcom,temp_little_cool_vfloat_mv",
    "qcom,temp_cool_vfloat_mv",
    "qcom,temp_little_cold_vfloat_mv",
    "qcom,temp_cold_vfloat_mv",
]
SW_PROPS = [
    "qcom,normal_vfloat_sw_limit",
    "qcom,little_cool_vfloat_sw_limit",
    "qcom,cool_vfloat_sw_limit",
    "qcom,little_cold_vfloat_sw_limit",
    "qcom,cold_vfloat_sw_limit",
]
FFC_PROPS = [
    "qcom,ffc_temp_normal_vfloat_mv",
    "qcom,ffc1_temp_normal_vfloat_mv",
    "qcom,ffc2_temp_normal_vfloat_mv",
]
VOOC_PROPS = ["qcom,vooc_1time_full_voltage", "qcom,vooc_ntime_full_voltage"]


def sub_prop(text, prop, value):
    """把 `prop = <num>;` 替换为 value；返回 (新文本, 命中数)"""
    pat = re.compile(r"(?m)^(\s*)" + re.escape(prop) + r"\s*=\s*<(\d+)>;")
    hits = len(pat.findall(text))
    return pat.sub(lambda m: f"{m.group(1)}{prop} = <{value}>;", text), hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dtsi", required=True)
    ap.add_argument("--capacity", type=int, required=True, help="新电芯标称容量 mAh")
    ap.add_argument("--qmax", type=int, help="电量计 qmax（默认按容量等比换算）")
    ap.add_argument("--fcc", type=int, help="电量计 fcc（默认按容量等比换算）")
    ap.add_argument("--vfloat-mv", type=int, help="常温充电截止电压，不给则不改电压")
    ap.add_argument("--sw-limit-mv", type=int, help="软件上限（默认 vfloat-50）")
    ap.add_argument("--ffc-mv", type=int, help="快充截止电压，给了 vfloat 才生效")
    ap.add_argument("--vooc-full-mv", type=int, help="VOOC 满充判定电压")
    ap.add_argument("--cell-max-mv", type=int, help="电芯规格书上允许的最高电压（动电压时必填）")
    ap.add_argument("--write", action="store_true", help="真正写入文件")
    args = ap.parse_args()

    if not (4000 <= args.capacity <= 7000):
        sys.exit(f"拒绝: 容量 {args.capacity}mAh 超出合理范围 4000-7000")

    touch_voltage = any([args.vfloat_mv, args.ffc_mv, args.vooc_full_mv])
    if touch_voltage and not args.cell_max_mv:
        sys.exit("拒绝: 要改电压就必须给 --cell-max-mv（电芯规格书上限），否则无法保证不过充")

    if args.cell_max_mv:
        for name, v in [("vfloat", args.vfloat_mv), ("ffc", args.ffc_mv), ("vooc-full", args.vooc_full_mv)]:
            if v and v > args.cell_max_mv:
                sys.exit(f"拒绝: {name}={v}mV 超过电芯上限 {args.cell_max_mv}mV")

    with open(args.dtsi, encoding="utf-8") as f:
        original = f.read()

    text = original
    report = []

    def apply(props, value, label):
        nonlocal text
        total = 0
        for p in props:
            text, hits = sub_prop(text, p, value)
            total += hits
        report.append((label, total, value))

    # 容量
    apply(CAP_PROPS, args.capacity, "容量 batt_capacity_mah")

    # 电量计：默认按容量等比
    scale = args.capacity / BASE_CAPACITY
    qmax = args.qmax if args.qmax else round(BASE_QMAX * scale)
    fcc = args.fcc if args.fcc else round(BASE_FCC * scale)
    apply(QMAX_PROPS, qmax, "电量计 nominal_qmax1")
    apply(FCC_PROPS, fcc, "电量计 nominal_fcc1")

    if args.vfloat_mv:
        sw = args.sw_limit_mv if args.sw_limit_mv else args.vfloat_mv - 50
        if sw >= args.vfloat_mv:
            sys.exit(f"拒绝: sw_limit({sw}) 必须小于 vfloat({args.vfloat_mv})")
        apply(VFLOAT_PROPS, args.vfloat_mv, "常温截止电压 vfloat")
        apply(SW_PROPS, sw, "软件上限 sw_limit")
        if args.ffc_mv:
            apply(FFC_PROPS, args.ffc_mv, "快充截止 ffc")
        if args.vooc_full_mv:
            apply(VOOC_PROPS, args.vooc_full_mv, "VOOC 满充判定")

    print("== 改动清单 ==")
    for label, n, v in report:
        flag = "OK " if n else "!! 未命中"
        print(f"  [{flag}] {label:24s} -> {v}  ({n} 处)")

    if text == original:
        sys.exit("\n没有任何改动，检查属性名或文件是否正确")

    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        text.splitlines(keepends=True),
        fromfile=args.dtsi,
        tofile=args.dtsi + " (modified)",
        n=2,
    )
    print("\n== diff ==")
    sys.stdout.writelines(diff)

    if args.write:
        with open(args.dtsi, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        print("\n已写入:", args.dtsi)
    else:
        print("\n(dry-run，加 --write 才会落盘)")


if __name__ == "__main__":
    main()
