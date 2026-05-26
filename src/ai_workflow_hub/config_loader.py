"""配置加载器 — 加载 YAML 配置、环境变量、.env 文件."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


class TaskQueueCorruptError(Exception):
    """tasks.yaml 损坏 — 不可恢复，不应静默覆盖."""


def _hub_dir() -> Path:
    """ai-workflow-hub 根目录."""
    return Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# File lock for tasks.yaml read-modify-write
# ---------------------------------------------------------------------------

_TASKS_LOCKFILE = _hub_dir() / "tasks.yaml.lock"


@contextmanager
def tasks_lock(timeout: float = 5.0):
    """跨进程锁 — 保护 tasks.yaml 的读-改-写操作.

    使用 O_EXCL 创建 lockfile 实现。超时后抛出 TimeoutError。
    """
    deadline = time.time() + timeout
    fd = None
    try:
        while time.time() < deadline:
            try:
                fd = os.open(str(_TASKS_LOCKFILE),
                            os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                time.sleep(0.05)
        else:
            raise TimeoutError(
                f"Failed to acquire tasks.yaml lock within {timeout}s")
        yield
    finally:
        if fd is not None:
            os.close(fd)
            try:
                _TASKS_LOCKFILE.unlink()
            except OSError:
                pass


def load_yaml(path: str | Path) -> dict[str, Any]:
    """加载 YAML 文件."""
    full = Path(path)
    if not full.is_absolute():
        full = _hub_dir() / path
    if full.exists():
        with open(full, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if data else {}
    return {}


def save_yaml(path: str | Path, data: dict[str, Any]) -> None:
    """保存 YAML 文件（原子写入：temp + fsync + replace）."""
    full = Path(path)
    if not full.is_absolute():
        full = _hub_dir() / path
    full.parent.mkdir(parents=True, exist_ok=True)

    tmp = full.parent / f"{full.name}.{os.getpid()}.{int(time.time()*1_000_000)}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True,
                       default_flow_style=False, sort_keys=False)
        f.flush()
        os.fsync(f.fileno())

    # Atomic replace — Windows 下有时目标被占用，短重试
    for attempt in range(3):
        try:
            tmp.replace(full)
            break
        except PermissionError:
            if attempt < 2:
                time.sleep(0.1 * (attempt + 1))
            else:
                raise


def load_tasks_safe() -> dict[str, Any]:
    """加载 tasks.yaml — 损坏时抛异常而非返回空字典."""
    full = _hub_dir() / "tasks.yaml"
    if not full.exists():
        return {}
    try:
        with open(full, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise TaskQueueCorruptError(
            f"tasks.yaml is corrupted and cannot be parsed: {e}"
        ) from e
    if not isinstance(data, dict):
        raise TaskQueueCorruptError(
            f"tasks.yaml root must be a dict, got {type(data).__name__}"
        )
    return data


def init_env() -> dict[str, str]:
    """加载 .env 并返回环境变量快照."""
    env_path = _hub_dir() / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    return dict(os.environ)


def get_env(key: str, default: str = "") -> str:
    """安全读取环境变量."""
    return os.environ.get(key, default)


def get_model_config() -> dict[str, Any]:
    """加载模型路由配置."""
    return load_yaml("configs/model-router.yaml")


def get_risk_policy() -> dict[str, Any]:
    """加载风险策略配置."""
    return load_yaml("configs/risk-policy.yaml")


def get_execution_policy() -> dict[str, Any]:
    """加载执行策略配置."""
    return load_yaml("configs/execution-policy.yaml")


def get_projects() -> dict[str, Any]:
    """加载 projects.yaml."""
    return load_yaml("projects.yaml")


def get_tasks() -> dict[str, Any]:
    """加载 tasks.yaml — 损坏时抛 TaskQueueCorruptError，不返回空字典."""
    return load_tasks_safe()


def save_projects(data: dict[str, Any]) -> None:
    """保存 projects.yaml."""
    save_yaml("projects.yaml", data)


def save_tasks(data: dict[str, Any]) -> None:
    """保存 tasks.yaml（原子写入）."""
    save_yaml("tasks.yaml", data)


def load_project_workflow_config(project_path: str, config_filename: str = ".aiworkflow.yaml") -> dict[str, Any]:
    """加载业务项目的 .aiworkflow.yaml."""
    config_path = Path(project_path) / config_filename
    if not config_path.exists():
        return {}
    return load_yaml(str(config_path))


def find_workflow_file(project_path: str) -> str | None:
    """查找项目 WORKFLOW.md。

    优先级: .aiworkflow/WORKFLOW.md > WORKFLOW.md > None.
    """
    root = Path(project_path)
    candidates = [root / ".aiworkflow" / "WORKFLOW.md", root / "WORKFLOW.md"]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def load_workflow_text(project_path: str, max_chars: int = 4000) -> str:
    """读取 WORKFLOW.md 内容，capped."""
    path = find_workflow_file(project_path)
    if not path:
        return ""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n... (truncated at {max_chars} chars, {len(text)} total)"
    return text
