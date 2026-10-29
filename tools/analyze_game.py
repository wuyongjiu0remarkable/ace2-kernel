#!/usr/bin/env python3
"""分析 game_watch.sh 采到的 CSV，判断是否真的发生温控降频。

用法:
    python analyze_game.py ace2_game.csv
"""
import csv
import sys

MAX7 = 3187200  # 大核硬件上限，用于判断是否被压


def main(path):
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({
                    "t": r["时间"],
                    "gpuT": int(r["GPU温度"]) / 1000,
                    "cpuT": int(r["CPU温度"]) / 1000,
                    "batT": int(r["电池温度"]) / 1000 if r["电池温度"] else None,
                    "cpu7": int(r["cpu7"]),
                    "max7": int(r["max7"]),
                    "gpu": int(r["gpu_cur"]) if r["gpu_cur"] else None,
                })
            except (ValueError, KeyError):
                continue

    if not rows:
        sys.exit("没有解析到数据，检查 CSV 格式")

    gmax = max(r["gpuT"] for r in rows)
    cmax = max(r["cpuT"] for r in rows)
    bmax = max((r["batT"] for r in rows if r["batT"] is not None), default=None)
    gmax_row = max(rows, key=lambda r: r["gpuT"])

    capped = [r for r in rows if r["max7"] < MAX7]
    low_freq = [r for r in rows if r["cpu7"] < MAX7 * 0.95]

    print(f"样本数        : {len(rows)}")
    print(f"GPU 温度峰值  : {gmax:.1f}℃  (出现在 {gmax_row['t']})")
    print(f"CPU 温度峰值  : {cmax:.1f}℃")
    if bmax is not None:
        print(f"电池温度峰值  : {bmax:.1f}℃")
    print()
    print(f"cpu7 上限被压低 : {len(capped)} 次 / {len(rows)}")
    print(f"cpu7 频率 <95%  : {len(low_freq)} 次 / {len(rows)}")

    if capped:
        print("\n上限被压低的时段（前 10 条）:")
        for r in capped[:10]:
            print(f"  {r['t']}  max7={r['max7']}  cpu7={r['cpu7']}  GPU={r['gpuT']:.1f}℃")

    if low_freq:
        print("\n频率下降时段（前 10 条）:")
        for r in low_freq[:10]:
            print(f"  {r['t']}  cpu7={r['cpu7']}  max7={r['max7']}  GPU={r['gpuT']:.1f}℃ CPU={r['cpuT']:.1f}℃")

    print("\n结论:")
    if gmax < 95:
        print(f"  GPU 峰值 {gmax:.1f}℃ 始终低于 95℃ —— 温控根本没被触发，")
        print("  如果此时掉帧，原因不在温度。")
    elif capped or low_freq:
        print(f"  GPU 到过 {gmax:.1f}℃，且观察到频率/上限被压低 —— 存在真实降频。")
        print("  对比温度触发点即可判断是内核 trip 还是用户态 HAL。")
    else:
        print(f"  GPU 到过 {gmax:.1f}℃ 但频率未被压低 —— 温控补丁生效，没降频。")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1])
