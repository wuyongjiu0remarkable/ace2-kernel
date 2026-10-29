#!/system/bin/sh
# 游戏/温控采样器 —— 低开销：每 10 秒读 12 个 sysfs 文件
# 用法（手机 root shell 或 adb）:
#   sh game_watch.sh [总秒数] [间隔秒] [输出文件]
#   sh game_watch.sh 2400 10 /sdcard/ace2_game.csv     # 40 分钟
DUR=${1:-2400}
INT=${2:-10}
OUT=${3:-/sdcard/ace2_game.csv}

find_zone() {
  for z in /sys/class/thermal/thermal_zone*; do
    [ "$(cat "$z/type" 2>/dev/null)" = "$1" ] && { echo "$z"; return 0; }
  done
}

GZ=$(find_zone gpuss-0)
CZ=$(find_zone cpuss-0)
[ -z "$GZ" ] && GZ=/sys/class/thermal/thermal_zone37
[ -z "$CZ" ] && CZ=/sys/class/thermal/thermal_zone25

echo "时间,GPU温度,CPU温度,电池温度,cpu0,cpu4,cpu7,max0,max4,max7,gpu_cur,gpu_max" > "$OUT"
END=$(( $(date +%s) + DUR ))
N=0
while [ "$(date +%s)" -lt "$END" ]; do
  echo "$(date +%H:%M:%S),$(cat $GZ/temp 2>/dev/null),$(cat $CZ/temp 2>/dev/null),$(cat /sys/class/power_supply/battery/temp 2>/dev/null),$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null),$(cat /sys/devices/system/cpu/cpu4/cpufreq/scaling_cur_freq 2>/dev/null),$(cat /sys/devices/system/cpu/cpu7/cpufreq/scaling_cur_freq 2>/dev/null),$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq 2>/dev/null),$(cat /sys/devices/system/cpu/cpu4/cpufreq/scaling_max_freq 2>/dev/null),$(cat /sys/devices/system/cpu/cpu7/cpufreq/scaling_max_freq 2>/dev/null),$(cat /sys/class/kgsl/kgsl-3d0/devfreq/cur_freq 2>/dev/null),$(cat /sys/class/kgsl/kgsl-3d0/devfreq/max_freq 2>/dev/null)" >> "$OUT"
  N=$((N+1))
  sleep $INT
done
echo "采样完成: $OUT  共 $N 行"
