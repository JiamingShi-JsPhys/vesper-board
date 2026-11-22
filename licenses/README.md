# licenses/

随安装包分发的许可证全文：

| 文件 | 对应组件 |
|---|---|
| `LGPL-3.0.txt` | PySide6 / Qt（含 QtWebEngine 的 Qt 部分） |
| `Apache-2.0.txt` | requests |
| `PSF-2.0.txt` | Python 3.12 运行时 |

文本取自官方发布：<https://www.gnu.org/licenses/lgpl-3.0.txt>、
<https://www.apache.org/licenses/LICENSE-2.0.txt>、
<https://github.com/python/cpython/blob/3.12/LICENSE>。

QtWebEngine 内含的 Chromium 第三方声明由 Qt 官方发行版提供；
本项目未修改这些组件，onedir 布局允许用户用同版本 Qt 库替换
`_internal/PySide6/` 下的动态库。
