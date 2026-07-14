#!/usr/bin/env python3
"""Git Publisher —— 批量脱敏 + 上传小工具到 GitHub。

使用方式:
  python publish.py --all --ssh          # 全部发布
  python publish.py --all --ssh --update # 增量更新
  python publish.py auto-accept --ssh    # 发布指定工具
  python publish.py --all --dry-run      # 仅预览
"""

import argparse
import os
import subprocess as sp
import sys
from pathlib import Path

import yaml

from sanitizer import Sanitizer, copy_and_sanitize
from repo_manager import (
    GitHubAPI,
    git_push,
    git_add_commit_push,
    resolve_token,
)
from templates import (
    generate_readme,
    generate_readme_mpv,
    generate_license,
    generate_gitignore,
)

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = SCRIPT_DIR / "config.yaml"


def load_config(path=None):
    config_path = Path(path) if path else DEFAULT_CONFIG
    if not config_path.exists():
        print(f"[ERROR] Config file not found: {config_path}")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_tool_info(config, name):
    for tool in config.get("tools", []):
        if tool["name"] == name:
            return tool
    return None


def list_tools(config):
    return config.get("tools", [])


def ensure_staging_dirs(config):
    staging_root = Path(config.get("staging_root", SCRIPT_DIR / "staging"))
    staging_root.mkdir(parents=True, exist_ok=True)
    return staging_root


def prepare_staging(tool_cfg, config, staging_root, sanitizer, dry_run=False):
    tools_root = Path(config.get("tools_root", "."))
    src_dir = tools_root / tool_cfg["name"]
    dst_dir = staging_root / tool_cfg["name"]

    if not src_dir.exists():
        raise FileNotFoundError(f"Tool directory not found: {src_dir}")

    exclude = tool_cfg.get("exclude", [])

    if dry_run:
        print(f"  [DRY-RUN] Would copy {src_dir} -> {dst_dir}")
        print(f"  [DRY-RUN] Would exclude: {exclude}")
        return dst_dir, 0, {}, []

    excluded_count, sanitize_results, issues = copy_and_sanitize(
        src_dir, dst_dir, sanitizer, exclude,
    )

    # Add missing files
    readme_path = dst_dir / "README.md"
    if not readme_path.exists():
        if tool_cfg["name"] == "mpv-setup":
            content = generate_readme_mpv()
        else:
            content = generate_readme(
                name=tool_cfg["name"],
                description=tool_cfg.get("description", ""),
                topics=tool_cfg.get("topics", []),
            )
        readme_path.write_text(content, encoding="utf-8")
        print(f"  [+] Created README.md")

    license_path = dst_dir / "LICENSE"
    if not license_path.exists():
        license_path.write_text(generate_license(), encoding="utf-8")
        print(f"  [+] Created LICENSE")

    gitignore_path = dst_dir / ".gitignore"
    if not gitignore_path.exists():
        extra = []
        if tool_cfg["name"] == "mpv-setup":
            extra = ["mpv/mpv.exe", "mpv/mpv.com", "mpv/d3dcompiler_43.dll"]
        gitignore_path.write_text(generate_gitignore(extra), encoding="utf-8")
        print(f"  [+] Created .gitignore")

    return dst_dir, excluded_count, sanitize_results, issues


def git_init_and_author(repo_dir: Path, username: str):
    """在 repo_dir 中初始化 git 仓库并设置 author。"""
    old = os.getcwd()
    try:
        os.chdir(str(repo_dir))
        if not (repo_dir / ".git").exists():
            sp.run(["git", "init"], check=True, capture_output=True)
            sp.run(["git", "checkout", "-b", "main"], check=True, capture_output=True)
        sp.run(["git", "config", "user.name", username], check=True, capture_output=True)
        sp.run(["git", "config", "user.email", f"{username}@users.noreply.github.com"],
               check=True, capture_output=True)
    finally:
        os.chdir(old)


def git_commit(repo_dir: Path, message: str = "Initial commit") -> bool:
    """在 repo_dir 中添加所有文件并提交。"""
    old = os.getcwd()
    try:
        os.chdir(str(repo_dir))
        sp.run(["git", "add", "-A"], check=True, capture_output=True)
        result = sp.run(["git", "status", "--porcelain"], check=True,
                        capture_output=True, text=True)
        if not result.stdout.strip():
            return False
        sp.run(["git", "commit", "-m", message], check=True, capture_output=True)
        return True
    finally:
        os.chdir(old)


def publish_tool(tool_cfg, config, staging_root, sanitizer, gh, username, token,
                 dry_run=False, update=False, use_ssh=False):
    name = tool_cfg["name"]
    desc = tool_cfg.get("description", "")
    topics = tool_cfg.get("topics", [])
    private = tool_cfg.get("private", False)

    print(f"\n{'=' * 60}")
    print(f"  Publishing: {name}")
    print(f"{'=' * 60}")

    # [1/4] Prepare staging
    print(f"\n[1/4] Preparing staging copy...")
    try:
        staging_dir, excluded, sanitized, issues = prepare_staging(
            tool_cfg, config, staging_root, sanitizer, dry_run,
        )
    except FileNotFoundError as e:
        print(f"  [ERROR] {e}")
        return False

    if not dry_run:
        print(f"  Removed {excluded} cache/excluded items")
        if sanitized:
            total = sum(len(v) for v in sanitized.values())
            print(f"  Sanitized {len(sanitized)} files ({total} changes):")
            for fpath, changes in sanitized.items():
                print(f"    - {fpath}:")
                for c in changes:
                    print(f"      {c}")

    # [2/4] Verify clean
    if not dry_run and issues:
        print(f"\n  [FAIL] {len(issues)} sensitive item(s) remaining!")
        for issue in issues:
            print(f"    - {issue}")
        print(f"\n  Aborting push for {name}.")
        return False
    elif not dry_run:
        print(f"\n[2/4] Verification: CLEAN (no sensitive info)")

    # [3/4] GitHub repo
    print(f"\n[3/4] GitHub repo: {username}/{name}")
    if dry_run:
        print(f"  [DRY-RUN] Would create repo {username}/{name}")
    else:
        try:
            repo_data = gh.create_repo(name, description=desc, topics=topics, private=private)
            clone_url = repo_data.get("clone_url",
                                       f"https://github.com/{username}/{name}.git")
            print(f"  [+] Repo ready: {repo_data.get('html_url', clone_url)}")
        except RuntimeError as e:
            print(f"  [ERROR] {e}")
            clone_url = f"https://github.com/{username}/{name}.git"

    # [4/4] Git
    print(f"\n[4/4] Git commit & push...")
    if dry_run:
        print(f"  [DRY-RUN] Would git push to {username}/{name}")
        return True

    if update:
        committed = git_add_commit_push(
            staging_dir, clone_url, token,
            message=f"Update {name}",
            use_ssh=use_ssh,
            username=username,
        )
        if committed:
            print(f"  [+] Pushed update to {username}/{name}")
        return committed
    else:
        git_init_and_author(staging_dir, username)
        committed = git_commit(staging_dir)
        if not committed:
            print("  [WARN] Nothing to commit")
            return False
        pushed = git_push(staging_dir, clone_url, token, use_ssh=use_ssh)
        if pushed:
            print(f"  [+] Published: https://github.com/{username}/{name}")
        return pushed


def main():
    parser = argparse.ArgumentParser(
        description="Git Publisher",
    )
    parser.add_argument("tools", nargs="*", help="Tool names")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-c", "--config", default=None)
    parser.add_argument("--ssh", action="store_true")
    parser.add_argument("--username", default=None)

    args = parser.parse_args()
    config = load_config(args.config)

    try:
        token = resolve_token(config)
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    username = args.username or config.get("github", {}).get("username", "")
    if not username:
        print("[ERROR] GitHub username not set.")
        sys.exit(1)

    if args.all:
        tool_list = list_tools(config)
    elif args.tools:
        tool_list = [get_tool_info(config, n) for n in args.tools
                     if get_tool_info(config, n)]
    else:
        print("Use --all or specify tool names.")
        return

    if not tool_list:
        print("[ERROR] No tools to publish.")
        sys.exit(1)

    if args.dry_run:
        print("=" * 60)
        print("  DRY RUN MODE")
        print("=" * 60)

    staging_root = ensure_staging_dirs(config)
    sanitizer = Sanitizer()
    gh = GitHubAPI(token)

    success = 0
    fail = 0
    for tool_cfg in tool_list:
        ok = publish_tool(
            tool_cfg, config, staging_root, sanitizer, gh, username, token,
            dry_run=args.dry_run, update=args.update, use_ssh=args.ssh,
        )
        if ok:
            success += 1
        else:
            fail += 1

    print(f"\n{'=' * 60}")
    print(f"  Done: {success} succeeded, {fail} failed")
    print(f"{'=' * 60}")
    if not args.dry_run and success > 0:
        print(f"\nVisit: https://github.com/{username}")


if __name__ == "__main__":
    main()
