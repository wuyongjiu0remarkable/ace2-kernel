# 编 SUSFS 内核（GitHub Actions 版）

## 为什么不在这台机器上编

- 本机 Windows，没有 WSL / Linux 环境，ARM64 内核交叉编译跑不了
- 内核树 188MB + clang 预编译包 600MB+，本机就算装了 WSL，编译也要 40~90 分钟
- Actions 的 runner 是 4 核 16G Ubuntu，免费，跑完直接下载产物

**所以这一步必须你来点一下，我没法代跑。**

## 你需要准备

| 项 | 说明 |
|---|---|
| GitHub 账号 | 免费版够用 |
| 一个新仓库 | 把本目录推上去即可（仓库很小，只有脚本和补丁） |
| `boot_a.img` | 从手机 dump，用来把新内核装回去（不推仓库，只在本地用） |

## 步骤

### 1. 建仓库并推送

```bash
cd "D:\ACE2 V_1.0"
git init
git add .
git commit -m "ace2 kernel build"
git remote add origin https://github.com/<你的用户名>/ace2-kernel.git
git push -u origin main
```

> `src/` 和 `out/` 已经在 `.gitignore` 里，不会被推上去（它们有 500MB+）。

### 2. 跑工作流

仓库页面 → **Actions** → `build-sm8475` → **Run workflow**：

| 输入 | 填 |
|---|---|
| variant | `full` |
| capacity_mah | `6100` |
| cell_max_mv | `4530` |
| vfloat_mv | 留空（不动电压） |

### 3. 下载产物

跑完在 Actions 页面下载 artifact，里面是 `Image`。

### 4. 装回 boot.img

```cmd
D:\python\python.exe "D:\ACE2 V_1.0\tools\bootimg.py" --image "D:\ACE2 V_1.0\boot_a.img" --kernel Image --out "D:\ACE2 V_1.0\boot_susfs.img"
```

### 5. 刷

```cmd
adb reboot bootloader
fastboot flash boot "D:\ACE2 V_1.0\boot_susfs.img"
fastboot reboot
```

回退：`fastboot flash boot "D:\ACE2 V_1.0\boot_a.img"`

---

## 工作流里已经写死的几件事

| 项 | 值 | 原因 |
|---|---|---|
| 内核源码 | `sm8475_b_16.0.0_ace_2` | 与你机器 5.10.236 一致 |
| KernelSU | KernelSU-Next | 支持 SUSFS 且维护活跃 |
| SUSFS | `ShirkNeko/susfs4ksu` 镜像 | 原版在 GitLab，本机代理连不上，GitHub 有镜像 |
| 构建配置 | `common/build.config.gki.aarch64` | 官方真实存在的那份（不是合成的） |
| 模块签名 | 不启用强制签名 | 否则自编模块加载不了 |

## 已知风险（必须先说）

1. **这套工作流我一次都没跑过**。语法检查过，但第一次运行大概率要修 1~2 处（缺依赖、路径不对、SUSFS 补丁对不上）
2. **SUSFS 补丁可能打不上**。它是按特定内核版本写的，OnePlus 的 5.10.236 有厂商改动，冲突是常态
3. **编出来的内核可能开不了机**。第一次务必先在 fastboot 里准备好 `boot_a.img` 回退

## 失败了怎么把信息给我

Actions 的失败日志里，把这三个文件贴给我就够：

- `build.log`（artifact 里会带）
- 报错那一步的 stderr
- `git apply --check` 的输出（如果卡在补丁）
