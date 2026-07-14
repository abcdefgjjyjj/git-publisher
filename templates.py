"""README 和 LICENSE 模板生成模块。"""

from datetime import date


def generate_readme(name: str, description: str, topics: list[str]) -> str:
    """为工具生成 README.md。"""

    tags = " ".join(f"`{t}`" for t in topics) if topics else ""

    return f"""# {name}

{description}

{tags}

## 安装 / 使用

> 以下为模板内容，请根据实际情况修改。

```bash
# 安装依赖
pip install -r requirements.txt

# 运行
# (请补充具体使用说明)
```

## 功能

- (请补充功能列表)

## 依赖

- (请补充依赖说明)

## License

MIT — 详见 [LICENSE](LICENSE) 文件。
"""


def generate_readme_mpv() -> str:
    """mpv-setup 专用 README（包含 mpv 下载说明）。"""
    return """# mpv Windows 便携播放器配置

基于 [VCB-Studio 科普教程 2.3](https://vcb-s.com/archives/7594) 的 Windows mpv 播放器配置。

`mpv` `video-player` `windows` `configuration`

## 安装

### 1. 下载 mpv

从 [mpv Windows 版下载页](https://sourceforge.net/projects/mpv-player-windows/files/) 下载最新版本。

推荐使用稳定版（如 v0.41.0+），解压到任意目录。

### 2. 放置配置文件

将本仓库的 `mpv.conf` 和 `input.conf` 放到 mpv 目录下的 `portable_config/` 子目录中：

```
mpv/
├── mpv.exe
└── portable_config/
    ├── mpv.conf      ← 主配置
    └── input.conf    ← 快捷键
```

### 3. 注册到右键菜单（可选）

右键 → 用 PowerShell 运行 `register-mpv.ps1`，即可在"打开方式"和"发送到"菜单中使用 mpv。

移动 mpv 目录后重新运行此脚本即可更新注册。

## 配置特点

- **视频渲染**: gpu-next + high-quality 预设
- **硬件解码**: auto-safe（自动选择可用方案）
- **缩放算法**: ewa_lanczossharp
- **流畅播放**: display-resample + interpolation
- **色彩管理**: 自动 ICC 配置
- **字幕**: CJK 字体支持 (Noto Sans CJK SC)

## 快捷键

| 操作 | 快捷键 |
|------|--------|
| 暂停/播放 | 右键 |
| 全屏 | 双击左键 |
| 音量 +/- | 滚轮上/下 |
| 截图 | s (含字幕) / S (纯画面) |
| 加速/减速 | ] / [ |
| AB 循环 | l |

## 参考

- 原教程: https://vcb-s.com/archives/7594
- mpv 官方: https://mpv.io/
- 非官方中文文档: https://hooke007.github.io/unofficial/mpv_profiles.html

## License

MIT — 详见 [LICENSE](LICENSE) 文件。
"""


def generate_license() -> str:
    """生成 MIT LICENSE 文件。"""
    year = date.today().year
    return f"""MIT License

Copyright (c) {year}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def generate_gitignore(extra_patterns: list[str] | None = None) -> str:
    """生成 .gitignore 文件。"""
    patterns = [
        "__pycache__/",
        "*.pyc",
        "*.pyo",
        ".venv/",
        "venv/",
        ".env",
        ".DS_Store",
        "Thumbs.db",
        "*.log",
    ]
    if extra_patterns:
        patterns.extend(extra_patterns)
    return "\n".join(patterns) + "\n"
