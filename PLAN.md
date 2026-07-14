# Git Publisher - 小工具批量上传 GitHub 工具

## 任务目标

将 `<project-root>` 下的全部小工具批量上传到 GitHub，具备：
1. 敏感信息自动抹除（API key、本地路径等）
2. 缓存/临时文件自动清理
3. README.md / LICENSE 自动补齐
4. **不修改本地原始文件**
5. 支持自动 commit 和增量更新

## 工具分析结果

| 工具 | 类型 | 敏感信息 | 缓存 | README | LICENSE |
|------|------|----------|------|--------|---------|
| auto-accept | Python CLI | API key, 本地路径 | `__pycache__/`, `*.log` | ✅ | ❌ |
| disable-autolock | PowerShell 脚本 | 无 | 无 | ❌ | ❌ |
| mpv-setup | 便携软件+配置 | 无(配置内无路径) | `cache/`, `watch_later/` | ❌ | ❌ |
| qt-install | 纯文档(STATUS.md) | Qt安装路径 | 无 | ❌ | ❌ |
| video-summarizer | Python管线 | API key, `<training-videos-directory>` | `__pycache__/`, `*.log`, `tmp/` | ❌ | ❌ |
| win-context-menu-powershell-admin | 注册表脚本 | 无 | 无 | ❌ | ❌ |

## 技术方案

### 架构：staging 目录模式

```
原始工具目录 (不改动)  ──copy──>  staging 目录  ──sanitize──>  GitHub
                                      │
                                      ├─ 清理缓存
                                      ├─ 替换敏感信息
                                      ├─ 生成 README/LICENSE
                                      └─ git init/commit/push
```

- 每个工具独立 copy 到 staging（临时目录）
- 在 staging 上做所有清理和脱敏
- push 到 GitHub 对应 repo
- staging 目录可保留用于增量更新（`--update` 模式）

### 敏感信息替换规则

| 原始内容 | 替换为 |
|----------|--------|
| `sk-xxxx...` (具体 key 从环境变量读取) | `YOUR_API_KEY` |
| 其他 `sk-[a-z0-9]{32,}` API keys | `YOUR_API_KEY` |
| `<project-root>\\...` 绝对路径 | 相对路径或占位符 |
| `<training-videos-directory>` | `PATH_TO_TRAINING_VIDEOS` |
| `python` | `python` |
| `<qt-install-root>\\Qt5.12.12\\...` | Qt 安装路径说明 |
| 含 `user` 或 `lx` 的用户目录路径 | `~` 或通用路径 |

### 缓存清理列表

- `__pycache__/` 目录
- `*.pyc` 文件
- `*.log` 文件（保留 `.gitkeep` 如需要）
- `tmp/` 目录及内容
- `watch_later/` 目录（mpv 播放历史）
- `cache/` 目录（mpv shader cache）
- `.llm/` 目录（项目级配置包含本地路径）

### GitHub 操作

由于 `gh` CLI 不可用，使用 GitHub REST API：
- 创建 repo：`POST /user/repos`
- 认证：Personal Access Token (classic) 或 `GITHUB_TOKEN`
- Git push：HTTPS remote + token 认证

### 文件生成模板

每个缺少 README 的工具生成包含：
- 工具名称和简介
- 功能列表
- 安装/使用方法
- 依赖说明
- License 信息

LICENSE 默认使用 MIT。

## 实现计划

```
git-publisher/
├── PLAN.md              # 本文件
├── STATUS.md            # 进度状态
├── README.md            # 本工具的使用说明
├── config.yaml          # 工具注册表 + GitHub 配置
├── requirements.txt     # Python 依赖
├── publish.py           # CLI 入口
├── sanitizer.py         # 敏感信息扫描与替换
├── repo_manager.py      # Git 操作 + GitHub API
├── templates.py         # README / LICENSE 模板
└── .gitignore
```

### publish.py CLI

```bash
# 全部发布（首次）
python publish.py --all

# 发布指定工具
python publish.py auto-accept video-summarizer

# 更新已发布的工具（增量）
python publish.py --update --all

# 仅预览变更，不实际上传
python publish.py --all --dry-run

# 指定 GitHub 用户名
python publish.py --all --github-user myuser
```

## 关键决策

- **staging 目录位置**：`%TEMP%/git-publish-staging/`，避免在项目目录下留痕迹
- **GitHub Token 获取**：优先环境变量 `GITHUB_TOKEN`，次选 `config.yaml` 中的 `github.token`
- **每个工具独立 repo**：而非 monorepo，便于独立 star/fork
- **qt-install 也发布**：虽然是纯文档，但有参考价值（aqtinstall 用法、Qt 版本选择）

## 下一步

1. 用户确认方案
2. 编写代码实现
3. 用户提供 GitHub username + token
4. 测试运行
