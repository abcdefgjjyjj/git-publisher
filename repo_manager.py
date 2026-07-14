"""Git 操作和 GitHub API 模块。"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import requests


# ── GitHub API ─────────────────────────────────────────────────

class GitHubAPI:
    """GitHub REST API 封装。"""

    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        self.base_url = "https://api.github.com"

    def repo_exists(self, owner: str, repo: str) -> bool:
        """检查仓库是否已存在。"""
        url = f"{self.base_url}/repos/{owner}/{repo}"
        resp = self.session.get(url)
        return resp.status_code == 200

    def create_repo(
        self,
        name: str,
        description: str = "",
        private: bool = False,
        topics: list[str] | None = None,
    ) -> dict:
        """创建 GitHub 仓库。

        Returns:
            API 返回的 repo 数据，包含 clone_url 等字段

        Raises:
            RuntimeError: 创建失败
        """
        url = f"{self.base_url}/user/repos"
        payload = {
            "name": name,
            "description": description,
            "private": private,
            "has_issues": True,
            "has_projects": False,
            "has_wiki": False,
            "auto_init": False,  # 我们手动 push
        }
        resp = self.session.post(url, json=payload)

        if resp.status_code == 422:
            # 仓库已存在，获取其信息
            username = self._get_username()
            existing = self.session.get(f"{self.base_url}/repos/{username}/{name}")
            if existing.status_code == 200:
                return existing.json()

        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Failed to create repo '{name}': HTTP {resp.status_code}\n"
                f"{resp.text}"
            )

        repo_data = resp.json()

        # 设置 topics（需要单独 API 调用）
        if topics:
            self.set_topics(name, topics)

        return repo_data

    def set_topics(self, repo: str, topics: list[str]):
        """设置仓库 topics。"""
        username = self._get_username()
        url = f"{self.base_url}/repos/{username}/{repo}/topics"
        payload = {"names": topics}
        resp = self.session.put(
            url,
            json=payload,
            headers={"Accept": "application/vnd.github.mercy-preview+json"},
        )
        if resp.status_code != 200:
            print(f"  [WARN] Failed to set topics: {resp.status_code} {resp.text}")

    def _get_username(self) -> str:
        """获取当前认证用户的用户名。"""
        resp = self.session.get(f"{self.base_url}/user")
        if resp.status_code == 200:
            return resp.json()["login"]
        raise RuntimeError(f"Failed to get user info: HTTP {resp.status_code}")


# ── Git 操作 ───────────────────────────────────────────────────

def resolve_token(config: dict) -> str:
    """从环境变量或配置文件获取 GitHub token。"""
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        return token
    token = config.get("github", {}).get("token", "")
    if token and not token.startswith("github_pat_") and not token.startswith("ghp_"):
        print("[WARN] Token format looks unusual, may not work")
    if not token:
        raise RuntimeError(
            "GitHub token not found. Set GITHUB_TOKEN environment variable\n"
            "or add it to config.yaml under github.token"
        )
    return token


def git_init_and_commit(repo_dir: Path, message: str = "Initial commit") -> bool:
    """在目录中初始化 git 仓库并提交。

    Returns:
        True 表示成功（有内容可提交），False 表示无变更
    """
    old_cwd = os.getcwd()
    try:
        os.chdir(str(repo_dir))

        # 初始化（如果还没有 .git）
        if not (repo_dir / ".git").exists():
            subprocess.run(
                ["git", "init"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "checkout", "-b", "main"],
                check=True, capture_output=True,
            )

        # 添加所有文件
        subprocess.run(
            ["git", "add", "-A"],
            check=True, capture_output=True,
        )

        # 检查是否有变更
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True, capture_output=True, text=True,
        )
        if not status.stdout.strip():
            return False  # 无变更

        subprocess.run(
            ["git", "commit", "-m", message],
            check=True, capture_output=True,
        )
        return True
    finally:
        os.chdir(old_cwd)


def git_push(
    repo_dir: Path,
    remote_url: str,
    token: str = "",
    branch: str = "main",
    max_retries: int = 3,
    use_ssh: bool = False,
    ssh_user: str = "git",
) -> bool:
    """推送到 GitHub（含自动重试）。

    支持两种认证方式：
    - HTTPS: https://<token>@github.com/<owner>/<repo>.git
    - SSH:   git@github.com:<owner>/<repo>.git

    Returns:
        True 表示推送成功
    """
    import time

    old_cwd = os.getcwd()
    try:
        os.chdir(str(repo_dir))

        if use_ssh:
            # 将 HTTPS URL 转为 SSH URL
            # https://github.com/owner/repo.git → git@github.com:owner/repo.git
            auth_url = remote_url.replace(
                "https://github.com/",
                f"{ssh_user}@github.com:"
            )
            # 去掉尾部 .git 如果存在（SSH 格式可以有也可以没有）
            if not auth_url.endswith(".git"):
                # 确保有 .git 后缀（git 需要）
                pass
        else:
            # 注入 token 到 HTTPS URL
            auth_url = remote_url.replace(
                "https://",
                f"https://{token}@"
            )

        # 检查是否已有 remote
        remotes = subprocess.run(
            ["git", "remote"], check=True, capture_output=True, text=True,
        )
        if "origin" in remotes.stdout:
            subprocess.run(
                ["git", "remote", "set-url", "origin", auth_url],
                check=True, capture_output=True,
            )
        else:
            subprocess.run(
                ["git", "remote", "add", "origin", auth_url],
                check=True, capture_output=True,
            )

        print(f"  Pushing to {auth_url.split('@')[-1] if '@' in auth_url else auth_url} ...")

        # 推送到 main 分支（含重试）
        for attempt in range(1, max_retries + 1):
            try:
                subprocess.run(
                    ["git", "push", "-u", "origin", branch, "--force"],
                    check=True, capture_output=True, timeout=120,
                )
                return True
            except subprocess.CalledProcessError as e:
                stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
                if "Everything up-to-date" in stderr:
                    return True
                if attempt < max_retries:
                    wait = attempt * 3
                    print(f"  [RETRY] Push attempt {attempt} failed, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"  [ERROR] Git push failed after {max_retries} attempts: {e}")
                    if stderr:
                        print(f"  {stderr[:300]}")
                    return False
            except subprocess.TimeoutExpired:
                if attempt < max_retries:
                    wait = attempt * 5
                    print(f"  [RETRY] Push timed out (attempt {attempt}), retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"  [ERROR] Git push timed out after {max_retries} attempts")
                    return False

        return False
    finally:
        os.chdir(old_cwd)


def git_add_commit_push(
    repo_dir: Path,
    remote_url: str,
    token: str = "",
    message: str = "Update",
    branch: str = "main",
    use_ssh: bool = False,
    username: str = "user",
) -> bool:
    """增量更新：init(if needed) → add → commit → push。"""
    old_cwd = os.getcwd()
    try:
        os.chdir(str(repo_dir))

        # 如果 .git 不存在（例如 staging 被重建），先 init
        if not (repo_dir / ".git").exists():
            subprocess.run(
                ["git", "init"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "checkout", "-b", branch],
                check=True, capture_output=True,
            )

        # 始终设置匿名 git author，防止本地身份泄露
        subprocess.run(
            ["git", "config", "user.name", username],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", f"{username}@users.noreply.github.com"],
            check=True, capture_output=True,
        )

        subprocess.run(
            ["git", "add", "-A"],
            check=True, capture_output=True,
        )

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True, capture_output=True, text=True,
        )
        if not status.stdout.strip():
            print("  No changes to commit.")
            return False

        subprocess.run(
            ["git", "commit", "-m", message],
            check=True, capture_output=True,
        )

        # push
        return git_push(repo_dir, remote_url, token, branch, use_ssh=use_ssh)
    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] Git operation failed: {e}")
        if e.stderr:
            print(f"  {e.stderr.decode('utf-8', errors='replace')}")
        return False
    finally:
        os.chdir(old_cwd)
