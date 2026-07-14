# Git Publisher - 状态文档

## 任务目标
将 `<project-root>` 下的全部小工具脱敏后批量上传到 GitHub。

## ✅ 已完成

### 发布结果

| # | 工具 | GitHub | 脱敏文件 | 变更数 |
|---|------|--------|----------|--------|
| 1 | auto-accept | https://github.com/abcdefgjjyjj/auto-accept | 6 | 23 |
| 2 | disable-autolock | https://github.com/abcdefgjjyjj/disable-autolock | 0 | 0 |
| 3 | mpv-setup | https://github.com/abcdefgjjyjj/mpv-setup | 1 | 1 |
| 4 | video-summarizer | https://github.com/abcdefgjjyjj/video-summarizer | 16 | 47 |
| 5 | win-context-menu-powershell-admin | https://github.com/abcdefgjjyjj/win-context-menu-powershell-admin | 0 | 0 |

### 脱敏内容

**去品牌化** (全部工具):
- LLM / llm / LLM → LLM / llm
- LLM CLI → LLM CLI
- LLM / llm → LLM / llm
- the API provider / the API provider → the API provider
- 相关 API URL → 占位符

**API Key 清除**:
- 特定 key `sk-xxxx...` → YOUR_API_KEY (从环境变量加载，2个工具)
- GitHub PAT → YOUR_GITHUB_TOKEN
- 通用 sk- 格式匹配清理

**路径清除**:
- `<project-root>\...` → `<project-root>/...`
- `<training-videos-directory>` → `<training-videos-directory>`
- `<python-install-dir>\...` → `python`
- `<qt-install-root>\...` → `<qt-install-root>`
- `~` → `~`

**缓存清理**:
- auto-accept: `__pycache__/`, `*.log`, `.llm/`
- mpv-setup: `cache/` (12 shader), `watch_later/` (25 history), mpv binaries
- video-summarizer: `__pycache__/`, `*.log`, `tmp/`

**补全文件**:
- 全部工具补齐 README.md, LICENSE (MIT), .gitignore

### 技术实现

- 脱敏逻辑: `sanitizer.py` — 字符串精确替换，避免正则转义问题
- 路径替换: 支持正斜杠、反斜杠、双反斜杠三种格式
- 推送验证: 每个工具推送前自动扫描残留敏感信息，发现问题拒绝推送
- Git 作者: 统一设为 abcdefgjjyjj
- 推送方式: SSH (因 HTTPS 被公司防火墙拦截)

### 使用方式

```bash
# 全部发布
python publish.py --all --ssh

# 增量更新
python publish.py --all --ssh --update

# 单个工具
python publish.py auto-accept --ssh

# 预览
python publish.py --all --dry-run
```

## 已知问题

- 本地原始文件完整保留，未做任何修改
- 推送前验证规则覆盖了主要敏感信息类型，但可能漏掉个性化内容

## 🔒 安全事件：API Key 泄露 (2026-07-14)

### 事件描述
`sanitizer.py` 的 `KNOWN_API_KEYS` 表中硬编码了真实 LLM API key (`sk-7015b8...`) 和 GitHub PAT。当 git-publisher 自己被发布到 GitHub 时，sanitizer 未能自清洁（PAT 被字符串拼接规避了替换匹配），导致真实 key 公开暴露在 `abcdefgjjyjj/git-publisher` 仓库的 `sanitizer.py` 中。

### 时间线
| 时间 | 事件 |
|------|------|
| 2026-07-09 | sanitizer 增强 commit 引入硬编码 key 并发布到 GitHub |
| 2026-07-12~13 | 周末期间 key 额度耗尽（疑似被外部使用） |
| 2026-07-14 | 审计发现泄露，key 已 revoke，GitHub 仓库已清理 |

### 修复措施
1. **revoke 泄露的 LLM API key** — 已在 LLM 后台移除
2. **删除并重建 GitHub 仓库** — 彻底清除 git 历史中的孤儿 blob
3. **移除硬编码 key** — `KNOWN_API_KEYS` 改为从环境变量 `SANITIZER_KNOWN_KEYS` 加载
4. **修复 DEBRAND_TABLE 顺序** — 模型 ID 替换移到品牌名替换之前，防止 `llm-chat-model` → `llm-chat-model` 残留
5. **补充 haiku/opus 模型 ID** — 之前仅覆盖了 sonnet，补充了 chat-model 和 chat-model
6. **清理本地 git 历史** — 使用 git filter-branch 清除所有历史提交中的 key
7. **全面扫描 12 个 GitHub 仓库** — 确认所有仓库（含私有）当前无 sk- 泄露

### 教训
- **永远不要硬编码 API key 在源代码中**，即使作为"替换规则表"也不行——这个文件本身会被发布
- 环境变量是唯一安全的 key 传递方式
- 发布流程应包含"自清洁测试"——检查 sanitizer 自身的源文件是否会被泄露
