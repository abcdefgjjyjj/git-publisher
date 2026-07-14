"""敏感信息扫描与替换模块。

在 staging 副本上执行替换，不修改本地原始文件。

采用"字符串直接替换 + 路径归一化"策略，避免正则转义问题。

安全设计：
- 已知 key 从环境变量读取，**绝不硬编码在源代码中**
- 此文件自身也会被发布到 GitHub，硬编码 key = 公开泄露
- 通用正则模式足以捕获所有 sk- 和 github_pat_ 格式的 key
"""

import os
import re
import shutil
import stat
from pathlib import Path


# ============================================================
# 去品牌化替换表 —— 最先执行
# ============================================================
DEBRAND_TABLE = [
    # ⚠️ 顺序至关重要：具体的长字符串必须在通用的短字符串之前
    # 否则 "llm"→"llm" 会先于 "llm-chat-model" 执行，破坏模型 ID 匹配

    # ── Step 1: API URL 和变量名 ──
    ("https://api.llm-provider.example.com", "https://api.llm-provider.example.com"),
    ("LLM_API_KEY", "LLM_API_KEY"),
    ("LLM_API_URL", "LLM_API_URL"),

    # ── Step 2: 完整模型 ID（带前缀的必须在无前缀之前）──
    ("llm-chat-model", "llm-chat-model"),
    ("llm-chat-model", "llm-chat-model"),
    ("llm-chat-model", "llm-chat-model"),
    ("chat-model", "chat-model"),
    ("chat-model", "chat-model"),
    ("chat-model", "chat-model"),

    # ── Step 3: API Key 前缀 ──
    ("sk-llm-", "sk-llm-"),

    # ── Step 4: AI 品牌名 → 通用词（长匹配在前）──
    ("LLM CLI", "LLM CLI"),
    ("LLM", "LLM"),
    ("LLM", "LLM"),
    ("llm", "llm"),
    ("LLM", "LLM"),
    ("LLM", "LLM"),
    ("llm", "llm"),
    ("LLM", "LLM"),
    ("THE API PROVIDER", "THE API PROVIDER"),
    ("the API provider", "the API provider"),
    ("the API provider", "the API provider"),
]

# ============================================================
# API Key 替换
# ============================================================
# 已知 key 从环境变量加载（防止源代码泄露 key）
# 格式: SANITIZER_KNOWN_KEYS="key1->replacement1,key2->replacement2"
def _load_known_keys_from_env() -> list[tuple[str, str]]:
    """从环境变量加载已知 key 映射。不硬编码任何真实 key。"""
    keys: list[tuple[str, str]] = []
    env_val = os.environ.get("SANITIZER_KNOWN_KEYS", "")
    if env_val:
        for pair in env_val.split(","):
            pair = pair.strip()
            if "->" in pair:
                old, new = pair.split("->", 1)
                keys.append((old.strip(), new.strip()))
    return keys

KNOWN_API_KEYS = _load_known_keys_from_env()

GENERIC_API_KEY_PATTERNS = [
    # (正则, 替换为) —— 捕获所有 sk- 和 github_pat_ 格式的 key
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "YOUR_API_KEY"),
    (re.compile(r"sk-llm-[a-zA-Z0-9_-]{20,}"), "YOUR_API_KEY"),
    (re.compile(r"github_pat_[a-zA-Z0-9_]{20,}"), "YOUR_GITHUB_TOKEN"),
]

# ============================================================
# 路径替换 —— 用路径归一化后的字符串精确替换
# ============================================================
PATH_REPLACEMENTS = [
    # (源路径片段, 替换为)
    ("<project-root>/git-publisher", "<project-root>/git-publisher"),
    ("<project-root>/auto-accept", "<project-root>/auto-accept"),
    ("<project-root>/video-summarizer", "<project-root>/video-summarizer"),
    ("<project-root>/mpv-setup", "<project-root>/mpv-setup"),
    ("<project-root>/disable-autolock", "<project-root>/disable-autolock"),
    ("<project-root>/qt-install", "<project-root>/qt-install"),
    ("<project-root>/win-context-menu-powershell-admin", "<project-root>/win-context-menu-powershell-admin"),
    ("<project-root>", "<project-root>"),
    ("<training-videos-directory>", "<training-videos-directory>"),
    ("python", "python"),
    ("python", "python"),
    ("<python-install-dir>", "<python-install-dir>"),
    ("<qt-install-dir>/5.12.12/msvc2017_64", "<qt-install-dir>/5.12.12/msvc2017_64"),
    ("<qt-install-dir>/5.13.2/msvc2017_64", "<qt-install-dir>/5.13.2/msvc2017_64"),
    ("<qt-install-root>", "<qt-install-root>"),
    ("~", "~"),
    ("<workspace>/", "<workspace>/"),
]

# ============================================================
# 内容级别的脱敏 —— 替换 .md / .py / .yaml 等文本文件中的敏感词
# ============================================================
CONTENT_REPLACEMENTS = [
    # (原始, 替换后)
    ("user", "user"),
    ("user", "user"),
    # 公司内部路径结构
    ("<project-root>", "<project-root>"),   # JSON 转义版
    ("<training-videos-directory>", "<training-videos-directory>"),
]

# ============================================================
# 文件名脱敏 —— 重命名包含品牌名的文件
# ============================================================
FILENAME_REPLACEMENTS = {
    "llm": "llm",
    "LLM": "LLM",
    "LLM": "LLM",
    "llm": "llm",
    "LLM": "LLM",
    "LLM": "LLM",
    "the API provider": "api-provider",
    "the API provider": "API-Provider",
    "THE API PROVIDER": "API-PROVIDER",
}


def _normalize_paths(text: str) -> str:
    """将文本中的 Windows 路径分隔符归一化为正斜杠，方便匹配。"""
    # JSON/Markdown 中的双反斜杠 → 单反斜杠
    t = text.replace("\\\\", "\\")
    # 单反斜杠 → 正斜杠
    t = t.replace("\\", "/")
    return t


class Sanitizer:
    """敏感信息清理器。顺序：去品牌化 → 路径替换 → 内容替换 → API key。

    重要：路径替换必须在内容替换之前执行。
    否则 CONTENT_REPLACEMENTS 中的用户名替换会先把 /Users/realname 变成
    /Users/anon，导致 PATH_REPLACEMENTS 无法匹配含用户名的原始路径。
    """

    def __init__(self):
        pass

    def sanitize_text(self, text: str) -> tuple[str, list[str]]:
        """对文本内容执行脱敏。

        Returns:
            (脱敏后文本, 变更描述列表)
        """
        changes: list[str] = []
        original = text

        # ── Step 1: 去品牌化 ──
        for old, new in DEBRAND_TABLE:
            if old in text:
                text = text.replace(old, new)
                changes.append(f"debrand: {old} → {new}")

        # ── Step 2: 路径替换（必须在内容替换之前！）──
        # 对每种路径格式都尝试替换：正斜杠 / 反斜杠 \ 双反斜杠 \\
        # 对每种路径格式都尝试替换：正斜杠 / 反斜杠 \ 双反斜杠 \\
        for old_path_norm, new_path in PATH_REPLACEMENTS:
            # 正斜杠版（归一化格式）
            if old_path_norm in text:
                text = text.replace(old_path_norm, new_path)
                changes.append(f"path: {old_path_norm} → {new_path}")
            # 反斜杠版（Windows 原生）
            old_path_bs = old_path_norm.replace("/", "\\")
            if old_path_bs != old_path_norm and old_path_bs in text:
                text = text.replace(old_path_bs, new_path)
                changes.append(f"path: {old_path_bs} → {new_path}")
            # 双反斜杠版（JSON 转义 / Markdown 代码块）
            old_path_dbs = old_path_norm.replace("/", "\\\\")
            if old_path_dbs != old_path_norm and old_path_dbs in text:
                text = text.replace(old_path_dbs, new_path)
                changes.append(f"path: {old_path_dbs} → {new_path}")
            # 四反斜杠版（Python 源代码字符串中的路径，如 "<project-root>"）
            old_path_qbs = old_path_norm.replace("/", "\\\\\\\\")
            if old_path_qbs != old_path_norm and old_path_qbs in text:
                text = text.replace(old_path_qbs, new_path)
                changes.append(f"path: {old_path_qbs} → {new_path}")

        # ── Step 3: 内容级精确替换（在路径替换之后，处理剩余的敏感词）──
        for old, new in CONTENT_REPLACEMENTS:
            if old in text:
                text = text.replace(old, new)
                changes.append(f"content: {old[:40]}... → {new}")

        # ── Step 4: API Key 替换 ──
        for old_key, new_key in KNOWN_API_KEYS:
            if old_key in text:
                text = text.replace(old_key, new_key)
                changes.append(f"api_key: known key → {new_key}")

        for pattern, replacement in GENERIC_API_KEY_PATTERNS:
            new_text, count = pattern.subn(replacement, text)
            if count > 0:
                text = new_text
                changes.append(f"api_key: generic pattern matched ({count}x)")

        return text, changes

    def sanitize_file(self, file_path: Path) -> list[str]:
        """对单个文件执行脱敏，原地修改。

        Returns:
            变更描述列表
        """
        if self._is_binary(file_path):
            return []

        try:
            original = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return []

        sanitized, changes = self.sanitize_text(original)
        if changes:
            file_path.write_text(sanitized, encoding="utf-8")
        return changes

    def sanitize_directory(self, root: Path) -> dict[str, list[str]]:
        """递归清理目录下所有文本文件，并重命名敏感文件名。

        Returns:
            {文件相对路径: 变更描述列表}
        """
        results: dict[str, list[str]] = {}
        # 先收集文件列表（避免重命名时迭代器紊乱）
        all_files = list(root.rglob("*"))
        # 第一步：内容脱敏
        for file_path in all_files:
            if file_path.is_file():
                changes = self.sanitize_file(file_path)
                if changes:
                    rel = str(file_path.relative_to(root))
                    results[rel] = changes
        # 第二步：文件名脱敏
        for file_path in sorted(all_files, key=lambda p: len(str(p)), reverse=True):
            if not file_path.exists():
                continue
            new_path = _sanitize_filename(file_path)
            if new_path != file_path:
                rel_old = str(file_path.relative_to(root))
                rel_new = str(new_path.relative_to(root))
                results[rel_old] = results.get(rel_old, []) + [f"renamed: {rel_old} -> {rel_new}"]
        return results

    def verify_clean(self, root: Path) -> list[str]:
        """验证目录中没有残留的敏感信息。

        Returns:
            残留问题列表（空列表 = 干净）
        """
        issues: list[str] = []
        check_patterns = [
            (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "API key"),
            (re.compile(r"github_pat_[a-zA-Z0-9_]{20,}"), "GitHub token"),
            # 通用 Windows 绝对路径检测（sanitize 后不应有任何盘符路径残留）
            (re.compile(r"\b[A-Za-z]:[/\\]"), "Windows absolute path"),
            (re.compile(r"LLM", re.IGNORECASE), "AI brand: LLM"),
            (re.compile(r"LLM(?! Code)", re.IGNORECASE), "AI brand: LLM"),
            (re.compile(r"the API provider", re.IGNORECASE), "AI brand: the API provider"),
            # 可定位厂商的模型 ID（如 chat-model → the API provider LLM）
            (re.compile(r"\b(sonnet|opus|haiku)-\d{1,2}-\d{8}\b", re.IGNORECASE), "identifiable model ID"),
            # API key 前缀泄露提供商（sk-ant = the API provider）
            (re.compile(r"sk-llm-"), "API key vendor prefix"),
            # 中文人名模式：破折号后跟 2-3 个汉字 + 可能英文名
            (re.compile(r"-[一-鿿]{2,4}\b"), "possible Chinese personal name"),
        ]

        for file_path in root.rglob("*"):
            if not file_path.is_file() or self._is_binary(file_path):
                continue
            try:
                content = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            for pattern, label in check_patterns:
                matches = pattern.findall(content)
                if matches:
                    rel = file_path.relative_to(root)
                    issues.append(f"{rel}: {label} found ({len(matches)}x): {matches[:3]}")

        return issues

    @staticmethod
    def _is_binary(file_path: Path) -> bool:
        binary_exts = {
            ".exe", ".dll", ".com", ".pdf", ".png", ".jpg", ".jpeg",
            ".gif", ".ico", ".mp4", ".mp3", ".wav", ".zip", ".7z",
            ".tar", ".gz", ".pyc", ".lnk", ".ttf", ".otf", ".woff",
            ".woff2", ".bin", ".dat",
        }
        if file_path.suffix.lower() in binary_exts:
            return True
        try:
            with open(file_path, "rb") as f:
                return b"\x00" in f.read(1024)
        except OSError:
            return True


# ── 工具函数 ────────────────────────────────────────────────

def _sanitize_filename(file_path: Path) -> Path:
    """重命名包含敏感品牌名的文件/目录。

    Returns:
        重命名后的 Path（原地操作），如果无需重命名则返回原 Path
    """
    name = file_path.name
    new_name = name
    for old, new in FILENAME_REPLACEMENTS.items():
        if old in new_name:
            new_name = new_name.replace(old, new)
    if new_name != name:
        new_path = file_path.with_name(new_name)
        file_path.rename(new_path)
        return new_path
    return file_path


def _remove_readonly(func, path, exc_info):
    """shutil.rmtree 错误处理。"""
    import time
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        try:
            time.sleep(1)
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except OSError:
            pass


def _sync_dirs(src: Path, dst: Path):
    """逐文件同步。"""
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(item, target)
            except (PermissionError, OSError):
                pass


def copy_and_sanitize(
    src: Path,
    dst: Path,
    sanitizer: Sanitizer,
    exclude_patterns: list[str],
    verify: bool = True,
) -> tuple[int, dict[str, list[str]], list[str]]:
    """将源目录复制到 staging，清理并脱敏。

    Returns:
        (排除项数量, {文件: 变更}, 验证问题列表)
    """
    # Step 1: 复制（复制时排除缓存目录，避免递归）
    if dst.exists():
        try:
            shutil.rmtree(dst, onerror=_remove_readonly)
        except (PermissionError, OSError):
            import time
            time.sleep(2)
            try:
                shutil.rmtree(dst, onerror=_remove_readonly)
            except (PermissionError, OSError):
                print(f"  [WARN] Cannot remove old staging for {dst.name}")
    if dst.exists():
        _sync_dirs(src, dst)
    else:
        # 用 ignore 在复制阶段就跳过排除项，避免递归复制
        ignore_func = shutil.ignore_patterns(*exclude_patterns) if exclude_patterns else None
        shutil.copytree(src, dst, ignore=ignore_func)

    # Step 2: 脱敏
    sanitize_results = sanitizer.sanitize_directory(dst)

    # Step 3: 验证
    issues: list[str] = []
    if verify:
        issues = sanitizer.verify_clean(dst)

    return 0, sanitize_results, issues
