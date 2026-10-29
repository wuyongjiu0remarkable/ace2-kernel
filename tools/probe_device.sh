#!/system/bin/sh
# 一加 Ace 2 温控/电池 现场探测脚本
# 用法（手机 root shell）: sh probe_device.sh > /sdcard/probe.txt
# 目的：拿到内核 patch 无法预判的运行时信息（可写性 / 服务名 / 电量计读数）

echo "== system =="
echo "kernel   : $(uname -r)"
echo "model    : $(getprop ro.product.model)"
echo "build    : $(getprop ro.build.display.id)"
echo "slot     : $(getprop ro.boot.slot_suffix)"
echo "verified : $(getprop ro.boot.verifiedbootstate)"

echo
echo "== root manager =="
[ -d /data/adb/ksu ]  && echo "KernelSU: yes"
[ -d /data/adb/magisk ] && echo "Magisk: yes"
[ -f /data/adb/ksud ] && echo "ksud: yes"

echo
echo "== thermal zones (type | temp | 可写 trip) =="
for z in /sys/class/thermal/thermal_zone*; do
  [ -d "$z" ] || continue
  t=$(cat "$z/type" 2>/dev/null)
  v=$(cat "$z/temp" 2>/dev/null)
  trips=""
  for tp in "$z"/trip_point_*_temp; do
    [ -e "$tp" ] || continue
    vv=$(cat "$tp" 2>/dev/null)
    case "$(ls -l "$tp" 2>/dev/null)" in
      -rw*) w="w" ;;
      *)    w="r" ;;
    esac
    trips="$trips $(basename "$tp" ._temp)=$vv($w)"
  done
  echo "$(basename "$z") | $t | $v |$trips"
done

echo
echo "== cooling devices =="
for c in /sys/class/thermal/cooling_device*; do
  [ -d "$c" ] || continue
  echo "$(basename "$c") | $(cat "$c/type" 2>/dev/null) | cur=$(cat "$c/cur_state" 2>/dev/null) max=$(cat "$c/max_state" 2>/dev/null)"
done

echo
echo "== power_supply / battery =="
for ps in /sys/class/power_supply/*; do
  [ -d "$ps" ] || continue
  case "$(cat "$ps/type" 2>/dev/null)" in
    Battery)
      echo "--- $(basename "$ps") ---"
      for a in charge_full_design charge_full voltage_max constant_charge_voltage \
               current_max charge_counter capacity health status technology; do
        [ -e "$ps/$a" ] && echo "$a = $(cat "$ps/$a" 2>/dev/null)"
      done
      ;;
  esac
done

echo
echo "== oplus chg =="
ls /sys/class/oplus_chg 2>/dev/null && ls /sys/class/oplus_chg/battery 2>/dev/null | head -30

echo
echo "== thermal services =="
getprop | grep -iE 'thermal|perfmgr' | head -20
ps -A 2>/dev/null | grep -iE 'thermal|perfmgr' | head -10

echo
echo "== cpufreq / core_ctl =="
for p in /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors; do
  [ -e "$p" ] && echo "$p = $(cat "$p")"
done
ls /sys/devices/system/cpu/cpu0/core_ctl 2>/dev/null && cat /sys/devices/system/cpu/cpu0/core_ctl/enable 2>/dev/null

echo
echo "== done =="
