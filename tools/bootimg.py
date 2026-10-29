#!/usr/bin/env python3
"""
bootimg.py —— 纯 Python 拆/重打包 boot.img（v3 / v4），用于替换 GKI Image

为什么需要：
  CI 编出来的是 Image，要变成能 `fastboot flash boot` 的文件，
  必须把它塞回原厂 boot.img 的壳里（保留 ramdisk / cmdline / header 版本）。

用法：
  python3 bootimg.py --selftest
  python3 bootimg.py --image boot_stock.img --info
  python3 bootimg.py --image boot_stock.img --unpack out/
  python3 bootimg.py --image boot_stock.img --kernel Image --out boot_new.img
"""
import argparse
import os
import struct
import sys

PAGE = 4096
MAGIC = b"ANDROID!"


def align(n, a=PAGE):
    return (n + a - 1) // a * a


def parse_header(buf):
    if buf[:8] != MAGIC:
        sys.exit("不是 Android boot image（magic 不匹配）")
    (kernel_size, ramdisk_size, os_version, header_size,
     r0, r1, r2, r3, header_version) = struct.unpack("<9I", buf[8:44])
    cmdline = buf[44:44 + 1536].split(b"\0")[0].decode("latin-1")
    h = dict(kernel_size=kernel_size, ramdisk_size=ramdisk_size,
             os_version=os_version, header_size=header_size,
             header_version=header_version, cmdline=cmdline,
             reserved=[r0, r1, r2, r3])
    if header_version >= 4:
        (h["signature_size"],) = struct.unpack("<I", buf[1580:1584])
    else:
        h["signature_size"] = 0
    return h


def unpack(buf):
    h = parse_header(buf)
    koff = align(h["header_size"])
    roff = align(koff + h["kernel_size"])
    soff = align(roff + h["ramdisk_size"])
    h["kernel"] = buf[koff:koff + h["kernel_size"]]
    h["ramdisk"] = buf[roff:roff + h["ramdisk_size"]]
    sig_len = h["signature_size"]
    h["signature"] = buf[soff:soff + sig_len] if sig_len else b""
    return h


def pack(h, kernel=None, ramdisk=None, signature=None, drop_signature=False):
    kernel = h["kernel"] if kernel is None else kernel
    ramdisk = h["ramdisk"] if ramdisk is None else ramdisk
    signature = h["signature"] if signature is None else signature
    if drop_signature:
        signature = b""
    ver = h["header_version"]
    if ver >= 4:
        hdr_size = 1584
        hdr = struct.pack("<8s9I", MAGIC, len(kernel), len(ramdisk),
                          h["os_version"], hdr_size,
                          *h["reserved"], ver)
        hdr += h["cmdline"].encode("latin-1")[:1536].ljust(1536, b"\0")
        hdr += struct.pack("<I", len(signature))
    elif ver == 3:
        hdr_size = 1580
        hdr = struct.pack("<8s9I", MAGIC, len(kernel), len(ramdisk),
                          h["os_version"], hdr_size,
                          *h["reserved"], ver)
        hdr += h["cmdline"].encode("latin-1")[:1536].ljust(1536, b"\0")
    else:
        sys.exit(f"暂不支持 header_version={ver}（本项目只需要 v3/v4）")

    assert len(hdr) == hdr_size, (len(hdr), hdr_size)
    out = bytearray(hdr.ljust(align(hdr_size), b"\0"))
    out += kernel.ljust(align(len(kernel)), b"\0")
    out += ramdisk.ljust(align(len(ramdisk)), b"\0")
    if signature:
        out += signature.ljust(align(len(signature)), b"\0")
    return bytes(out)


def selftest():
    h = dict(kernel_size=0, ramdisk_size=0, os_version=0x12345678,
             header_size=1584, header_version=4,
             reserved=[0, 0, 0, 0], cmdline="console=ttyMSM0 androidboot.hardware=qcom",
             signature_size=4096)
    kernel = bytes(range(256)) * 37          # 9472 bytes
    ramdisk = b"RD" * 5000                    # 10000 bytes
    sig = b"S" * 4096
    img = pack(h, kernel=kernel, ramdisk=ramdisk, signature=sig)

    h2 = unpack(img)
    assert h2["kernel"] == kernel, "kernel 不一致"
    assert h2["ramdisk"] == ramdisk, "ramdisk 不一致"
    assert h2["signature"] == sig, "signature 不一致"
    assert h2["cmdline"] == h["cmdline"], h2["cmdline"]
    assert h2["header_version"] == 4
    print(f"[1/3] v4 往返成功: kernel={len(kernel)} ramdisk={len(ramdisk)} sig={len(sig)}")

    new_kernel = b"NEWK" * 3000
    img2 = pack(h2, kernel=new_kernel)
    h3 = unpack(img2)
    assert h3["kernel"] == new_kernel and h3["ramdisk"] == ramdisk
    assert len(img2) == align(1584) + align(len(new_kernel)) + align(len(ramdisk)) + align(4096)
    print("[2/3] 换内核重打包成功，ramdisk/signature 保留")

    img3 = pack(h3, drop_signature=True)
    h4 = unpack(img3)
    assert h4["signature_size"] == 0 and h4["signature"] == b""
    assert len(img3) < len(img2)
    print("[3/3] drop-signature 模式成功")
    print("SELFTEST PASSED")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--image")
    ap.add_argument("--info", action="store_true")
    ap.add_argument("--unpack", metavar="DIR")
    ap.add_argument("--kernel", help="新的 Image 文件")
    ap.add_argument("--out", help="输出 boot.img")
    ap.add_argument("--drop-signature", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        selftest()
        return
    if not a.image:
        ap.error("需要 --image 或 --selftest")

    with open(a.image, "rb") as f:
        buf = f.read()
    h = unpack(buf)

    if a.info or (not a.unpack and not a.out):
        print(f"header_version : {h['header_version']}")
        print(f"header_size    : {h['header_size']}")
        print(f"kernel_size    : {h['kernel_size']} ({h['kernel_size']/1048576:.2f} MiB)")
        print(f"ramdisk_size   : {h['ramdisk_size']}")
        print(f"signature_size : {h['signature_size']}")
        print(f"os_version     : {h['os_version']:#x}")
        print(f"cmdline        : {h['cmdline']}")
        return

    if a.unpack:
        os.makedirs(a.unpack, exist_ok=True)
        for name in ("kernel", "ramdisk", "signature"):
            data = h[name]
            if data:
                with open(os.path.join(a.unpack, name), "wb") as f:
                    f.write(data)
                print(f"写出 {name}: {len(data)} 字节")
        with open(os.path.join(a.unpack, "cmdline.txt"), "w", encoding="utf-8") as f:
            f.write(h["cmdline"])
        print(f"cmdline 已写出；header_version={h['header_version']}")

    if a.out:
        if not a.kernel:
            ap.error("--out 必须同时给 --kernel")
        with open(a.kernel, "rb") as f:
            newk = f.read()
        out = pack(h, kernel=newk, drop_signature=a.drop_signature)
        with open(a.out, "wb") as f:
            f.write(out)
        print(f"已写出 {a.out}: kernel {h['kernel_size']} -> {len(newk)} 字节，"
              f"总大小 {len(out)} 字节，signature={'已丢弃' if a.drop_signature else '保留'}")


if __name__ == "__main__":
    main()
