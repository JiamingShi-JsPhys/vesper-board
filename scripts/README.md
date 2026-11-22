# scripts/

在没有对应系统的机器上补出其它平台安装包的辅助脚本。

| 脚本 | 用途 |
|---|---|
| `wsl_build_linux.sh` | 在 WSL Ubuntu 里把源码复制到 `~/vesper-linux`，用 `uv` 建虚拟环境并跑 PyInstaller，产出 `dist/VesperBoard` |
| `wsl_pack_linux.sh` | 对已构建的 Linux 目录做裁剪（去掉多余翻译、devtools pak、非 1.0.0 形象），打成 zip 并复制回本机 `dist/` |

用法（在 WSL 里，不是 PowerShell）：

```bash
sh scripts/wsl_build_linux.sh
sh scripts/wsl_pack_linux.sh
```

脚本用自身位置推导仓库根、用 `$HOME` 推导 WSL 工作目录，换机器不用改路径。
常规打包请看 `packaging/README.md`；这两个只是本机特产不出 Linux 时的替代方案。
