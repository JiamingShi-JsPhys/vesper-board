# docs/audit/

DeepSec 的原始扫描产物，保留下来是为了让 `../security-audit.md` 的结论可追溯。

| 文件 | 内容 |
|---|---|
| `deepsec-src-2026-11-21.json` | 源码树 `shield scan --layer all --no-remote-l3` 的 JSON 结果：1 条 medium |
| `deepsec-src-2026-11-21-rerun.json` | 同一范围的复扫，内容一致（只差时间戳） |
| `deepsec-src-2026-11-21.log` | 上面对应的表格输出 |
| `deepsec-dist-2026-11-21.log` | 解包后 `Vesper_Board_1.0.0` 发行目录的扫描：0 findings |

唯一的 medium 在 `tools/paper_gen.py:81`（开发期出图脚本，URL 由本机调用方给出），
`tools/` 不进发行包，所以发行目录的复扫是干净的。判定依据见 `../../SECURITY.md`。
