"""Git 工具 — 安全封装所有 Git 操作.

审计强化:
- get_diff_name_status: 解析 git diff --name-status 获取精确的文件变更类型
- detect_forbidden_paths: 基于 name-status 的硬拦截
- detect_protected_test_deletion: 基于 D status 的精确检测
"""

from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path
from typing import Any


def _normalize_paths(paths: list[str]) -> list[str]:
    """Deduplicate and normalize file paths: forward slash, no empty, no dups."""
    seen = set()
    result = []
    for p in paths:
        p = p.strip().replace("\\", "/")
        if not p or p in seen:
            continue
        # Skip directory-only paths
        if p.endswith("/"):
            continue
        seen.add(p)
        result.append(p)
    return result


def _run_git(repo_path: str, args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """执行 git 命令并返回 (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return 1, "", "git command not found"
    except subprocess.TimeoutExpired:
        return 1, "", "git command timed out"


def is_git_repo(repo_path: str) -> bool:
    exit_code, _, _ = _run_git(repo_path, ["rev-parse", "--git-dir"])
    return exit_code == 0


def is_worktree_clean(repo_path: str) -> bool:
    exit_code, stdout, _ = _run_git(repo_path, ["status", "--porcelain"])
    if exit_code != 0:
        return False
    return stdout == ""


def get_current_branch(repo_path: str) -> str:
    exit_code, stdout, _ = _run_git(repo_path, ["branch", "--show-current"])
    if exit_code != 0:
        return ""
    return stdout


def is_main_branch(repo_path: str) -> bool:
    branch = get_current_branch(repo_path)
    return branch in ("main", "master")


def create_branch(repo_path: str, branch_name: str) -> tuple[bool, str]:
    exit_code, stdout, stderr = _run_git(repo_path, ["checkout", "-b", branch_name])
    if exit_code != 0:
        return False, stderr or stdout
    return True, f"Created branch: {branch_name}"


def create_worktree(repo_path: str, worktree_path: str, branch_name: str) -> tuple[bool, str]:
    Path(worktree_path).parent.mkdir(parents=True, exist_ok=True)
    exit_code, stdout, stderr = _run_git(
        repo_path, ["worktree", "add", worktree_path, "-b", branch_name]
    )
    if exit_code != 0:
        return False, stderr or stdout
    return True, f"Created worktree at {worktree_path}"


def remove_worktree(repo_path: str, worktree_path: str) -> tuple[bool, str]:
    exit_code, stdout, stderr = _run_git(repo_path, ["worktree", "remove", worktree_path, "--force"])
    if exit_code != 0:
        return False, stderr or stdout
    return True, "Worktree removed"


def checkout_branch(repo_path: str, branch_name: str) -> tuple[bool, str]:
    """Checkout a branch. Returns (success, error_message)."""
    exit_code, stdout, stderr = _run_git(repo_path, ["checkout", branch_name])
    if exit_code != 0:
        return False, stderr or stdout
    return True, f"Checked out branch: {branch_name}"


def delete_branch(repo_path: str, branch_name: str) -> tuple[bool, str]:
    """Delete a local branch. Caller must ensure this is not the current branch."""
    exit_code, stdout, stderr = _run_git(repo_path, ["branch", "-D", branch_name])
    if exit_code != 0:
        return False, stderr or stdout
    return True, f"Deleted branch: {branch_name}"


# ---------------------------------------------------------------------------
# diff 收集
# ---------------------------------------------------------------------------

def get_diff(repo_path: str) -> tuple[str, list[str], int]:
    """收集 git diff (unified).

    Returns:
        (diff_text, changed_files, diff_line_count)
    """
    exit_code, diff_text, _ = _run_git(repo_path, ["diff", "--unified=3"])
    if exit_code != 0:
        return "", [], 0

    exit_code, files_out, _ = _run_git(repo_path, ["diff", "--name-only"])
    changed_files = [f for f in files_out.splitlines() if f.strip()] if files_out.strip() else []
    diff_line_count = len([l for l in diff_text.split("\n") if l and not l.startswith("\\")])

    return diff_text, changed_files, diff_line_count


def get_diff_name_status(repo_path: str) -> dict[str, str]:
    """解析 git diff --name-status，返回 {filepath: status}.

    status: A=Added, M=Modified, D=Deleted, R=Renamed, C=Copied, T=Type changed.

    这是安全检查的硬事实来源。
    """
    exit_code, stdout, _ = _run_git(repo_path, ["diff", "--name-status"])
    if exit_code != 0 or not stdout:
        return {}

    result: dict[str, str] = {}
    for line in stdout.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) == 2:
            status = parts[0][0]  # 取第一个字符 (M, A, D, R, ...)
            filepath = parts[1]
            result[filepath] = status
        elif len(parts) == 1:
            # 某些 git 版本用空格
            sparts = line.split(None, 1)
            if len(sparts) == 2:
                result[sparts[1]] = sparts[0][0]

    return result


def get_staged_diff(repo_path: str) -> str:
    exit_code, stdout, _ = _run_git(repo_path, ["diff", "--cached", "--unified=3"])
    return stdout if exit_code == 0 else ""


def get_untracked_files(repo_path: str) -> dict[str, str]:
    """Return untracked files via git status --porcelain. {filepath: 'A'}

    Directory entries are expanded to their contained files.
    """
    exit_code, stdout, _ = _run_git(repo_path, ["status", "--porcelain"])
    if exit_code != 0:
        return {}
    result: dict[str, str] = {}
    for line in stdout.splitlines():
        if len(line) < 3:
            continue
        # porcelain: "XY path" — after _run_git strip, may lose leading space.
        # Parse as: first 2 non-space chars are status, rest is path after the space.
        stripped = line.strip()
        if len(stripped) < 3:
            continue
        # Find first space: status is everything before it, path is after
        space_idx = stripped.find(" ")
        if space_idx < 1:
            continue
        code = stripped[:space_idx]
        filepath = stripped[space_idx + 1:].strip()
        if not filepath:
            continue
        if code == "??":
            full = Path(repo_path) / filepath
            if full.is_dir():
                # Expand directory to contained regular files
                for f in full.rglob("*"):
                    if f.is_file() and ".git" not in f.parts:
                        rel = str(f.relative_to(repo_path)).replace("\\", "/")
                        result[rel] = "A"
            else:
                result[filepath] = "A"
        elif code[0] in "AMDRC":
            result[filepath] = code[0]
    return result


def _untracked_file_diff(repo_path: str, filepath: str) -> str:
    """Generate a unified diff for a new (untracked) file."""
    full = Path(repo_path) / filepath
    if not full.exists():
        return ""
    try:
        content = full.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    import difflib
    lines = content.splitlines(keepends=True)
    diff = difflib.unified_diff(
        [], lines,
        fromfile=f"/dev/null", tofile=filepath,
        fromfiledate="", tofiledate="",
    )
    return "".join(diff)


def get_worktree_changes(repo_path: str) -> tuple[str, list[str], dict[str, str], int]:
    """Collect ALL worktree changes: tracked diff + untracked files.

    Returns:
        (combined_diff, changed_files, changed_files_status, diff_line_count)
    """
    # Tracked changes
    diff_text, tracked_files, _ = get_diff(repo_path)
    ns = get_diff_name_status(repo_path)

    # Untracked files
    untracked = get_untracked_files(repo_path)

    # Merge: untracked files supplement tracked
    all_status = dict(ns)
    all_files = list(tracked_files)
    extra_diffs = []
    for fp, st in untracked.items():
        if fp not in all_files:
            all_files.append(fp)
        all_status[fp] = st
        ud = _untracked_file_diff(repo_path, fp)
        if ud:
            extra_diffs.append(ud)

    all_files = _normalize_paths(all_files)
    # Normalize all_status keys too
    norm_status: dict[str, str] = {}
    for k, v in all_status.items():
        nk = k.strip().replace("\\", "/")
        if nk and not nk.endswith("/"):
            norm_status[nk] = v
    all_status = norm_status

    combined = diff_text
    if extra_diffs:
        if combined:
            combined += "\n"
        combined += "\n".join(extra_diffs)

    line_count = len([l for l in combined.split("\n") if l and not l.startswith("\\")])
    return combined, all_files, all_status, line_count


def save_diff_patch(repo_path: str, output_path: str) -> bool:
    diff, _, _, _ = get_worktree_changes(repo_path)
    Path(output_path).write_text(diff, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# 安全硬拦截 — 基于 git diff --name-status
# ---------------------------------------------------------------------------

def detect_forbidden_paths(
    changed_files_status: dict[str, str], forbidden_patterns: list[str]
) -> list[str]:
    """基于 --name-status 检测 forbidden paths 变更.

    任何匹配 forbidden pattern 的文件变更（M/A/D/R）都算违规。
    不依赖 prompt 约束，这是硬规则。

    Returns:
        违规文件列表.
    """
    violations = []
    for filepath in changed_files_status:
        for pattern in forbidden_patterns:
            if fnmatch.fnmatch(filepath, pattern):
                violations.append(f"{filepath} [{changed_files_status[filepath]}]")
                break
    return violations


def detect_protected_test_deletion(
    repo_path: str, protected_patterns: list[str]
) -> tuple[list[str], list[str]]:
    """基于 --name-status 检测受保护测试删除和断言降低.

    使用 D (Deleted) status 做精确匹配，不再启发式猜测。

    Returns:
        (deleted_tests, lowered_assertions)
    """
    name_status = get_diff_name_status(repo_path)

    # 精确检测: D status 的文件
    deleted_tests = []
    for filepath, status in name_status.items():
        if status == "D":
            for pattern in protected_patterns:
                if fnmatch.fnmatch(filepath, pattern):
                    deleted_tests.append(filepath)
                    break

    # 断言降低检测: M status 的测试文件中 assert 减少
    lowered: list[str] = []
    modified_test_files = [
        fp for fp, st in name_status.items()
        if st == "M" and any(fnmatch.fnmatch(fp, pat) for pat in protected_patterns)
    ]

    for test_file in modified_test_files:
        exit_code, file_diff, _ = _run_git(repo_path, ["diff", "--unified=3", "--", test_file])
        if exit_code == 0:
            removed = sum(1 for l in file_diff.split("\n") if l.startswith("-") and ("assert" in l.lower() or "verify" in l.lower() or "expect" in l.lower()))
            added = sum(1 for l in file_diff.split("\n") if l.startswith("+") and ("assert" in l.lower() or "verify" in l.lower() or "expect" in l.lower()))
            if removed > 0 and removed > added:
                # 断言减少超过 1 条才触发（容忍 1 条替换）
                if removed - added >= 2:
                    lowered.append(f"{test_file}: -{removed} asserts/expects, +{added}")

    return deleted_tests, lowered


def parse_diff_changed_files(diff_text: str) -> tuple[list[str], dict[str, str]]:
    """Parse unified diff text to extract changed files and their status.

    Returns (changed_files, name_status).
    Status: A=new file (from /dev/null), M=modified, D=deleted.
    """
    import re
    files: list[str] = []
    status: dict[str, str] = {}
    seen = set()

    # Match unified diff headers: --- a/path or --- /dev/null, +++ b/path or +++ /dev/null
    for match in re.finditer(
        r'^--- (?:a/)?(\S+).*?\n\+\+\+ (?:b/)?(\S+)',
        diff_text, re.MULTILINE
    ):
        old_path = match.group(1)
        new_path = match.group(2)

        if old_path == "/dev/null" and new_path != "/dev/null":
            filepath = new_path.replace("\\", "/")
            files.append(filepath)
            status[filepath] = "A"
        elif new_path == "/dev/null" and old_path != "/dev/null":
            filepath = old_path.replace("\\", "/")
            files.append(filepath)
            status[filepath] = "D"
        elif old_path != "/dev/null" and new_path != "/dev/null":
            filepath = new_path.replace("\\", "/")
            if filepath not in seen:
                files.append(filepath)
                status[filepath] = "M"
        seen.add(filepath)

    # Normalize
    return _normalize_paths(files), {k: v for k, v in status.items()
                                     if k.strip() and not k.endswith("/")}


def collect_all_diff_info(repo_path: str) -> dict[str, Any]:
    """一次性收集所有 diff 信息，包括 untracked 文件.

    Returns:
        {diff_text, changed_files, name_status, diff_line_count}
    """
    diff_text, changed_files, name_status, diff_line_count = get_worktree_changes(repo_path)
    return {
        "diff_text": diff_text,
        "changed_files": changed_files,
        "name_status": name_status,
        "diff_line_count": diff_line_count,
    }
