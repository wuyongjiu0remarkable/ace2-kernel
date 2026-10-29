#!/usr/bin/env python3
"""
dtbo_thermal.py —— 不依赖 dtc 的 DTBO/FDT 热区温度改写工具

为什么需要它：
  OnePlus 的 msm-kernel 未开源，无法用官方构建系统编 dtbo。
  但对"把某个 temperature 属性从 A 改成 B"这种同长度改动，
  可以直接在二进制 DTB 里原地改 4 字节 —— 不需要反编译、不需要重新编译、
  不会改变节点顺序/phandle/长度，因此不会破坏任何校验。

用法：
  python3 dtbo_thermal.py --selftest
  python3 dtbo_thermal.py --image dtbo.img --out dtbo_patched.img --from 95000 --to 105000
  python3 dtbo_thermal.py --image dtbo.img --list
"""
import argparse
import struct
import sys

FDT_MAGIC = 0xD00DFEED
DTBO_MAGIC = 0xD7B7AB1E
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9


# ---------------------------------------------------------------- DTB 解析
def parse_dtb(buf):
    """返回 (props, totalsize)；props = [(path, name, value_abs_off, value_len)]"""
    (magic, totalsize, off_struct, off_strings, off_rsvmap, ver, lastcomp,
     cpuid, size_strings, size_struct) = struct.unpack(">10I", buf[:40])
    if magic != FDT_MAGIC:
        raise ValueError(f"bad FDT magic {magic:#x}")
    if totalsize > len(buf):
        raise ValueError("totalsize > buffer")

    def cstr(off, base=off_strings, end=None):
        end = end if end is not None else off_strings + size_strings
        s = buf[base + off:end]
        return s[:s.index(b"\0")].decode("latin-1")

    props = []
    stack = []
    pos = off_struct
    limit = off_struct + size_struct
    while pos < limit:
        (tag,) = struct.unpack(">I", buf[pos:pos + 4])
        pos += 4
        if tag == FDT_BEGIN_NODE:
            end = buf.index(b"\0", pos)
            name = buf[pos:end].decode("latin-1")
            stack.append(name)
            pos = (end + 1 + 3) & ~3
        elif tag == FDT_END_NODE:
            if stack:
                stack.pop()
        elif tag == FDT_PROP:
            ln, nameoff = struct.unpack(">II", buf[pos:pos + 8])
            pos += 8
            path = "/" + "/".join(stack[1:]) if len(stack) > 1 else "/"
            props.append((path, cstr(nameoff), pos, ln))
            pos = (pos + ln + 3) & ~3
        elif tag == FDT_NOP:
            continue
        elif tag == FDT_END:
            break
        else:
            raise ValueError(f"bad tag {tag} @ {pos-4}")
    return props, totalsize


# ---------------------------------------------------------------- DTB 构造（仅自测用）
def build_dtb(tree):
    strings = {}
    str_blob = bytearray()

    def intern(s):
        if s not in strings:
            strings[s] = len(str_blob)
            str_blob.extend(s.encode() + b"\0")
        return strings[s]

    def pad4(b):
        return b + b"\0" * ((4 - len(b) % 4) % 4)

    def emit(node):
        out = bytearray()
        out += struct.pack(">I", FDT_BEGIN_NODE)
        out += pad4(node[0].encode() + b"\0")
        for k, v in node[1].items():
            out += struct.pack(">III", FDT_PROP, len(v), intern(k))
            out += pad4(bytes(v))
        for kid in node[2]:
            out += emit(kid)
        out += struct.pack(">I", FDT_END_NODE)
        return out

    body = emit(tree) + struct.pack(">I", FDT_END)
    rsv = b"\0" * 16
    off_rsv = 40
    off_struct = off_rsv + len(rsv)
    off_strings = off_struct + len(body)
    total = off_strings + len(str_blob)
    hdr = struct.pack(">10I", FDT_MAGIC, total, off_struct, off_strings, off_rsv,
                      17, 16, 0, len(str_blob), len(body))
    return bytes(hdr) + rsv + bytes(body) + bytes(str_blob)


# ---------------------------------------------------------------- DTBO 解析
def parse_dtbo(buf):
    (magic, total, hdr_size, ent_size, ent_count,
     ent_off, page_size, version) = struct.unpack(">8I", buf[:32])
    if magic != DTBO_MAGIC:
        raise ValueError(f"bad DTBO magic {magic:#x} (是 boot.img/vendor_boot.img 而不是 dtbo.img?)")
    if ent_size != 32:
        raise ValueError(f"unsupported entry size {ent_size}")
    entries = []
    for i in range(ent_count):
        o = ent_off + i * ent_size
        dt_size, dt_off, dt_id, dt_rev = struct.unpack(">4I", buf[o:o + 16])
        entries.append(dict(size=dt_size, offset=dt_off, id=dt_id, rev=dt_rev))
    return entries


# ---------------------------------------------------------------- vendor_boot 解析
VNDR_MAGIC = b"VNDRBOOT"


def parse_vendor_boot(buf):
    """v3/v4: header 占第一页，vendor_ramdisk 从 page 开始，dtb 紧随其后（各自页对齐）"""
    if buf[:8] != VNDR_MAGIC:
        raise ValueError("不是 vendor_boot 镜像（magic 不匹配）")
    ver, page, _kaddr, _raddr, vrsize = struct.unpack("<5I", buf[8:28])
    (dtb_size,) = struct.unpack("<I", buf[2100:2104])
    dtb_off = ((page + vrsize + page - 1) // page) * page
    return dict(version=ver, page=page, ramdisk_size=vrsize,
                dtb_size=dtb_size, dtb_offset=dtb_off)


# ---------------------------------------------------------------- 核心：改写
def patch_image(buf, old, new, dry_run=True, entries=None,
                prop="temperature", need_path=True):
    if entries is None:
        entries = parse_dtbo(buf)
    out = bytearray(buf)
    changes, scanned = [], 0
    for i, e in enumerate(entries):
        dtb = buf[e["offset"]:e["offset"] + e["size"]]
        props, _ = parse_dtb(dtb)
        scanned += 1
        for path, name, voff, vlen in props:
            if name != prop or vlen != 4:
                continue
            (val,) = struct.unpack(">I", dtb[voff:voff + 4])
            if val != old:
                continue
            if need_path and not any(k in path.lower() for k in ("tj", "junction", "trips", "thermal")):
                continue
            abs_off = e["offset"] + voff
            struct.pack_into(">I", out, abs_off, new)
            changes.append((i, path, val, new))
    return bytes(out), changes, scanned


def selftest():
    dtb = build_dtb(("", {}, [
        ("thermal-zones", {}, [
            ("gpuss-0", {}, [
                ("trips", {}, [
                    ("tj_cfg", {"temperature": struct.pack(">I", 95000),
                                "hysteresis": struct.pack(">I", 5000)}, []),
                ]),
            ]),
        ]),
    ]))
    props, total = parse_dtb(dtb)
    assert total == len(dtb), (total, len(dtb))
    got = {(p, n) for p, n, _, _ in props}
    assert ("/thermal-zones/gpuss-0/trips/tj_cfg", "temperature") in got, got
    print(f"[1/3] 解析合成 DTB 成功，共 {len(props)} 个属性")

    # 包一层 DTBO
    hdr_size, ent_size = 32, 32
    dt_off = hdr_size + ent_size
    total_size = dt_off + len(dtb)
    hdr = struct.pack(">8I", DTBO_MAGIC, total_size, hdr_size, ent_size, 1,
                      hdr_size, 4096, 0)
    entry = struct.pack(">4I", len(dtb), dt_off, 0, 0) + b"\0" * 16
    dtbo = hdr + entry + dtb
    entries = parse_dtbo(dtbo)
    assert len(entries) == 1 and entries[0]["size"] == len(dtb)
    print("[2/3] DTBO 封装/解析成功")

    out, changes, scanned = patch_image(dtbo, 95000, 105000, dry_run=False)
    assert scanned == 1, scanned
    assert len(changes) == 1, changes
    assert changes[0][2] == 95000 and changes[0][3] == 105000
    e = parse_dtbo(out)[0]
    props2, _ = parse_dtb(out[e["offset"]:e["offset"] + e["size"]])
    vals = {n: struct.unpack(">I", out[e["offset"] + o:e["offset"] + o + 4])[0]
            for _, n, o, _ in props2}
    assert vals["temperature"] == 105000, vals
    assert vals["hysteresis"] == 5000, "不应改动其它属性"
    print(f"[3/4] 改写成功: {changes[0][1]} 95000 -> 105000，其它属性未动")

    raw_entry = [dict(size=len(dtb), offset=0, id=0, rev=0)]
    out2, ch2, _ = patch_image(dtb, 95000, 108000, dry_run=False, entries=raw_entry)
    assert len(ch2) == 1 and out2 != dtb, ch2
    assert len(out2) == len(dtb), "裸 DTB 改写不应改变长度"
    print("[4/4] 裸 DTB 模式通过")

    dtb2 = build_dtb(("", {}, [
        ("soc", {}, [("battery_charger", {
            "qcom,batt_capacity_mah": struct.pack(">I", 5000)}, [])]),
    ]))
    out3, ch3, _ = patch_image(
        dtb2, 5000, 5500, dry_run=False,
        entries=[dict(size=len(dtb2), offset=0, id=0, rev=0)],
        prop="qcom,batt_capacity_mah", need_path=False)
    assert len(ch3) == 1, ch3
    print("[附加] 解容属性改写通过: qcom,batt_capacity_mah 5000 -> 5500")

    # vendor_boot：header 一页 + ramdisk + 页对齐后的 dtb
    page, vrsize = 4096, 5000
    dtb_off = ((page + vrsize + page - 1) // page) * page
    hdr = bytearray(2124)
    hdr[0:8] = VNDR_MAGIC
    struct.pack_into("<5I", hdr, 8, 3, page, 0, 0, vrsize)
    struct.pack_into("<I", hdr, 2096, 2124)
    struct.pack_into("<I", hdr, 2100, len(dtb))
    vb = bytes(hdr).ljust(page, b"\0") + b"R" * vrsize
    vb = vb.ljust(dtb_off, b"\0") + dtb
    info = parse_vendor_boot(vb)
    assert info["dtb_offset"] == dtb_off and info["dtb_size"] == len(dtb), info
    out5, ch5, _ = patch_image(
        vb, 95000, 106000,
        entries=[dict(size=len(dtb), offset=dtb_off, id=0, rev=0)])
    assert len(ch5) == 1, ch5
    assert out5[:dtb_off] == vb[:dtb_off], "dtb 之前的 ramdisk 区域不应被改动"
    print("[5/5] vendor_boot 的 dtb 段改写通过，ramdisk 区域零改动")
    print("SELFTEST PASSED")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--image")
    ap.add_argument("--out")
    ap.add_argument("--from", dest="old", type=int, default=95000,
                    help="要替换的值，默认 95000（温度是毫摄氏度，95℃=95000）")
    ap.add_argument("--to", dest="new", type=int, default=105000)
    ap.add_argument("--prop", default="temperature",
                    help="属性名；改容量时用 qcom,batt_capacity_mah")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--vendor-boot", action="store_true",
                    help="输入是 vendor_boot.img，改其中的 dtb 段")
    a = ap.parse_args()

    if a.selftest:
        selftest()
        return
    if not a.image:
        ap.error("需要 --image 或 --selftest")

    with open(a.image, "rb") as f:
        buf = f.read()
    print(f"读取 {a.image}: {len(buf)} 字节")
    if a.vendor_boot or buf[:8] == VNDR_MAGIC:
        vb = parse_vendor_boot(buf)
        print(f"识别为 vendor_boot v{vb['version']}：ramdisk={vb['ramdisk_size']} "
              f"dtb={vb['dtb_size']} @ {vb['dtb_offset']}")
        entries = [dict(size=vb["dtb_size"], offset=vb["dtb_offset"], id=0, rev=0)]
        kind = "vendor_boot(dtb)"
    else:
        try:
            entries = parse_dtbo(buf)
            kind = "DTBO 镜像"
        except ValueError:
            entries = [dict(size=len(buf), offset=0, id=0, rev=0)]
            kind = "裸 DTB"
    print(f"识别为 {kind}，{len(entries)} 个 DTB")
    if a.list:
        for i, e in enumerate(entries):
            print(f"  #{i} id={e['id']} rev={e['rev']} size={e['size']} off={e['offset']}")
        return

    out, changes, scanned = patch_image(buf, a.old, a.new, dry_run=a.dry_run, entries=entries,
                                        prop=a.prop, need_path=(a.prop == "temperature"))
    print(f"扫描 {scanned} 个 DTB，命中 {len(changes)} 处")
    for i, path, o, n in changes:
        print(f"  #{i} {path}: {o} -> {n}")
    if not changes:
        sys.exit("没有命中，确认 --from 的值（毫摄氏度，95℃ = 95000）")

    if a.dry_run:
        print("(dry-run，未写文件)")
        return
    if not a.out:
        ap.error("写文件需要 --out")
    with open(a.out, "wb") as f:
        f.write(out)
    print(f"已写出 {a.out} ({len(out)} 字节)")


if __name__ == "__main__":
    main()
