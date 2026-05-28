"""aihub CLI — Typer 命令行入口.

审计强化:
- doctor: 增加 opencode models 检查 + codex exec --help 检查
- --run-tests flag: dry-run 下显式执行测试
- 使用 compile_graph 的 checkpointer (thread_id = run_id)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

import yaml as _yaml

from .config_loader import (
    init_env,
    load_project_workflow_config,
    get_execution_policy,
    get_risk_policy,
    _hub_dir,
)
from .model_router import get_model_for_task, validate_all_models
from .project_registry import list_projects, find_project, validate_project, add_project
from .task_queue import list_tasks, find_task, add_task
from .run_store import create_run_dir, save_run_file, save_run_json, list_runs, get_run_report
from .schemas import WorkflowState

app = typer.Typer(
    name="aihub",
    help="稳定优先的多项目 AI 自动化闭环开发系统",
    no_args_is_help=True,
)

console = Console()


# ============================================================
# project 命令
# ============================================================

project_app = typer.Typer(help="项目管理")
app.add_typer(project_app, name="project")


@project_app.command("list")
def project_list():
    init_env()
    projects = list_projects()
    if not projects:
        console.print("[yellow]projects.yaml 中没有项目[/yellow]")
        return

    table = Table(title="Registered Projects")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Path")
    table.add_column("Priority")
    table.add_column("Enabled")

    for p in projects:
        table.add_row(
            p.get("id", ""),
            p.get("name", ""),
            p.get("path", ""),
            p.get("priority", "medium"),
            "Yes" if p.get("enabled", True) else "No",
        )

    console.print(table)


@project_app.command("validate")
def project_validate(project_id: str = typer.Option(..., "--project", "-p", help="项目 ID")):
    init_env()
    is_valid, messages = validate_project(project_id)

    console.print(f"\n[bold]Project: {project_id}[/bold]")
    console.print("-" * 40)

    for msg in messages:
        if msg.startswith("ERROR"):
            console.print(f"  [red]{msg}[/red]")
        elif msg.startswith("WARNING"):
            console.print(f"  [yellow]{msg}[/yellow]")
        else:
            console.print(f"  [dim]{msg}[/dim]")

    if is_valid:
        console.print(f"\n[green]Validation PASSED[/green]")
    else:
        console.print(f"\n[red]Validation FAILED — {len([m for m in messages if m.startswith('ERROR')])} error(s)[/red]")

    raise typer.Exit(0 if is_valid else 1)


# ============================================================
# task 命令
# ============================================================

task_app = typer.Typer(help="任务管理")
app.add_typer(task_app, name="task")


@task_app.command("list")
def task_list(status: Optional[str] = typer.Option(None, "--status", "-s")):
    init_env()
    tasks = list_tasks(status)

    if not tasks:
        console.print("[yellow]没有任务.[/yellow]")
        return

    table = Table(title="Task Queue")
    table.add_column("ID", style="cyan")
    table.add_column("Title")
    table.add_column("Risk")
    table.add_column("Priority")
    table.add_column("Status")
    table.add_column("Last Run")

    for t in tasks:
        risk_style = {"low": "green", "medium": "yellow", "high": "red"}.get(t.get("risk", ""), "")
        status_style = {"queued": "dim", "running": "blue", "passed": "green", "failed": "red", "blocked": "red", "human_required": "yellow", "cancelled": "dim"}.get(t.get("status", ""), "")
        lr = t.get("last_run_id", "")
        table.add_row(
            t.get("id", ""),
            t.get("title", "")[:50],
            f"[{risk_style}]{t.get('risk', '')}[/{risk_style}]",
            t.get("priority", "normal"),
            f"[{status_style}]{t.get('status', '')}[/{status_style}]",
            lr[-16:] if lr else "-",
        )

    console.print(table)


@task_app.command("mark")
def task_mark(
    task_id: str = typer.Argument(..., help="任务 ID"),
    status: str = typer.Argument(..., help="状态: queued | cancelled | ..."),
    reason: str = typer.Option("", "--reason", "-r", help="阻塞原因"),
):
    """标记任务状态."""
    init_env()
    valid = ("queued", "cancelled", "blocked", "human_required")
    if status not in valid:
        console.print(f"[red]无效状态: {status}。允许: {', '.join(valid)}[/red]")
        raise typer.Exit(1)
    from .task_queue import mark_task_finished
    ok = mark_task_finished(task_id, status, blocked_reason=reason)
    if ok:
        console.print(f"[green]{task_id} → {status}[/green]")
    else:
        console.print(f"[red]任务 '{task_id}' 不存在[/red]")


@task_app.command("pause")
def task_pause(task_id: str = typer.Argument(..., help="任务 ID")):
    """暂停 queued 任务."""
    init_env()
    from .task_queue import pause_task
    if pause_task(task_id):
        console.print(f"[green]{task_id} → paused[/green]")
    else:
        console.print(f"[red]无法暂停: {task_id} (仅 queued 状态可暂停)[/red]")


@task_app.command("resume")
def task_resume(task_id: str = typer.Argument(..., help="任务 ID")):
    """恢复 paused 任务."""
    init_env()
    from .task_queue import resume_task
    if resume_task(task_id):
        console.print(f"[green]{task_id} → queued[/green]")
    else:
        console.print(f"[red]无法恢复: {task_id} (仅 paused 状态可恢复)[/red]")


@task_app.command("cancel")
def task_cancel(task_id: str = typer.Argument(..., help="任务 ID")):
    """取消任务."""
    init_env()
    from .task_queue import cancel_task
    if cancel_task(task_id):
        console.print(f"[green]{task_id} → cancelled[/green]")
    else:
        console.print(f"[red]无法取消: {task_id}[/red]")


@task_app.command("archive")
def task_archive(task_id: str = typer.Argument(..., help="任务 ID")):
    """归档已完成/已取消任务."""
    init_env()
    from .task_queue import archive_task
    if archive_task(task_id):
        console.print(f"[green]{task_id} → archived[/green]")
    else:
        console.print(f"[red]无法归档: {task_id} (仅 passed/cancelled/blocked/failed 可归档)[/red]")


@task_app.command("retry")
def task_retry(task_id: str = typer.Argument(..., help="任务 ID")):
    """重新排队任务."""
    init_env()
    from .task_queue import mark_task_retry, find_task
    ok = mark_task_retry(task_id)
    if ok:
        t = find_task(task_id)
        rc = t.get("retry_count", 0) if t else 0
        console.print(f"[green]{task_id} → queued (retry #{rc})[/green]")
    else:
        console.print(f"[red]任务 '{task_id}' 不存在[/red]")


@task_app.command("add")
def task_add(
    project_id: str = typer.Option(..., "--project", "-p", help="项目 ID"),
    title: str = typer.Option(..., "--title", "-t", help="任务标题"),
    description: str = typer.Option("", "--description", "-d", help="任务描述"),
    risk: str = typer.Option("medium", "--risk", "-r", help="风险等级: low | medium | high"),
):
    init_env()

    if risk not in ("low", "medium", "high"):
        console.print(f"[red]无效的风险等级: {risk}。必须为 low, medium 或 high[/red]")
        raise typer.Exit(1)

    project = find_project(project_id)
    if not project:
        console.print(f"[red]项目 '{project_id}' 不在注册表中。先执行: aihub project validate[/red]")
        raise typer.Exit(1)

    task_id = add_task(project_id, title, description, risk)
    console.print(f"[green]任务已添加: {task_id}[/green]")


# ============================================================
# run 命令
# ============================================================

run_app = typer.Typer(help="运行管理")
app.add_typer(run_app, name="run")


@run_app.command("start")
def run_start(
    project_id: str = typer.Option(..., "--project", "-p"),
    task_id: str = typer.Option(..., "--task", "-t"),
    apply_changes: bool = typer.Option(False, "--apply", help="显式允许真实代码修改"),
    run_tests: bool = typer.Option(False, "--run-tests", help="dry-run 下也执行测试命令"),
    coding_backend: str = typer.Option("", "--coding-backend", help="coding agent backend: opencode | claude"),
):
    """运行工作流。默认 dry-run。"""
    init_env()
    _execute_run(project_id, task_id, apply_changes, run_tests, coding_backend)


@run_app.command("all")
def run_all(
    risk: Optional[str] = typer.Option(None, "--risk", "-r", help="按风险等级过滤: low | medium | high"),
):
    init_env()

    tasks = list_tasks("pending")
    if risk:
        tasks = [t for t in tasks if t.get("risk") == risk]

    if not tasks:
        console.print("[yellow]没有待执行的任务[/yellow]")
        return

    risk_order = {"low": 0, "medium": 1, "high": 2}
    tasks.sort(key=lambda t: risk_order.get(t.get("risk", "medium"), 1))

    console.print(f"[bold]将串行运行 {len(tasks)} 个任务（默认 dry-run）[/bold]\n")

    for i, task in enumerate(tasks, 1):
        console.print(f"\n{'='*60}")
        console.print(f"[bold]任务 {i}/{len(tasks)}: {task['title']}[/bold]")
        console.print(f"{'='*60}")

        try:
            _execute_run(task["project_id"], task["id"], apply_changes=False, run_tests=False)
        except typer.Exit:
            pass


@app.command("board")
def task_board_cmd(watch: bool = typer.Option(False, "--watch", "-w", help="持续刷新")):
    """任务仪表盘."""
    init_env()
    import time as _time
    while True:
        task_board()  # call the function above
        if not watch:
            break
        _time.sleep(5)
        console.clear()


@run_app.command("show")
def run_show(run_id: str = typer.Option(..., "--run-id", "-r")):
    """展示 run 详情."""
    init_env()
    from .run_store import list_runs, _hub_dir
    import json
    runs = list_runs(limit=200)
    found = [r for r in runs if r.get("run_id") == run_id]
    if not found:
        console.print(f"[red]Run not found: {run_id}[/red]")
        return

    info = found[0]
    pid = info.get("project_id", "")
    rd = _hub_dir() / "runs" / pid / run_id
    sf = rd / "state.json"
    if not sf.exists():
        console.print(f"[red]State not found: {sf}[/red]")
        return

    s = json.loads(sf.read_text(encoding="utf-8"))
    console.print(f"[bold]Run: {run_id}[/bold]")
    console.print(f"Status: {s.get('status','?')} | Review: {s.get('review_result','?')}")
    console.print(f"Task: {s.get('task_title','?')} | Risk: {s.get('task_risk','?')}")
    console.print(f"Branch: {s.get('current_branch','?')} | Isolation: {s.get('isolation_mode','?')}")
    console.print(f"Diff: {s.get('diff_line_count',0)} lines, {len(s.get('changed_files',[]))} files")
    console.print(f"Test exit: {s.get('test_exit_code',-1)} | Fix rounds: {s.get('fix_round',0)}/{s.get('max_fix_rounds',3)}")
    console.print(f"Error: {s.get('error_message','')[:200]}")

    bc = s.get("backend_calls", {})
    if bc:
        console.print("\n[bold]Backend Calls:[/bold]")
        for node, info in bc.items():
            if isinstance(info, dict):
                console.print(f"  {node}: {info.get('backend','?')} exit={info.get('exit_code','?')} dur={info.get('duration_seconds','?')}s")

    # Chain evidence
    ce = rd / "chain-evidence.json"
    if ce.exists():
        ce_data = json.loads(ce.read_text(encoding="utf-8"))
        console.print("\n[bold]Chain Evidence:[/bold]")
        for node, info in ce_data.get("nodes", {}).items():
            if info.get("called") == False:
                console.print(f"  {node}: (not called)")
            else:
                console.print(f"  {node}: {info.get('backend','?')} exit={info.get('exit_code','?')} "
                              f"model={info.get('effective_model',info.get('requested_model','?'))}")
                if info.get("tokens_used"):
                    console.print(f"    tokens: {info['tokens_used'][:60]}")
                if info.get("session_id"):
                    console.print(f"    session: {info['session_id']}")

    for f in ["diff.patch", "review.yaml", "failure-analysis.md", "safety-report.md"]:
        fp = rd / f
        if fp.exists():
            console.print(f"  [dim]{f}: {fp.stat().st_size} bytes[/dim]")


@run_app.command("prune")
def run_prune(
    project_id: str = typer.Option("", "--project", "-p"),
    older_than_days: int = typer.Option(30, "--older-than", "-d"),
    keep_summary: bool = typer.Option(True, "--keep-summary"),
    dry_run: bool = typer.Option(True, "--dry-run"),
):
    """清理旧 run 目录."""
    init_env()
    from .run_store import _hub_dir
    import shutil, time as _time

    runs_base = _hub_dir() / "runs"
    cutoff = _time.time() - older_than_days * 86400
    pruned = 0

    for proj_dir in runs_base.iterdir():
        if not proj_dir.is_dir() or proj_dir.name in ("acceptance", "audit", "ci", "daemon", "backend-health"):
            continue
        for run_dir in proj_dir.iterdir():
            if not run_dir.is_dir(): continue
            if run_dir.stat().st_mtime > cutoff: continue
            # Read state to check status
            sf = run_dir / "state.json"
            status = "unknown"
            if sf.exists():
                try:
                    s = json.loads(sf.read_text(encoding="utf-8"))
                    status = s.get("status", "unknown")
                except Exception:
                    pass
            # Only prune passed
            if status != "passed": continue
            if dry_run:
                console.print(f"[dim]would prune: {run_dir.name} ({status})[/dim]")
                pruned += 1
            else:
                if keep_summary:
                    # Keep state.json + final-report + diff.patch
                    for f in run_dir.iterdir():
                        if f.name not in ("state.json", "final-report.md", "diff.patch", "failure-analysis.md"):
                            if f.is_file(): f.unlink()
                            elif f.is_dir(): shutil.rmtree(str(f))
                else:
                    shutil.rmtree(str(run_dir))
                pruned += 1

    action = "would prune" if dry_run else "pruned"
    console.print(f"[green]{action}: {pruned} runs[/green]")


@run_app.command("recover")
def run_recover(run_id: str = typer.Option(..., "--run-id", "-r"),
                project_id: str = typer.Option("", "--project", "-p")):
    """恢复建议 — 不自动执行，只给出可操作步骤."""
    init_env()
    from .run_store import list_runs
    runs = list_runs(limit=200)
    found = [r for r in runs if r.get("run_id") == run_id]
    pid = project_id or (found[0].get("project_id", "") if found else "")
    from .recover import analyze_recovery
    result = analyze_recovery(run_id, pid)
    if result.get("error"):
        console.print(f"[red]{result['error']}[/red]")
        return
    console.print(f"[bold]Recovery: {result['status']}[/bold]")
    console.print(f"Blocking: {result['blocking']} | Task: {result['task_id']}")
    console.print(f"\n[green]Suggested actions:[/green]")
    for s in result['suggestions']:
        console.print(f"  {s}")


@run_app.command("verify")
def run_verify(run_id: str = typer.Option(..., "--run-id", "-r"),
               project_id: str = typer.Option("", "--project", "-p")):
    """验证 run evidence 完整性."""
    init_env()
    from .run_store import list_runs, _hub_dir

    runs = list_runs(limit=200)
    found = [r for r in runs if r.get("run_id") == run_id]
    if not found:
        console.print(f"[red]Run not found: {run_id}[/red]")
        return

    pid = project_id or found[0].get("project_id", "")
    rd = _hub_dir() / "runs" / pid / run_id

    required = ["state.json", "final-report.md", "safety-report.json",
                "diff.patch", "test-output.md", "review.md", "review.yaml"]
    status = "passed"
    import json as _j
    sf = rd / "state.json"
    if sf.exists():
        s = _j.loads(sf.read_text(encoding="utf-8"))
        status = s.get("status", "?")
        if status != "passed":
            required.append("failure-analysis.md")

    present = [f for f in required if (rd / f).exists()]
    missing = [f for f in required if f not in present]
    ok = len(missing) == 0

    # Check final-report consistency
    fr = rd / "final-report.md"
    fr_ok = True
    fr_trusted = True
    if fr.exists():
        fr_text = fr.read_text(encoding="utf-8", errors="replace")
        if "deterministic" in fr_text or "fallback" in fr_text.lower():
            fr_trusted = False
        if status == "blocked" and "passed" in fr_text.lower() and "blocked" not in fr_text.lower():
            fr_ok = False
        if status == "passed" and "blocked" in fr_text.lower():
            fr_ok = False

    # Chain evidence
    ce = rd / "chain-evidence.json"
    ce_trust = "MISSING"
    if ce.exists():
        ce_data = json.loads(ce.read_text(encoding="utf-8"))
        ce_status = ce_data.get("status", "?")
        if ce_status in ("blocked", "failed"):
            ce_trust = "NOT_TRUSTED"
        else:
            thinking_ok = True
            for node in ["planner", "reviewer"]:
                n = ce_data.get("nodes", {}).get(node, {})
                be = n.get("backend", "")
                if be and be not in ("codex_cli",):
                    thinking_ok = False
                    console.print(f"[red]CHAIN: {node} backend={be} — not codex_cli[/red]")
            ce_trust = "TRUSTED" if thinking_ok else "NOT_TRUSTED"

    ev_ok = len(missing) == 0
    chain_ok = ce_trust != "NOT_TRUSTED"
    overall = "PASS" if ev_ok and chain_ok else "FAIL"

    console.print(f"[bold]{overall}: {len(present)}/{len(required)} evidence files[/bold]")
    if missing:
        console.print(f"[red]Evidence missing: {', '.join(missing)}[/red]")
    else:
        console.print("[green]All evidence present[/green]")
    console.print(f"[{'green' if chain_ok else 'red'}]Chain evidence: {ce_trust}[/{'green' if chain_ok else 'red'}]")
    console.print(f"[dim]Run status: {status}[/dim]")
    if missing:
        console.print(f"[red]Missing: {', '.join(missing)}[/red]")
    else:
        console.print("[green]All evidence present[/green]")
    console.print(f"[dim]Run status: {status}[/dim]")
    if not fr_ok:
        console.print(f"[red]WARN: final-report inconsistent with state[/red]")
    if not fr_trusted:
        console.print(f"[yellow]WARN: final-report is fallback/local template — trusted_for_status=false[/yellow]")


@run_app.command("latest")
def run_latest(project_id: str = typer.Option(..., "--project", "-p")):
    """显示最近的 run."""
    init_env()
    from .run_store import list_runs
    runs = list_runs(limit=1)
    if runs:
        run_show(run_id=runs[0].get("run_id", ""))
    else:
        console.print("[dim]No runs[/dim]")


# ============================================================
# status / report 命令
# ============================================================

@app.command("status")
@app.command("board")
def task_board():
    """任务仪表盘."""
    init_env()
    from .task_queue import list_tasks
    from .daemon import daemon_is_running

    daemon_state = "[green]RUNNING[/green]" if daemon_is_running() else "[dim]stopped[/dim]"
    console.print(f"Daemon: {daemon_state}\n")

    tasks = [t for t in list_tasks() if t.get("status") != "archived"]
    if not tasks:
        console.print("[dim]无活跃任务[/dim]")
        return

    table = Table(title="Task Board")
    table.add_column("ID")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Backend")
    table.add_column("Last Run")
    table.add_column("FA")

    for t in sorted(tasks, key=lambda t: {"queued": 0, "running": 1, "human_required": 2, "blocked": 3, "failed": 4, "passed": 5, "cancelled": 6}.get(t.get("status", ""), 9)):
        st = t.get("status", "")
        sc = {"passed": "green", "queued": "dim", "running": "blue", "blocked": "red", "failed": "red", "human_required": "yellow"}.get(st, "")

        # Check FA
        lr = t.get("last_run_id", "")
        fa_exists = False
        if lr:
            from .run_store import _hub_dir
            fa_path = _hub_dir() / "runs" / t["project_id"] / lr / "failure-analysis.md"
            fa_exists = fa_path.exists()

        table.add_row(
            t["id"], t.get("title", "")[:40],
            f"[{sc}]{st}[/{sc}]",
            t.get("coding_backend", "-") or "-",
            lr[-16:] if lr else "-",
            "[red]FA[/red]" if fa_exists else "-",
        )
    console.print(table)


def status_command():
    init_env()
    runs = list_runs(limit=20)

    if not runs:
        console.print("[yellow]没有运行记录[/yellow]")
        return

    table = Table(title="Recent Runs")
    table.add_column("Run ID", style="cyan")
    table.add_column("Project")
    table.add_column("Task")
    table.add_column("Status")
    table.add_column("Report")

    for r in runs:
        status = r.get("status", "unknown")
        status_style = {
            "passed": "green",
            "failed": "red",
            "blocked": "red",
            "human_required": "yellow",
            "pending": "dim",
            "running": "blue",
        }.get(status, "")
        table.add_row(
            r.get("run_id", ""),
            r.get("project_id", ""),
            r.get("task_id", ""),
            f"[{status_style}]{status}[/{status_style}]",
            "Yes" if r.get("has_report") else "No",
        )

    console.print(table)


@app.command("report")
def report_command(run_id: str = typer.Option(..., "--run", "-r")):
    init_env()

    runs = list_runs(limit=200)
    found = [r for r in runs if r.get("run_id") == run_id]

    if not found:
        console.print(f"[red]找不到运行: {run_id}[/red]")
        raise typer.Exit(1)

    info = found[0]
    project_id = info.get("project_id", "")
    report = get_run_report(run_id, project_id)

    if report:
        console.print(Panel(report[:3000], title=f"Report: {run_id}"))
        run_dir = Path(os.getcwd()) / "runs" / project_id / run_id
        console.print(f"\n[dim]完整报告: {run_dir}/final-report.md[/dim]")
    else:
        console.print(f"[yellow]report 不存在: {run_id}[/yellow]")


# ============================================================
# backup 命令
# ============================================================

bu_app = typer.Typer(help="备份管理")
app.add_typer(bu_app, name="backup")


@bu_app.command("list")
def backup_list(limit: int = typer.Option(20, "--limit", "-n")):
    """列出最近备份."""
    init_env()
    from .backup_manager import list_backups
    backups = list_backups(limit)
    if not backups:
        console.print("[dim]无备份[/dim]")
        return
    for b in backups:
        console.print(f"[dim]{b.get('_ts','?')[:19]}[/dim] {b.get('action','?')}: {b.get('source','?')}")


@bu_app.command("show")
def backup_show(timestamp: str = typer.Argument(..., help="时间戳前缀")):
    """查看备份详情."""
    init_env()
    from .backup_manager import list_backups
    matches = [b for b in list_backups(100) if timestamp in str(b.get("_ts", ""))]
    if matches:
        import json as _j
        console.print(_j.dumps(matches[0], indent=2, ensure_ascii=False))
    else:
        console.print(f"[red]未找到: {timestamp}[/red]")


@bu_app.command("restore")
def backup_restore(timestamp: str = typer.Argument(..., help="时间戳前缀")):
    """恢复备份."""
    init_env()
    from .backup_manager import restore_backup
    result = restore_backup(timestamp)
    if result.get("restored"):
        console.print(f"[green]Restored: {result['source']}[/green]")
    else:
        console.print(f"[red]{result.get('error')}[/red]")


# ============================================================
# worktree 命令
# ============================================================

wt_app = typer.Typer(help="worktree 管理")
app.add_typer(wt_app, name="worktree")


@wt_app.command("list")
def worktree_list():
    """列出所有 worktree."""
    init_env()
    from .config_loader import _hub_dir
    from .task_queue import list_tasks
    wt_base = _hub_dir().parent / "aihub-worktrees"
    if not wt_base.exists():
        console.print("[dim]无 worktree[/dim]")
        return

    tasks_map = {t.get("last_run_id", ""): t for t in list_tasks()}

    table = Table(title="Worktrees")
    table.add_column("Path")
    table.add_column("Task")
    table.add_column("Status")
    for wt_dir in sorted(wt_base.rglob("*")):
        if wt_dir.is_dir() and (wt_dir / ".git").exists():
            rel = str(wt_dir.relative_to(wt_base.parent))
            # Match to task
            task_id = wt_dir.name.split("-")[0] if "-" in wt_dir.name else ""
            t = tasks_map.get("", {})
            matched = any(wt_dir.name in lr for lr in [tt.get("last_run_id", "") for tt in tasks_map.values()])
            table.add_row(rel, task_id or "?", "-")
    console.print(table)


@wt_app.command("clean")
def worktree_clean(
    what: str = typer.Argument("passed", help="passed | all | failed"),
    older_than_days: int = typer.Option(0, "--older-than", "-d", help="仅清理 N 天前的"),
):
    """清理 worktree."""
    init_env()
    from .audit import audit_log
    audit_log("worktree.clean", result="STARTED", allowed=True, reason=f"mode={what}")
    import shutil
    from .config_loader import _hub_dir
    from .task_queue import list_tasks

    wt_base = _hub_dir().parent / "aihub-worktrees"
    if not wt_base.exists():
        console.print("[dim]无 worktree[/dim]")
        return

    task_statuses = {t["id"]: t.get("status", "") for t in list_tasks()}
    cleaned = 0
    cutoff = time.time() - older_than_days * 86400 if older_than_days else 0

    for proj_dir in wt_base.iterdir():
        if not proj_dir.is_dir(): continue
        for wt_dir in proj_dir.iterdir():
            if not wt_dir.is_dir(): continue
            if older_than_days and wt_dir.stat().st_mtime > cutoff: continue
            task_id = wt_dir.name.split("-")[0] if "-" in wt_dir.name else ""
            ts = task_statuses.get(task_id, "")
            should_clean = (what == "all") or (what == "passed" and ts == "passed")
            if should_clean:
                shutil.rmtree(str(wt_dir), ignore_errors=True)
                cleaned += 1
                console.print(f"[dim]已清理: {wt_dir.name}[/dim]")

    console.print(f"[green]清理完成: {cleaned} 个 worktree[/green]")


@app.command("apply")
def aihub_apply(
    description: str = typer.Argument(..., help="任务描述"),
    auto_yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
    backend: str = typer.Option("", "--backend", "-b"),
    risk: str = typer.Option("", "--risk", "-r"),
    project: str = typer.Option("", "--project", "-p"),
):
    """真实执行 — 改代码 / 测试 / 复审."""
    _aihub_plan_or_apply(description, apply_changes=True, auto_yes=auto_yes,
                         backend=backend, risk=risk, project=project)


@app.command("plan")
def aihub_plan(
    description: str = typer.Argument(..., help="任务描述"),
    apply_changes: bool = typer.Option(False, "--apply", help="拒绝 — 请用 aihub apply"),
    auto_yes: bool = typer.Option(False, "--yes", "-y"),
    backend: str = typer.Option("", "--backend", "-b"),
    risk: str = typer.Option("", "--risk", "-r"),
    project: str = typer.Option("", "--project", "-p"),
):
    """预演 — dry-run，不改代码."""
    if apply_changes:
        console.print("[red]plan 不支持 --apply。请使用: aihub apply[/red]")
        raise typer.Exit(1)
    _aihub_plan_or_apply(description, apply_changes=False, auto_yes=False,
                         backend=backend, risk=risk, project=project)


@app.command("do")
def aihub_do(
    description: str = typer.Argument(..., help="任务描述"),
    apply_changes: bool = typer.Option(False, "--apply", help="真实执行"),
    auto_yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
    backend: str = typer.Option("", "--backend", "-b"),
    risk: str = typer.Option("", "--risk", "-r"),
    project: str = typer.Option("", "--project", "-p"),
):
    """[deprecated] 请使用 aihub plan 或 aihub apply."""
    console.print("[yellow]aihub do is deprecated. Use aihub plan (dry-run) or aihub apply.[/yellow]")
    _aihub_plan_or_apply(description, apply_changes=apply_changes, auto_yes=auto_yes,
                         backend=backend, risk=risk, project=project)


def _aihub_plan_or_apply(
    description: str,
    apply_changes: bool = False,
    auto_yes: bool = False,
    backend: str = "",
    risk: str = "",
    project: str = "",
) -> None:
    """共享实现：plan (dry-run) / apply (真实)."""
    init_env()
    from pathlib import Path as _Path

    # 1. Session gate + project auto-detect
    cwd = str(_Path.cwd())
    from .session_gate import ensure_session_marker
    ensure_session_marker(cwd, created_by="aihub-do")

    # 2. Zero-config: auto-init if needed
    proj_id = project or _Path(cwd).name
    existing = find_project(proj_id)
    if not existing:
        from .project_detect import detect_project
        from .init_project import init_project
        detected = detect_project(cwd)
        console.print(f"[dim]Auto-detect: {detected['type']} (confidence {detected['confidence']})[/dim]")
        result = init_project(path=cwd, auto_register=True)
        if result.get("registered"):
            console.print(f"[green]Auto-registered: {proj_id}[/green]")
        existing = find_project(proj_id)

    if not project:
        from .project_detect import detect_project
        detected = detect_project(cwd)
        proj_id = detected["project_id"]
        existing = find_project(proj_id)
        if not existing:
            console.print(f"[dim]Auto-detected: {detected['type']} (confidence: {detected['confidence']})[/dim]")
            from .init_project import init_project
            result = init_project(path=cwd, auto_register=True)
            if result.get("registered"):
                console.print(f"[green]Auto-registered: {proj_id}[/green]")
            add_project(proj_id, proj_id, cwd)
            console.print(f"[green]Project registered: {proj_id}[/green]")

    # 2. Infer risk
    task_risk = risk or infer_risk_from_desc(description)
    console.print(f"[dim]Risk: {task_risk}[/dim]")

    # 3. Create task
    from .task_queue import add_task, list_tasks
    task_id = add_task(proj_id, description[:80], description, risk=task_risk)
    console.print(f"[dim]Task: {task_id}[/dim]")

    # 4. Select backend
    from .agent_client import resolve_backend
    from .backend_health import _load_health
    be = backend or resolve_backend()
    health = _load_health()
    h = health.get(be, {})
    console.print(f"[dim]Backend: {be} (score: {h.get('health_score', '?')})[/dim]")

    # 5. Dry-run by default
    if not apply_changes:
        console.print(f"\n[bold]Dry-run: {description[:100]}[/bold]")
        _execute_run(proj_id, task_id, apply_changes=False, run_tests=False, coding_backend=be)
        console.print(f"\n[yellow]No changes made. Review the plan above.[/yellow]")
        console.print(f"[dim]To apply: aihub do --apply \"{description[:60]}...\"[/dim]")
        return

    # 6. Preflight
    from .preflight import run_apply_preflight
    pf = run_apply_preflight(proj_id, task_id, backend=be, risk=task_risk, project_path=cwd)
    if pf["result"] == "BLOCKED":
        console.print(f"[red]Preflight BLOCKED: {pf['reason']}[/red]")
        for c in pf["checks"]:
            console.print(f"  {c['status']:7s} {c['name']}: {c['detail']}")
        return
    if pf["result"] == "WARN":
        console.print(f"[yellow]Preflight WARN: {pf['reason']}[/yellow]")

    # 6.5 Codex readiness gate (v1.0)
    if apply_changes:
        from .codex_readiness import check_apply_readiness
        ready, reason = check_apply_readiness()
        if not ready:
            console.print(f"[red]Codex thinking not ready: {reason}[/red]")
            console.print(f"[dim]Check: aihub codex readiness[/dim]")
            return

    # 8. Apply — risk/human gate
    if task_risk == "high":
        console.print(f"[red]HIGH RISK task — requires human gate. Use manual workflow.[/red]")
        return

    if not auto_yes:
        import typer as _typer
        confirm = _typer.confirm("Apply changes in isolated worktree?")
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            return

    console.print(f"\n[bold]Apply: {description[:100]}[/bold]")
    _execute_run(proj_id, task_id, apply_changes=True, run_tests=False, coding_backend=be)


def infer_risk_from_desc(description: str) -> str:
    from .project_detect import infer_risk
    return infer_risk(description)


@app.command("init")
def project_init(
    path: str = typer.Option(".", "--path", "-p", help="项目路径"),
    proj_type: str = typer.Option("", "--type", "-t", help="python | node | android | generic"),
    force: bool = typer.Option(False, "--force", "-f", help="覆盖已有 WORKFLOW.md"),
    auto: bool = typer.Option(False, "--auto", help="自动探测 + 注册项目"),
):
    """初始化项目 — 生成 .aiworkflow/WORKFLOW.md."""
    init_env()
    from .init_project import init_project
    result = init_project(path=path, proj_type=proj_type, force=force, auto_register=auto)
    if result.get("error"):
        console.print(f"[red]{result['error']}[/red]")
        return
    if result.get("warning"):
        console.print(f"[yellow]{result['warning']}[/yellow]")
        return
    console.print(f"[green]Project initialized: {result['project_type']}[/green]")
    console.print(f"  Workflow: {result['workflow_file']}")
    for k, v in result.get("test_commands", {}).items():
        console.print(f"  {k}: {v}")


# ============================================================
# issue 命令
# ============================================================

issue_app = typer.Typer(help="外部 issue 导入")
app.add_typer(issue_app, name="issue")


@issue_app.command("import")
def issue_import(
    repo: str = typer.Option(..., "--repo", "-r", help="GitHub repo: owner/name"),
    label: str = typer.Option("aihub", "--label", "-l", help="只导入此 label 的 issue"),
    limit: int = typer.Option(10, "--limit", "-n"),
):
    """从 GitHub 导入 issue 到本地 tasks.yaml。只导入，不双向同步."""
    init_env()
    from .issue_import import import_github_issues
    count = import_github_issues(repo=repo, label=label, limit=limit)
    if count:
        console.print(f"[green]Imported {count} issues[/green]")
    else:
        console.print("[dim]No new issues to import[/dim]")


# ============================================================
# codex 命令
# ============================================================

codex_app = typer.Typer(help="Codex CLI 诊断")
app.add_typer(codex_app, name="codex")


@codex_app.command("readiness")
def codex_readiness_cmd(refresh: bool = typer.Option(False, "--refresh", "-r")):
    """显示 Codex readiness 状态."""
    init_env()
    from .codex_readiness import readiness_cache_valid, refresh_readiness, CACHE_FILE
    if refresh or not readiness_cache_valid():
        console.print("[dim]Running probe...[/dim]")
        data = refresh_readiness()
    else:
        import json
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))

    status = "[green]READY[/green]" if data.get("ready") else "[red]NOT READY[/red]"
    console.print(f"Codex readiness: {status}")
    console.print(f"  Passes: {data.get('passes','?/3')}  p95: {data.get('p95_duration','?')}s")
    console.print(f"  Auth: {data.get('auth','?')} ({data.get('auth_mode','?')})  Proxy: {data.get('proxy_set','?')}")
    if data.get("failure_reasons"):
        for r in data["failure_reasons"]:
            console.print(f"  [red]{r}[/red]")


@codex_app.command("probe")
def codex_probe(
    count: int = typer.Option(3, "--count", "-n"),
    timeout: int = typer.Option(180, "--timeout", "-t"),
):
    """Codex CLI 专用探针 — 极小 prompt 测试."""
    init_env()
    from .codex_client import codex_auth_check, codex_exec
    import time as _t

    auth = codex_auth_check()
    console.print(f"Auth: {auth['authenticated']} mode={auth['auth_mode']}")

    results = []
    for i in range(count):
        console.print(f"\n[bold]Probe {i+1}/{count}...[/bold]", end=" ")
        start = _t.time()
        r = codex_exec(
            prompt="Reply with OK only.",
            model="gpt-5.5-codex",
            timeout=timeout,
            cwd=str(Path.cwd()),
        )
        dur = round(_t.time() - start, 1)
        be = r.get("backend", "?")
        ec = r.get("exit_code", -1)
        fb = r.get("fallback_from", "")

        results.append({"backend": be, "exit_code": ec, "duration": dur, "fallback_from": fb,
                        "stdout": r["stdout"][:100], "stderr": r["stderr"][:200]})

        icon = "[green]OK[/green]" if ec == 0 and be == "codex_cli" else "[red]FAIL[/red]"
        console.print(f"{icon} backend={be} exit={ec} dur={dur}s fallback={fb or 'none'}")

    # Summary
    passes = sum(1 for r in results if r["exit_code"] == 0 and r["backend"] == "codex_cli")
    durs = [r["duration"] for r in results]
    p95 = sorted(durs)[int(len(durs) * 0.95)] if durs else 0
    console.print(f"\n[bold]Result: {passes}/{count} codex_cli exit=0, p95={p95}s[/bold]")
    if passes == count and p95 < 60:
        console.print("[green]Codex CLI healthy[/green]")
    else:
        console.print("[red]Codex CLI NOT ready for thinking backend[/red]")


# ============================================================
# backend 命令
# ============================================================

backend_app = typer.Typer(help="Backend management")
app.add_typer(backend_app, name="backend")


@backend_app.command("probe")
def backend_probe():
    """轻量探针 — 检查 proxy/model 可达性，不消耗 token."""
    init_env()
    import urllib.request as _ur
    import os as _os

    proxy_url = _os.environ.get("ANTHROPIC_BASE_URL", "http://127.0.0.1:15721")

    # 1. Proxy TCP reachability
    proxy_reachable = False
    proxy_latency = 0
    try:
        import time as _t
        t0 = _t.time()
        req = _ur.Request(f"{proxy_url}/v1/messages", data=b'{}',
                         headers={"Content-Type": "application/json"})
        _ur.urlopen(req, timeout=10)
        proxy_latency = round(_t.time() - t0, 2)
        # HTTP error responses (401, 404) still mean reachable
        proxy_reachable = True
    except _ur.HTTPError:
        proxy_reachable = True  # server responded
        proxy_latency = round(_t.time() - t0 if 't0' in dir() else 0, 2)
    except Exception as e:
        console.print(f"[red]Proxy unreachable: {e}[/red]")

    console.print(f"[bold]Proxy:[/bold] {proxy_url}")
    console.print(f"  Reachable: {'[green]YES[/green]' if proxy_reachable else '[red]NO[/red]'}"
                  f"  Latency: {proxy_latency}s")

    # 2. Codex CLI availability
    from .codex_client import codex_is_available, codex_auth_check
    codex_ok = codex_is_available()
    console.print(f"[bold]Codex CLI:[/bold] {'[green]available[/green]' if codex_ok else '[red]not found[/red]'}")

    # 3. Auth check
    if codex_ok:
        auth = codex_auth_check()
        console.print(f"[bold]Codex auth:[/bold] {auth.get('auth_mode','?')} authenticated={auth.get('authenticated')}")

    # 4. Category determination
    if not proxy_reachable:
        cat = "BACKEND_UNAVAILABLE"
    elif codex_ok:
        cat = "READY"
    else:
        cat = "BACKEND_UNAVAILABLE"
    console.print(f"[bold]Category:[/bold] {cat}")


@backend_app.command("status")
def backend_status():
    """显示 backend 健康度."""
    init_env()
    from .backend_health import update_all_health
    data = update_all_health()

    from .agent_client import backend_health_summary
    status_map = backend_health_summary()

    table = Table(title="Backend Health")
    table.add_column("Backend")
    table.add_column("Status")
    table.add_column("Runs")
    table.add_column("Passed")
    table.add_column("Score")
    table.add_column("Avg(s)")
    table.add_column("P95(s)")
    for b in ["claude", "opencode"]:
        h = data.get(b, {})
        st = status_map.get(b, "?")
        st_color = {"healthy": "green", "degraded": "yellow"}.get(st, "dim")
        table.add_row(b, f"[{st_color}]{st}[/{st_color}]",
                      str(h.get("total_runs", 0)), str(h.get("passed", 0)),
                      f"{h.get('health_score', 0):.2f}",
                      str(h.get("avg_duration_seconds", 0)),
                      str(h.get("p95_duration_seconds", 0)))
    console.print(table)


@backend_app.command("stress")
def backend_stress(
    backend: str = typer.Option("claude", "--backend", "-b", help="claude | opencode"),
    count: int = typer.Option(5, "--count", "-n"),
    project: str = typer.Option("test-repo", "--project", "-p"),
):
    """Backend 压力测试 — 连续 N 次 apply."""
    init_env()
    import time as _t

    console.print(f"[bold]Stress: {backend} x{count} on {project}[/bold]")

    passed = 0
    failed = 0
    timeout_count = 0
    durations = []

    for i in range(count):
        # Generate unique stress task
        tid = f"stress-{backend}-{i}"
        title = f"Stress-{backend}-{i}"
        desc = f"在 stress_targets.py 的 stress_marker_{i} 函数上方添加注释 # backend stress {backend} run {i}"

        from .task_queue import add_task, mark_task_finished, update_task_status
        import subprocess as _sp

        # Write single task
        _yaml.safe_dump({"tasks": [{
            "id": tid, "project_id": project, "title": title,
            "description": desc, "risk": "low", "status": "queued",
            "priority": "normal",
        }]}, open(_hub_dir() / "tasks.yaml", "w", encoding="utf-8"), allow_unicode=True)

        console.print(f"[dim]Task {i+1}/{count}: {tid}...[/dim]", end=" ")
        try:
            _execute_run(project_id=project, task_id=tid, apply_changes=True,
                        run_tests=False, coding_backend=backend)
            # Read result
            from .run_store import list_runs
            runs = list_runs(limit=1)
            if runs:
                sf = _hub_dir() / "runs" / runs[0]["project_id"] / runs[0]["run_id"] / "state.json"
                if sf.exists():
                    import json as _j
                    s = _j.loads(sf.read_text(encoding="utf-8"))
                    st = s.get("status", "?")
                    bc = s.get("backend_calls", {}).get("executor", {})
                    dur = bc.get("duration_seconds", 0)
                    to = bc.get("timed_out", False)
                    durations.append(dur)
                    if st == "passed":
                        passed += 1
                        console.print(f"[green]{st} {dur}s[/green]")
                    elif to:
                        timeout_count += 1
                        failed += 1
                        console.print(f"[red]timeout {dur}s[/red]")
                    else:
                        failed += 1
                        console.print(f"[yellow]{st}[/yellow]")
        except Exception as e:
            failed += 1
            console.print(f"[red]ERROR: {e}[/red]")

        # Clean worktree
        _sp.run(["git", "-C", f"D:/devFrame/ai-workflow-hub-test-repo", "worktree", "prune"],
                capture_output=True)
        _sp.run(["rm", "-rf", "/d/devFrame/aihub-worktrees"], capture_output=True, shell=True)

    # Summary
    console.print(f"\n[bold]Stress complete: {backend} x{count}[/bold]")
    console.print(f"Passed: {passed}/{count} | Failed: {failed}/{count} | Timeouts: {timeout_count}")
    if durations:
        avg = sum(durations) / len(durations)
        console.print(f"Avg duration: {avg:.1f}s | Min: {min(durations):.1f}s | Max: {max(durations):.1f}s")

    from .backend_health import update_all_health
    update_all_health()


# ============================================================
# ops 命令
# ============================================================

ops_app = typer.Typer(help="运营状态")
app.add_typer(ops_app, name="ops")


@ops_app.command("status")
def ops_status():
    """一屏运营视图 — 不调模型，只读."""
    init_env()
    from .task_queue import list_tasks
    from .daemon import daemon_is_running
    from .backend_health import _load_health
    from .codex_readiness import readiness_cache_valid, CACHE_FILE
    from .config_loader import get_execution_policy
    import json as _j

    # Daemon
    console.print(f"[bold]Daemon:[/bold] {'[green]RUNNING[/green]' if daemon_is_running() else '[dim]stopped[/dim]'}")

    # Tasks
    tasks = list_tasks()
    counts = {"queued": 0, "running": 0, "blocked": 0, "passed": 0, "failed": 0, "human_required": 0}
    for t in tasks:
        st = t.get("status", "")
        if st in counts:
            counts[st] += 1
    console.print(f"[bold]Tasks:[/bold] Q:{counts['queued']} R:{counts['running']} B:{counts['blocked']} P:{counts['passed']} F:{counts['failed']} H:{counts['human_required']}")

    # Backend health
    health = _load_health()
    for b in ["claude", "opencode"]:
        h = health.get(b, {})
        console.print(f"[bold]{b}:[/bold] score={h.get('health_score',0):.2f} {h.get('passed',0)}/{h.get('total_runs',0)} passed")

    # Readiness
    if readiness_cache_valid():
        try:
            rd = _j.loads(CACHE_FILE.read_text(encoding="utf-8"))
            console.print(f"[bold]Readiness:[/bold] {'[green]READY[/green]' if rd.get('ready') else '[red]NOT READY[/red]'} {rd.get('passes','?')} p95={rd.get('p95_duration','?')}s")
        except Exception:
            console.print("[bold]Readiness:[/bold] [yellow]cache corrupt[/yellow]")
    else:
        console.print("[bold]Readiness:[/bold] [dim]stale or not probed[/dim]")

    # Policy
    rp = get_execution_policy().get("release_policy", {})
    blocked = [k for k, v in rp.items() if isinstance(v, bool) and not v]
    console.print(f"[bold]Policy blocked:[/bold] {', '.join(blocked[:5])}")

    # Goals
    from .goal_store import list_goals as _lg
    goals = _lg(5)
    active_goals = [g for g in goals if g.get("status") not in ("passed", "archived")]
    console.print(f"[bold]Goals:[/bold] {len(goals)} total, {len(active_goals)} active")

    # Evidence dirs
    from .config_loader import _hub_dir
    import os as _os
    runs_dir = _hub_dir() / "runs"
    run_count = sum(1 for _ in runs_dir.rglob("state.json")) if runs_dir.exists() else 0
    console.print(f"[bold]Runs:[/bold] {run_count} with state.json")


# ============================================================
# goal 命令
# ============================================================

goal_app = typer.Typer(help="多步骤目标编排")
app.add_typer(goal_app, name="goal")


@goal_app.command("plan")
def goal_plan(objective: str = typer.Argument(..., help="目标描述")):
    """Codex 拆解目标，不改代码."""
    init_env()
    from .goal_planner import plan_goal
    console.print(f"[bold]Planning: {objective[:100]}[/bold]")
    result = plan_goal(objective)
    if result.get("error"):
        console.print(f"[red]{result['error']}[/red]")
        if result.get("raw"):
            console.print(result["raw"][:500])
        return
    slices = result.get("slices", [])
    console.print(f"[green]Goal created: {result['goal_id']}[/green]")
    console.print(f"Slices: {len(slices)}")
    for sl in slices:
        console.print(f"  [{sl['risk']:5s}] {sl['title']}")
    console.print(f"\n[dim]Run: aihub goal run {result['goal_id']} --project <id>[/dim]")


@goal_app.command("run")
def goal_run(
    goal_id: str = typer.Argument(..., help="Goal ID"),
    project: str = typer.Option("test-repo", "--project", "-p"),
    backend: str = typer.Option("claude", "--backend", "-b"),
):
    """按依赖顺序执行 goal 的所有 slices."""
    init_env()
    from .goal_runner import run_goal
    g = run_goal(goal_id, project, backend)
    if g.get("error"):
        console.print(f"[red]{g['error']}[/red]")
        return
    console.print(f"[bold]Goal: {g['goal_id']} → {g['status']}[/bold]")
    for r in g.get("results", []):
        icon = "[green]OK[/green]" if r["status"] == "passed" else "[red]FAIL[/red]"
        name = r.get("batch") or r.get("slice", "?")
        console.print(f"  {icon} {name}: {r.get('run_id','')} {r.get('reason','')}")


@goal_app.command("status")
def goal_status(goal_id: str = typer.Argument(..., help="Goal ID")):
    """查看 goal 状态."""
    init_env()
    from .goal_store import load_goal
    g = load_goal(goal_id)
    if not g:
        console.print(f"[red]Goal not found: {goal_id}[/red]")
        return
    console.print(f"[bold]{g['goal_id']}[/bold]")
    console.print(f"Objective: {g['objective'][:100]}")
    console.print(f"Status: {g['status']} | Replans: {g.get('replan_count',0)}/{g.get('max_replans',2)}")

    # Batch-first view (v1.1)
    batches = g.get("batches", [])
    if batches:
        console.print(f"\nBatches ({len(batches)}):")
        for b in batches:
            icon = {"passed":"[green]OK[/green]","failed":"[red]FAIL[/red]",
                    "running":"[blue]RUN[/blue]","planned":"[dim]QUE[/dim]",
                    "blocked":"[red]BLOCK[/red]","human_required":"[yellow]GATE[/yellow]",
                    "needs_fix":"[yellow]FIX[/yellow]"}.get(b["status"], "[dim]?[/dim]")
            rd = b.get("risk_domain", "?")
            tasks_n = len(b.get("included_tasks", []))
            bid = b.get("batch_id", "?")
            console.print(f"  {icon} {bid} [{rd:20s}] {b.get('risk_level','?'):5s} {tasks_n} tasks  {b.get('run_id','')}")
        return

    # Legacy slice view
    slices = g.get("slices", [])
    if slices:
        console.print(f"\nSlices ({len(slices)}):")
        for sl in slices:
            icon = {"passed":"[green]OK[/green]","failed":"[red]FAIL[/red]",
                    "running":"[blue]RUN[/blue]","planned":"[dim]QUE[/dim]",
                    "blocked":"[red]BLOCK[/red]"}.get(sl["status"], "[dim]?[/dim]")
            console.print(f"  {icon} {sl['slice_id']}: {sl['title'][:50]}")


@goal_app.command("list")
def goal_list(limit: int = typer.Option(20, "--limit", "-n")):
    """列出所有 goals."""
    init_env()
    from .goal_store import list_goals
    goals = list_goals(limit)
    if not goals:
        console.print("[dim]No goals[/dim]")
        return
    for g in goals:
        batches = g.get("batches", [])
        slices = g.get("slices", [])
        if batches:
            n = len(batches)
            passed = sum(1 for b in batches if b["status"] == "passed")
            console.print(f"[dim]{g['goal_id']}[/dim] {g['status']:12s} {passed}/{n} batches  {g['objective'][:60]}")
        else:
            n = len(slices)
            passed = sum(1 for s in slices if s["status"] == "passed")
            console.print(f"[dim]{g['goal_id']}[/dim] {g['status']:12s} {passed}/{n} slices  {g['objective'][:60]}")


@goal_app.command("report")
def goal_report_cmd(goal_id: str = typer.Argument(..., help="Goal ID")):
    """生成 goal 报告 (goal-report.md + goal-evidence.json)."""
    init_env()
    from .goal_report import generate_goal_report
    result = generate_goal_report(goal_id)
    if result.get("error"):
        console.print(f"[red]{result['error']}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Report: {result['report_path']}[/green]")
    console.print(f"[green]Evidence: {result['evidence_path']}[/green]")
    console.print(f"[dim]Batches: {result.get('batches', 0)}[/dim]")


@goal_app.command("review-recovered")
def goal_review_recovered(
    goal_id: str = typer.Argument(..., help="Goal ID"),
    apply_changes: bool = typer.Option(False, "--apply", help="真实调用 reviewer backend"),
    project: str = typer.Option("test-repo", "--project", "-p"),
):
    """审阅 recovered evidence (dry-run default, --apply 调用真实 reviewer)."""
    init_env()
    from .goal_store import load_goal
    from .goal_runner import sync_goal_runs
    from .config_loader import _hub_dir
    from pathlib import Path as _P

    # Sync first
    sync_goal_runs(goal_id, project)
    g = load_goal(goal_id)
    if not g:
        console.print(f"[red]Goal not found: {goal_id}[/red]")
        raise typer.Exit(1)

    for b in g.get("batches", []):
        if not b.get("evidence_recovered") and not b.get("review_required"):
            continue
        rid = b.get("run_id", "")
        if not rid:
            console.print(f"[yellow]batch {b['batch_id']}: no run_id[/yellow]")
            continue

        rd = _hub_dir() / "runs" / project / rid
        dp = rd / "diff.patch"
        sf = rd / "state.json"

        # Pre-flight checks
        changed = b.get("changed_files", [])
        allowed = b.get("allowed_files", [])
        out = [f for f in changed if f not in allowed]
        diff_ok = len(out) == 0

        console.print(f"\n[bold]Batch: {b['batch_id']} (run: {rid})[/bold]")
        console.print(f"  changed_files: {changed}")
        console.print(f"  diff_scope_ok: {diff_ok}")
        console.print(f"  diff.patch: {'[green]exists[/green]' if dp.exists() else '[red]missing[/red]'}")
        console.print(f"  evidence_recovered: {b.get('evidence_recovered')}")
        console.print(f"  review_required: {b.get('review_required', True)}")

        if not diff_ok:
            console.print(f"[red]BLOCKED: out-of-scope files {out}[/red]")
            continue
        if not dp.exists() or dp.stat().st_size == 0:
            console.print(f"[red]BLOCKED: diff.patch missing or empty[/red]")
            continue

        if not apply_changes:
            console.print(f"\n[yellow]DRY-RUN: ready_for_review=true[/yellow]")
            console.print(f"[dim]Use --apply to invoke real reviewer backend[/dim]")
            continue

        # Real reviewer
        console.print(f"\n[red]APPLY: invoking reviewer backend...[/red]")
        try:
            diff_text = dp.read_text(encoding="utf-8")
            review_prompt = f"""Review the following recovered diff from an interrupted workflow.

Changed files: {', '.join(changed)}
Allowed files: {', '.join(allowed)}
Diff scope check: PASS (all changes within allowed_files)

## Recovered Diff
```diff
{diff_text[:8000]}
```

Review the changes. Check:
1. All changes are within allowed_files
2. No forbidden patterns
3. Changes are safe and correct
4. No test regressions introduced

Output: verdict (passed/failed/blocked) and reason.
"""
            from .agent_client import run_coding_agent
            result = run_coding_agent(
                prompt=review_prompt,
                backend="claude",
                model="deepseek-v4-pro",
                cwd=str(project) if not str(project).startswith("test") else "D:/devFrame/ai-workflow-hub-test-repo",
                timeout=300,
            )
            verdict = "passed" if result.get("exit_code") == 0 else "failed"
            review_text = result.get("stdout", "")[:500]

            # Write back
            from .goal_store import update_batch_status
            import json as _j
            update_batch_status(goal_id, b["batch_id"],
                               "passed" if verdict == "passed" else "failed",
                               run_id=rid,
                               review_result=f"RECOVERED_EVIDENCE_REVIEW_{verdict.upper()}; {review_text[:200]}",
                               evidence_recovered=True,
                               evidence_recovery_source="review-recovered")
            if sf.exists():
                s = _j.loads(sf.read_text(encoding="utf-8"))
                s["review_required"] = False
                s["review_result"] = review_text[:500]
                sf.write_text(_j.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")

            from .goal_report import generate_goal_report
            generate_goal_report(goal_id)
            console.print(f"[green]Reviewer: {verdict.upper()} — state written[/green]")
            try:
                console.print(f"[dim]{review_text[:200]}[/dim]")
            except UnicodeEncodeError:
                safe = review_text[:200].encode("ascii", errors="replace").decode("ascii")
                console.print(f"[dim]{safe}[/dim]")
        except Exception as e:
            console.print(f"[red]Reviewer error: {e}[/red]")


# ============================================================
# acceptance 命令
# ============================================================

acceptance_app = typer.Typer(help="自动化验收套件")
app.add_typer(acceptance_app, name="acceptance")

SUITES = {"smoke", "backend", "daemon", "external", "audit", "zero-config", "chain", "chain-truth", "chain-truth-negative", "dynamic", "goal", "cleanup", "status-check", "backend-probe", "assertion-check", "recovery-pipeline", "rc-check", "cleanup-safety", "all", "baseline", "compare", "daemon-atomicity"}


@acceptance_app.command("run")
def acceptance_run(suite: str = typer.Argument("smoke", help=f"Suite: {', '.join(sorted(SUITES))}")):
    """运行验收套件."""
    if suite not in SUITES:
        console.print(f"[red]Unknown suite: {suite}[/red]")
        raise typer.Exit(1)

    init_env()
    from .acceptance import (run_smoke, run_backend, run_daemon, run_external, run_audit,
        run_zero_config, run_chain, run_chain_truth, run_chain_truth_negative,
        run_dynamic, run_goal, run_cleanup, run_status_check, run_backend_probe,
        run_assertion_check, run_recovery_pipeline, run_rc_check,
        run_cleanup_safety, run_daemon_atomicity, run_all)
    from .acceptance import save_baseline, compare_baseline

    if suite == "baseline":
        name = "default"
        bp = save_baseline(name)
        console.print(f"[green]Baseline saved: {bp}[/green]")
        return
    if suite == "compare":
        result = compare_baseline("default")
        if result.get("error"):
            console.print(f"[red]{result['error']}[/red]")
            raise typer.Exit(1)
        if result["healthy"]:
            console.print("[green]No regressions[/green]")
        else:
            for r in result["regressions"]:
                console.print(f"[red]REGRESSION: {r}[/red]")
            raise typer.Exit(1)
        return

    fn = {"smoke": run_smoke, "backend": run_backend, "daemon": run_daemon,
          "external": run_external, "audit": run_audit, "zero-config": run_zero_config,
          "chain": run_chain, "chain-truth": run_chain_truth,
          "chain-truth-negative": run_chain_truth_negative,
          "dynamic": run_dynamic, "goal": run_goal, "cleanup": run_cleanup,
          "status-check": run_status_check, "backend-probe": run_backend_probe,
          "assertion-check": run_assertion_check,
          "recovery-pipeline": run_recovery_pipeline, "rc-check": run_rc_check,
          "cleanup-safety": run_cleanup_safety,
          "daemon-atomicity": run_daemon_atomicity, "all": run_all}[suite]
    rc = fn()
    if rc:
        raise typer.Exit(1)


# ============================================================
# PR 命令
# ============================================================

pr_app = typer.Typer(help="PR 创建")
app.add_typer(pr_app, name="pr")


@pr_app.command("preview")
def pr_preview(
    project_id: str = typer.Option(..., "--project", "-p"),
    run_id: str = typer.Option(..., "--run-id", "-r"),
):
    """预览 PR body，不创建."""
    init_env()
    from .pr_create import preview_pr
    body = preview_pr(project_id, run_id)
    console.print(Panel(body[:3000], title=f"PR Preview: {run_id}"))


@pr_app.command("create")
def pr_create_cmd(
    project_id: str = typer.Option(..., "--project", "-p"),
    run_id: str = typer.Option(..., "--run-id", "-r"),
    repo: str = typer.Option(..., "--repo", help="GitHub repo: owner/name"),
    push: bool = typer.Option(False, "--push", help="先 push branch 再创建 PR"),
):
    """创建 GitHub PR。默认不 push."""
    init_env()
    from .pr_create import create_pr
    result = create_pr(project_id, run_id, repo, push=push)
    if result["success"]:
        console.print(f"[green]PR created: {result['url']}[/green]")
    else:
        console.print(f"[red]{result['error']}[/red]")
        if result["body"]:
            console.print(Panel(result["body"][:1000], title="PR Body (would be)"))


# ============================================================
# CI 命令
# ============================================================

ci_app = typer.Typer(help="CI inspect/fix")
app.add_typer(ci_app, name="ci")


@ci_app.command("inspect")
def ci_inspect(
    repo: str = typer.Option(..., "--repo", "-r", help="GitHub repo: owner/name"),
    pr_number: int = typer.Option(..., "--pr", help="PR number"),
):
    """只读 GitHub Actions CI 状态."""
    init_env()
    from .ci_inspect import check_gh_ci_auth, inspect_ci_pr
    ok, msg = check_gh_ci_auth()
    if not ok:
        console.print(f"[red]{msg}[/red]")
        raise typer.Exit(1)

    report_path, overall = inspect_ci_pr(repo, pr_number)
    color = {"CI_PASS": "green", "CI_FAIL": "red", "CI_RUNNING": "yellow"}.get(overall, "dim")
    console.print(f"[{color}]{overall}[/{color}]")
    console.print(f"[dim]Report: {report_path}[/dim]")

    if overall in ("CI_FAIL", "CI_RUNNING"):
        with open(report_path, encoding="utf-8") as f:
            console.print(f.read()[:1000])


@ci_app.command("fix")
def ci_fix(
    project_id: str = typer.Option(..., "--project", "-p"),
    task_id: str = typer.Option(..., "--task", "-t"),
    repo: str = typer.Option(..., "--repo", "-r"),
    pr_number: int = typer.Option(..., "--pr"),
):
    """CI 失败后自动修复。需要 allow_ci_fix=true."""
    init_env()
    from .ci_inspect import check_gh_ci_auth, ci_fix_task
    ok, msg = check_gh_ci_auth()
    if not ok:
        console.print(f"[red]{msg}[/red]")
        raise typer.Exit(1)

    result = ci_fix_task(project_id, task_id, repo, pr_number)
    if result["status"] == "blocked":
        console.print(f"[red]{result['ci_results']}[/red]")
    else:
        console.print(f"[green]{result['ci_results']}[/green]")


# ============================================================
# daemon 命令
# ============================================================

daemon_app = typer.Typer(help="本地任务调度 daemon")
app.add_typer(daemon_app, name="daemon")


@daemon_app.command("start")
def daemon_start(once: bool = typer.Option(False, "--once", help="只执行一轮")):
    """启动 daemon 轮询。"""
    init_env()
    from .daemon import daemon_loop, daemon_is_running
    if daemon_is_running() and not once:
        console.print("[yellow]Daemon 已在运行[/yellow]")
        raise typer.Exit(1)
    console.print("[bold]Daemon 启动...[/bold]")
    daemon_loop(once=once)


@daemon_app.command("stop")
def daemon_stop():
    """停止 daemon."""
    init_env()
    from .daemon import _PIDFILE, _cleanup_lock, daemon_is_running
    import ctypes
    if not daemon_is_running():
        console.print("[yellow]Daemon 未在运行[/yellow]")
        return
    try:
        pid = int(_PIDFILE.read_text().strip())
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
        if handle:
            kernel32.TerminateProcess(handle, 0)
            kernel32.CloseHandle(handle)
            console.print(f"[green]Daemon (pid={pid}) 已停止[/green]")
    except Exception as e:
        console.print(f"[red]停止失败: {e}[/red]")
    _cleanup_lock()


@daemon_app.command("soak")
def daemon_soak_cmd(
    duration: str = typer.Option("30m", "--duration", "-d", help="30m | 2h | 8h"),
    projects: str = typer.Option("test-repo", "--projects", "-p"),
    mode: str = typer.Option("plan", "--mode", "-m", help="plan | apply-safe"),
):
    """运行 daemon soak 测试."""
    init_env()
    # Parse duration
    d = duration.lower()
    mins = 30
    if d.endswith("m"): mins = int(d[:-1])
    elif d.endswith("h"): mins = int(d[:-1]) * 60
    pids = [p.strip() for p in projects.split(",") if p.strip()]

    console.print(f"[bold]Soak: {mins}m, mode={mode}, projects={pids}[/bold]")
    from .daemon import daemon_soak
    result = daemon_soak(duration_minutes=mins, projects=pids, mode=mode)

    sim = " (simulated)" if result.get("simulated") else ""
    console.print(f"\nStatus: [bold]{result['status']}[/bold]{sim} | Reason: {result['end_reason']}")
    console.print(f"Cycles: {result['cycle_count']} | Tasks: seen={result['tasks_seen']} started={result['tasks_started']}")
    console.print(f"Passed: {result['tasks_passed']} Blocked: {result['tasks_blocked']} Failed: {result['tasks_failed']}")
    console.print(f"Stale: {result['stale_running_count']} | Duration: {result['actual_duration_seconds']}s | Exit: {result['exit_code']}")
    if result.get("errors"):
        for e in result["errors"]:
            console.print(f"[red]  {e[:120]}[/red]")

    if result.get("report_json"):
        console.print(f"[dim]Report JSON: {result['report_json']}[/dim]")
        console.print(f"[dim]Report MD:   {result['report_md']}[/dim]")

    # Propagate exit code
    if result["exit_code"] != 0:
        raise typer.Exit(1)


@daemon_app.command("status")
def daemon_status():
    """查看 daemon 状态."""
    init_env()
    from .daemon import daemon_is_running, _HEARTBEAT
    from .config_loader import _hub_dir
    from .task_queue import list_tasks

    if daemon_is_running():
        hb = ""
        if _HEARTBEAT.exists():
            hb = f" (last heartbeat: {_HEARTBEAT.read_text().strip()[:19]})"
        console.print(f"[green]Daemon: RUNNING{hb}[/green]")
    else:
        console.print("[dim]Daemon: stopped[/dim]")

    log_dir = _hub_dir() / "runs" / "daemon"
    if log_dir.exists():
        logs = sorted(log_dir.glob("daemon-*.log"))
        if logs:
            console.print(f"\n[dim]最近日志 ({logs[-1].name}):[/dim]")
            with open(logs[-1], encoding="utf-8") as f:
                for l in f.readlines()[-8:]:
                    console.print(f"  {l.rstrip()}")

    queued = list_tasks(status="queued")
    running = list_tasks(status="running")
    blocked = list_tasks(status="blocked")
    passed = list_tasks(status="passed")
    console.print(f"\n[bold]Queued: {len(queued)}  Running: {len(running)}  Blocked: {len(blocked)}  Passed: {len(passed)}[/bold]")


# ============================================================
# doctor 命令 (增强)
# ============================================================

@app.command("doctor")
def doctor(strict: bool = typer.Option(False, "--strict", help="生产就绪检查")):
    """检查系统环境."""
    init_env()
    from .config_loader import get_model_config
    mc = get_model_config()

    console.print("[bold]ai-workflow-hub Doctor[/bold]")
    console.print(f"\n[bold]Target Chain:[/bold]")
    console.print(f"  Thinking (planner/reviewer/finalizer): {mc.get('thinking',{}).get('backend','?')} / {mc.get('thinking',{}).get('model','?')}")
    console.print(f"  Coding  (executor/fixer):           {mc.get('coding',{}).get('backend','?')} / {mc.get('coding',{}).get('model','?')}")
    console.print()

    if strict:
        console.print("[bold yellow]STRICT MODE[/bold yellow]\n")
    else:
        console.print()

    checks = []

    # Python
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    checks.append(("Python >= 3.10", py_ver >= "3.10", py_ver))

    # Git
    import subprocess
    try:
        git_result = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
        git_ok = git_result.returncode == 0
        git_ver = git_result.stdout.strip()
    except Exception:
        git_ok = False
        git_ver = "not found"
    checks.append(("Git", git_ok, git_ver))

    # OpenCode CLI + 兼容检查
    from .opencode_client import opencode_is_available, opencode_cli_check, opencode_list_models
    opencode_ok = opencode_is_available()
    if opencode_ok:
        cli_info = opencode_cli_check()
        flags_found = cli_info.get("flags_found", [])
        flags_missing = cli_info.get("flags_missing", [])
        models_cmd = cli_info.get("models_cmd_ok", False)

        flags_str = ", ".join(f"{f}={'Y' if f in flags_found else 'N'}" for f in flags_found + flags_missing)
        detail = f"available, [{flags_str}]" if flags_str else "available"
        checks.append(("OpenCode CLI", True, detail))

        if flags_missing:
            checks.append(("OpenCode missing flags", False, f"missing: {', '.join(flags_missing)}"))
        else:
            checks.append(("OpenCode flags", True, "all required flags found"))

        checks.append(("OpenCode models cmd", models_cmd, "available" if models_cmd else "not available"))

        if models_cmd:
            available_models = opencode_list_models()
            checks.append(("OpenCode models list", bool(available_models), f"{len(available_models)} models found" if available_models else "empty"))
    else:
        checks.append(("OpenCode CLI", False, "not found"))

    # Codex CLI + 兼容检查
    from .codex_client import codex_is_available, codex_cli_check
    codex_ok = codex_is_available()
    if codex_ok:
        cli_info = codex_cli_check()
        flags_found = cli_info.get("flags_found", [])
        flags_missing = cli_info.get("flags_missing", [])
        # Codex 0.133: no required flags (model via config.toml)
        cli_note = "(model via config.toml, no runtime flags required)"
        checks.append(("Codex CLI", True, cli_note))
        # Strict: Codex WebSocket reachability
        if strict:
            from .codex_client import codex_auth_check
            auth = codex_auth_check()
            if auth["authenticated"]:
                proxy_set = bool(os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or os.environ.get("ALL_PROXY"))
                checks.append(("Codex proxy", proxy_set, "configured" if proxy_set else "NOT SET — WebSocket will fail"))
                checks.append(("Codex auth mode", True, auth.get("auth_mode", "?")))
    else:
        checks.append(("Codex CLI", False, "not found"))

    # Release policy
    policy = get_execution_policy()
    rp = policy.get("release_policy", {})
    for key in ["allow_push", "allow_pr_create", "allow_merge", "allow_deploy"]:
        val = rp.get(key, False)
        checks.append((f"Release: {key}", not val, "BLOCKED (default)" if not val else "ENABLED"))

    # Claude 2.0 CLI + 兼容检查
    from .claude_client import claude_is_available, claude_cli_check
    claude_ok = claude_is_available()
    if claude_ok:
        claude_info = claude_cli_check()
        ver = claude_info.get("version", "unknown")
        checks.append(("Claude 2.0 CLI", True, f"available (v{ver})"))
    else:
        checks.append(("Claude 2.0 CLI", False, "not found"))

    # 模型校验
    console.print("\n[bold]Model Validation:[/bold]")
    model_results = validate_all_models()
    for role, info in model_results.items():
        fmt_ok = info["format_ok"]
        remote_ok = info.get("remote_ok")
        model_id = info["model_id"]

        if not fmt_ok:
            checks.append((f"Model [{role}]: format", False, info["format_msg"]))
        elif remote_ok is False:
            checks.append((f"Model [{role}]: {model_id}", False, info.get("remote_msg", "not available")))
        else:
            status_msg = info.get("remote_msg", "OK")
            checks.append((f"Model [{role}]: {model_id}", True, status_msg))

    # 环境变量
    env_vars = ["CODEX_API_KEY", "OPENCODE_API_KEY"]
    for var in env_vars:
        val = os.environ.get(var, "")
        is_set = bool(val)
        masked = val[:4] + "..." if len(val) > 4 else "(not set)"
        display = masked if is_set else "(not set)"
        checks.append((f"ENV: {var}", is_set, display))

    # Python 依赖
    deps = ["langgraph", "typer", "rich", "pydantic", "yaml", "dotenv"]
    for dep in deps:
        try:
            __import__(dep.replace("-", "_"))
            checks.append((f"Python: {dep}", True, "installed"))
        except ImportError:
            checks.append((f"Python: {dep}", False, "not installed"))

    # 配置
    from .config_loader import _hub_dir
    for config_file in ["projects.yaml", "tasks.yaml", "configs/model-router.yaml", "configs/risk-policy.yaml", "configs/execution-policy.yaml"]:
        exists = (_hub_dir() / config_file).exists()
        checks.append((f"Config: {config_file}", exists, "found" if exists else "missing"))

    # 输出
    all_ok = True
    for name, ok, detail in checks:
        icon = "[green]PASS[/green]" if ok else "[red]FAIL[/red]"
        if not ok:
            all_ok = False
        console.print(f"  {icon}  {name}: {detail}")

    console.print()
    if all_ok:
        console.print("[green]所有检查通过[/green]")
    else:
        console.print("[yellow]部分检查未通过，请安装缺失依赖或设置环境变量[/yellow]")


# ============================================================
# 核心执行逻辑
# ============================================================

def _execute_run(project_id: str, task_id: str, apply_changes: bool, run_tests: bool = False, coding_backend: str = "",
                 task_allowed_files: list[str] | None = None,
                 task_forbidden_files: list[str] | None = None) -> None:
    """执行一次完整的 workflow run (带 checkpointer)."""
    # 1. 加载项目
    project = find_project(project_id)
    if not project:
        console.print(f"[red]项目 '{project_id}' 不在注册表中[/red]")
        raise typer.Exit(1)

    # 2. 加载任务
    task = find_task(task_id)
    if not task:
        console.print(f"[red]任务 '{task_id}' 不存在[/red]")
        raise typer.Exit(1)

    # 3. 校验项目路径
    project_path = project.get("path", "")
    if not Path(project_path).exists():
        console.print(f"[red]项目路径不存在: {project_path}[/red]")
        raise typer.Exit(1)

    # 4. Git 检查
    from .git_utils import is_git_repo, is_worktree_clean, is_main_branch, get_current_branch

    if not is_git_repo(project_path):
        console.print(f"[red]项目不是 Git 仓库: {project_path}[/red]")
        raise typer.Exit(1)

    if apply_changes and not is_worktree_clean(project_path):
        console.print(f"[red]Git 工作区不干净。先提交或 stash 再 apply。[/red]")
        raise typer.Exit(1)

    if apply_changes and is_main_branch(project_path):
        console.print(f"[red]不允许在 main/master 分支上 apply。[/red]")
        raise typer.Exit(1)

    # 5. 加载项目配置
    config_filename = project.get("config", ".aiworkflow.yaml")
    project_config = load_project_workflow_config(project_path, config_filename)
    if not project_config:
        console.print(f"[yellow]警告: {config_filename} 不存在或为空[/yellow]")

    # 6. 加载策略
    risk = task.get("risk", "medium")
    risk_policy = get_risk_policy()
    execution_policy = get_execution_policy()

    risk_config = risk_policy.get("risk_categories", {}).get(risk, {})
    constraints = {
        "max_fix_rounds": risk_config.get("max_fix_rounds", execution_policy.get("max_fix_rounds", 3)),
        "max_changed_files": risk_config.get("max_changed_files", execution_policy.get("max_changed_files", 20)),
        "max_diff_lines": risk_config.get("max_diff_lines", execution_policy.get("max_diff_lines", 800)),
    }

    # 7. 模型分配 + 校验
    models = get_model_for_task(risk)
    from .model_router import validate_model_format
    # Model format validation — only for OpenCode (needs provider/model)
    from .agent_client import resolve_backend as _rb
    for role, model_id in models.items():
        if role in ("executor", "fixer"):
            backend = _rb(coding_backend)
            if backend == "opencode" and "/" not in model_id:
                console.print(f"[red]模型格式错误 [{role}]: OpenCode 模型 ID 必须为 provider/model 格式，当前: {model_id}[/red]")
                raise typer.Exit(1)
        # Claude uses bare model names (e.g., deepseek-v4-pro), no validation needed

    # 8. 创建 run 目录
    run_id, run_dir = create_run_dir(project_id)

    # 9. 隔离策略：worktree → branch fallback
    current_branch = get_current_branch(project_path)
    original_branch = current_branch  # preserved for cleanup (Defect 2 fix)
    worktree_path = ""
    isolation_mode = "branch"
    isolation_fallback_reason = ""

    if apply_changes:
        from .git_utils import create_branch, create_worktree
        mode = execution_policy.get("isolation_mode", "worktree")
        fallback_mode = execution_policy.get("fallback_isolation_mode", "branch")
        ai_branch = f"ai/{task_id}-{run_id[-12:]}"
        _worktree_created = False
        _branch_created = False

        if mode == "worktree":
            wt_dir = str(Path(project_path).parent / "aihub-worktrees" / project_id / f"{task_id}-{run_id[-12:]}")
            ok, msg = create_worktree(project_path, wt_dir, ai_branch)
            if ok:
                worktree_path = wt_dir
                isolation_mode = "worktree"
                current_branch = ai_branch
                _worktree_created = True
                console.print(f"[green]Worktree 创建: {worktree_path}[/green]")
            else:
                isolation_fallback_reason = f"worktree failed: {msg}"
                console.print(f"[yellow]Worktree 失败 ({msg})，降级 branch[/yellow]")

        if isolation_mode != "worktree":
            ok, msg = create_branch(project_path, ai_branch)
            if not ok:
                console.print(f"[red]创建分支失败: {msg}[/red]")
                raise typer.Exit(1)
            current_branch = ai_branch
            isolation_mode = fallback_mode if isolation_mode == "worktree" else isolation_mode
            _branch_created = True
            console.print(f"[green]在分支 '{ai_branch}' 上执行[/green]")

    # CI report from task (for CI fix)
    ci_report = task.get("ci_report", "")

    # 加载项目 WORKFLOW.md
    from .config_loader import find_workflow_file, load_workflow_text
    wf_file = find_workflow_file(project_path) or ""
    wf_text = load_workflow_text(project_path)

    state = WorkflowState(
        project_id=project_id,
        project_name=project.get("name", project_id),
        workflow_file=wf_file,
        workflow_text=wf_text,
        project_type=project_config.get("project", {}).get("type", ""),
        project_path=project_path,
        project_config=project_config,
        task_id=task_id,
        task_title=task.get("title", ""),
        task_description=task.get("description", ""),
        task_risk=risk,
        run_id=run_id,
        run_dir=run_dir,
        thread_id=run_id,  # run_id → thread_id
        current_branch=current_branch,
        worktree_path=worktree_path,
        base_project_path=project_path,
        original_branch=original_branch,
        isolation_mode=isolation_mode,
        isolation_fallback_reason=isolation_fallback_reason,
        dry_run=not apply_changes,
        apply_changes=apply_changes,
        run_tests=run_tests,
        coding_backend=coding_backend,
        ci_report=ci_report,
        planner_model=models["planner"],
        reviewer_model=models["reviewer"],
        executor_model=models["executor"],
        fixer_model=models["fixer"],
        constraints=constraints,
        test_commands=project_config.get("commands", {}),
        allowed_files=task_allowed_files if task_allowed_files is not None else [],
        forbidden_files=_resolve_boundary(
            task_forbidden_files if task_forbidden_files is not None
            else project_config.get("policy", {}).get("forbidden_paths", []),
            task_allowed_files or []),
        protected_tests=project_config.get("policy", {}).get("protected_tests", []),
        max_fix_rounds=constraints["max_fix_rounds"],
        status="running",
    )

    # 10. 保存初始状态
    save_run_file(run_dir, "input-task.md", f"# Task: {task['title']}\n\n{task['description']}")
    save_run_file(run_dir, "project-config.yaml", json.dumps(project_config, indent=2, ensure_ascii=False))
    save_run_json(run_dir, "state.json", state.model_dump())

    # 11. 显示信息
    mode_parts = []
    if not apply_changes:
        mode_parts.append("[yellow]DRY-RUN[/yellow]")
    else:
        mode_parts.append("[red]APPLY[/red]")
    if run_tests and not apply_changes:
        mode_parts.append("[blue]+RUN-TESTS[/blue]")

    mode_str = " ".join(mode_parts)
    console.print(f"\n[bold]Run: {run_id}[/bold]")
    console.print(f"Project: {project_id} | Task: {task['title']} | Risk: {risk} | Mode: {mode_str}")
    console.print(f"Models: planner={models['planner']}, executor={models['executor']}, reviewer={models['reviewer']}")
    console.print(f"Thread: {run_id}")
    console.print(f"Run dir: {run_dir}")

    # 12. 执行 LangGraph 工作流 (带 checkpointer)
    console.print("\n[bold]执行工作流...[/bold]\n")

    from .workflows.coding_graph import compile_graph
    app_graph = compile_graph(thread_id=run_id)

    state_dict = state.model_dump()

    # Trace marker: persist diagnostic snapshot before workflow starts
    _write_trace(run_dir, last_node="", last_event="workflow_started",
                 last_model="", last_backend="",
                 started_at=datetime.now(timezone.utc).isoformat())

    final_state = None
    from .task_queue import mark_task_running, mark_task_finished
    mark_task_running(task_id, run_id)

    final_state = None
    _should_cleanup = False  # set to True only for non-deliverable outcomes (Defect 1 fix)

    try:
        final_state = app_graph.invoke(
            state_dict,
            config={"configurable": {"thread_id": run_id}, "recursion_limit": 50},
        )
    except Exception as e:
        console.print(f"[red]工作流执行错误: {e}[/red]")
        # Classify timeout/blocker category for diagnostics
        msg = str(e).lower()
        if "timeout" in msg or "timed out" in msg:
            if "proxy" in msg or "127.0.0.1" in msg or "localhost" in msg:
                category = "PROXY_TIMEOUT"
            else:
                category = "MODEL_TIMEOUT"
        elif any(w in msg for w in ("connection refused", "unreachable", "name resolution",
                                      "no route", "econnrefused", "could not connect")):
            category = "BACKEND_UNAVAILABLE"
        elif any(w in msg for w in ("unauthorized", "auth", "forbidden", "permission")):
            category = "BACKEND_UNAVAILABLE"
        else:
            category = "UNKNOWN_TIMEOUT"
        _write_trace(run_dir, last_node="workflow", last_event="exception",
                     last_model=state_dict.get("planner_model", ""),
                     last_backend="workflow_executor",
                     started_at=state_dict.get("started_at", ""))
        mark_task_finished(task_id, "failed", run_id)
        # 保存错误状态
        state_dict["status"] = "failed"
        state_dict["error_message"] = str(e)
        state_dict["timeout_category"] = category
        state_dict["updated_at"] = WorkflowState().updated_at
        save_run_json(run_dir, "state.json", state_dict)
        _should_cleanup = True  # exception = non-deliverable (Defect 1 fix)
        cleanup_result = _cleanup_isolation(project_path, worktree_path, ai_branch,
                                           original_branch, _worktree_created,
                                           _branch_created, run_dir, apply_changes)
        state_dict.update(cleanup_result)
        save_run_json(run_dir, "state.json", state_dict)
        raise typer.Exit(1)

    # Defect 1 fix: only cleanup for non-deliverable statuses (not "passed")
    cleanup_result = {"cleanup_success": True, "cleanup_error": ""}
    if apply_changes and (_worktree_created or _branch_created):
        status = final_state.get("status", "unknown")
        if status in ("failed", "blocked", "human_required", "running", "pending"):
            _should_cleanup = True
            cleanup_result = _cleanup_isolation(project_path, worktree_path, ai_branch,
                                               original_branch, _worktree_created,
                                               _branch_created, run_dir, apply_changes)

    # 统一持久化最终状态 — 无论 workflow 走到哪个节点结束
    status = final_state.get("status", "unknown")
    if status in ("running", "pending"):
        # workflow 未正常结束，视为 failed
        status = "failed"
        final_state["status"] = "failed"

    # Defect 3RR fix: merge cleanup result into final_state before persisting,
    # so cleanup fields are not lost when final_state overwrites state.json
    final_state.update(cleanup_result)
    final_state["updated_at"] = WorkflowState().updated_at
    save_run_json(run_dir, "state.json", final_state)
    mark_task_finished(task_id, status, run_id,
                       blocked_reason=final_state.get("error_message", ""))
    # Chain evidence
    _write_chain_evidence(run_dir, final_state)

    # 如果 human_gate 结束但 finalizer 没走到，补生成 final-report
    final_report_path = Path(run_dir) / "final-report.md"
    if not final_report_path.exists() and status in ("human_required", "blocked", "failed"):
        _generate_fallback_final_report(run_dir, final_state)

    status_styles = {
        "passed": "green",
        "failed": "red",
        "blocked": "red",
        "human_required": "yellow",
    }
    style = status_styles.get(status, "")
    console.print(f"\n[bold {style}]最终状态: {status}[/bold {style}]")
    console.print(f"[dim]报告: {run_dir}/final-report.md[/dim]")

    if status == "human_required":
        console.print(f"\n[yellow]Human gate required. 查看: {run_dir}/human-gate.md[/yellow]")
        console.print(f"[dim]当前运行已通过 checkpointer 保存 (thread_id={run_id})[/dim]")
        console.print(f"[dim]审批后，重新运行 aihub run start --apply 继续[/dim]")


def _cleanup_isolation(project_path: str, worktree_path: str, ai_branch: str,
                      original_branch: str, _worktree_created: bool,
                      _branch_created: bool, run_dir: str,
                      apply_changes: bool) -> dict[str, Any]:
    """Clean up isolation resources (worktree/branch) for non-deliverable outcomes.

    Returns a dict with keys cleanup_success (bool) and cleanup_error (str).
    Caller is responsible for merging these into the final state before persisting.

    Does NOT write state.json — that is the caller's responsibility so the
    cleanup fields are not overwritten by a subsequent final_state save.

    Defect 1 fix: Only called when status is non-deliverable (failed/blocked/human_required/exception).
    Defect 2 fix: Checkout original_branch before deleting temp branch to avoid
    "cannot delete branch you are on" errors.
    Defect 3RR fix: Returns cleanup result instead of writing state.json internally.
    """
    if not apply_changes or not (_worktree_created or _branch_created):
        return {"cleanup_success": True, "cleanup_error": ""}

    from .git_utils import remove_worktree, delete_branch, checkout_branch
    cleanup_success = True
    cleanup_error = ""

    if _worktree_created and worktree_path:
        ok, msg = remove_worktree(project_path, worktree_path)
        if not ok:
            cleanup_success = False
            cleanup_error = f"worktree_remove: {msg}"
            console.print(f"[yellow]Worktree 清理失败: {msg}[/yellow]")
        else:
            console.print(f"[dim]Worktree 已清理: {worktree_path}[/dim]")

    if _branch_created:
        # Defect 2 fix: checkout original_branch first so delete_branch can succeed
        if original_branch:
            co_ok, co_msg = checkout_branch(project_path, original_branch)
            if not co_ok:
                # Defect 3RR fix: checkout failure must be recorded as cleanup failure
                cleanup_success = False
                if cleanup_error:
                    cleanup_error += f"; checkout_original: {co_msg}"
                else:
                    cleanup_error = f"checkout_original: {co_msg}"
                console.print(f"[yellow]Checkout 回 {original_branch} 失败: {co_msg}[/yellow]")
        ok, msg = delete_branch(project_path, ai_branch)
        if not ok:
            cleanup_success = False
            if cleanup_error:
                cleanup_error += f"; branch_delete: {msg}"
            else:
                cleanup_error = f"branch_delete: {msg}"
            console.print(f"[yellow]分支清理失败: {msg}[/yellow]")
        else:
            console.print(f"[dim]分支已清理: {ai_branch}[/dim]")

    # Persist cleanup result to isolation-cleanup.json (dedicated artifact)
    # state.json persistence is handled by the caller to prevent overwrite
    save_run_json(run_dir, "isolation-cleanup.json", {
        "cleanup_success": cleanup_success,
        "cleanup_error": cleanup_error,
        "worktree_created": _worktree_created,
        "branch_created": _branch_created,
        "cleaned_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"cleanup_success": cleanup_success, "cleanup_error": cleanup_error}


def _generate_fallback_final_report(run_dir: str, state: dict[str, Any]) -> None:
    """当 finalizer 未走到时，生成基础 final-report."""
    from datetime import datetime, timezone
    status = state.get("status", "unknown")
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    content = f"""# Final Report (auto-generated)

## Run Info
- **Run ID**: {state.get("run_id", "")}
- **Project**: {state.get("project_name", "")} ({state.get("project_id", "")})
- **Task**: {state.get("task_title", "")} ({state.get("task_id", "")})
- **Risk**: {state.get("task_risk", "medium")}
- **Mode**: {'dry-run' if state.get("dry_run", True) else 'apply'}
- **Status**: {status}

## Reason
The workflow ended with status `{status}` before reaching the finalizer node.
This is normal for human_gate and blocked outcomes.

## Backend Calls
{_render_cli_backend_calls(state.get("backend_calls", {}))}

## Evidence Files
All evidence is in: {run_dir}
"""
    save_run_file(run_dir, "final-report.md", content)
    # 生成 failure-analysis.md（human_gate 路径不经过 finalizer）
    from .nodes.finalizer import build_failure_analysis
    fa = build_failure_analysis(state)
    save_run_file(run_dir, "failure-analysis.md", fa)


def _resolve_boundary(forbidden_files: list[str], allowed_files: list[str]) -> list[str]:
    """Remove exact file matches from forbidden_files. allowed_files win.

    Directory patterns (e.g. src/) are preserved — only exact file paths are removed.
    """
    allowed_set = {f.strip() for f in allowed_files if f.strip()
                   and not f.strip().endswith("/")}  # exact files only, not dirs
    return [f for f in forbidden_files
            if f.strip() not in allowed_set or f.strip().endswith("/")]


def _write_trace(run_dir: str, *, last_node: str, last_event: str,
                 last_model: str, last_backend: str,
                 started_at: str = "", updated_at: str = "",
                 timeout_budget_seconds: int = 0,
                 timeout_source: str = "",
                 elapsed_seconds: float = 0.0,
                 planner_prompt_chars: int = 0,
                 workflow_text_chars: int = 0,
                 task_description_chars: int = 0,
                 allowed_files_count: int = 0,
                 forbidden_files_count: int = 0) -> None:
    """Write diagnostic trace to run_dir/trace.json. Survives node crashes."""
    from datetime import datetime, timezone
    trace_path = Path(run_dir) / "trace.json"
    trace = {}
    if trace_path.exists():
        try:
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    trace["last_node"] = last_node or trace.get("last_node", "")
    trace["last_event"] = last_event
    trace["last_model"] = last_model or trace.get("last_model", "")
    trace["last_backend"] = last_backend or trace.get("last_backend", "")
    trace["started_at"] = started_at or trace.get("started_at", "")
    trace["updated_at"] = updated_at or datetime.now(timezone.utc).isoformat()
    # v1.5: timeout budget + prompt metrics (preserve existing if zero)
    if timeout_budget_seconds:
        trace["timeout_budget_seconds"] = timeout_budget_seconds
    if timeout_source:
        trace["timeout_source"] = timeout_source
    if elapsed_seconds:
        trace["elapsed_seconds"] = elapsed_seconds
    if planner_prompt_chars:
        trace["planner_prompt_chars"] = planner_prompt_chars
    if workflow_text_chars:
        trace["workflow_text_chars"] = workflow_text_chars
    if task_description_chars:
        trace["task_description_chars"] = task_description_chars
    if allowed_files_count or "allowed_files_count" not in trace:
        trace["allowed_files_count"] = allowed_files_count
    if forbidden_files_count or "forbidden_files_count" not in trace:
        trace["forbidden_files_count"] = forbidden_files_count
    trace_path.write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")


def verify_run_evidence(run_id: str, project_id: str) -> dict:
    """共享函数：run verify 三态判定。run verify CLI 和 goal_runner 共用."""
    import json as _j, os as _os
    from .config_loader import _hub_dir
    rd = _hub_dir() / "runs" / project_id / run_id
    if not rd.exists():
        return {"evidence_ok": False, "chain_trusted": False, "final_report_consistent": False,
                "status": "unknown", "reasons": ["run directory not found"]}

    required = ["state.json", "final-report.md", "safety-report.json",
                "diff.patch", "test-output.md", "review.md", "review.yaml"]
    evidence_ok = all((rd / f).exists() for f in required)

    ce = rd / "chain-evidence.json"
    chain_trusted = False
    if ce.exists():
        ce_data = _j.loads(ce.read_text(encoding="utf-8"))
        chain_trusted = ce_data.get("status") not in ("blocked", "failed")

    sf = rd / "state.json"
    run_status = "unknown"
    fr_consistent = True
    if sf.exists():
        s = _j.loads(sf.read_text(encoding="utf-8"))
        run_status = s.get("status", "unknown")

    fr = rd / "final-report.md"
    if fr.exists():
        fr_text = fr.read_text(encoding="utf-8", errors="replace").lower()
        if run_status == "blocked" and "passed" in fr_text and "blocked" not in fr_text:
            fr_consistent = False

    # Build detailed result
    present = [f for f in required if (rd / f).exists()]
    missing = [f for f in required if f not in present]
    if run_status != "passed" and "failure-analysis.md" not in required:
        if (rd / "failure-analysis.md").exists():
            present.append("failure-analysis.md")
        else:
            missing.append("failure-analysis.md")

    reasons = []
    if not evidence_ok:
        reasons.append(f"evidence missing: {', '.join(missing)}")
    if not chain_trusted:
        reasons.append(f"chain NOT_TRUSTED (status={run_status})")
    if not fr_consistent:
        reasons.append("final report inconsistent with state.status")
    if evidence_ok and chain_trusted and fr_consistent:
        pass  # no reasons needed

    return {
        "evidence_ok": evidence_ok,
        "chain_trusted": chain_trusted,
        "final_report_consistent": fr_consistent,
        "status": run_status,
        "reasons": reasons,
        "evidence_files_present": present,
        "evidence_files_missing": missing,
        "chain_status": "TRUSTED" if chain_trusted else ("NOT_TRUSTED" if ce.exists() else "MISSING"),
        "final_report_status": "CONSISTENT" if fr_consistent else "INCONSISTENT" if (rd / "final-report.md").exists() else "MISSING",
    }


def _write_chain_evidence(run_dir: str, state: dict) -> None:
    """生成 chain-evidence.json."""
    import json as _j, hashlib as _hl, os as _os
    bc = state.get("backend_calls", {})
    evidence = {
        "run_id": state.get("run_id", ""),
        "status": state.get("status", ""),
        "thinking_backend": "codex_cli",
        "coding_backend": "claude",
        "proxy_set": bool(_os.environ.get("HTTPS_PROXY") or _os.environ.get("ALL_PROXY")),
        "nodes": {},
    }
    for node in ["planner", "executor", "reviewer", "fixer", "finalizer"]:
        info = bc.get(node, {})
        if not isinstance(info, dict):
            evidence["nodes"][node] = {"called": False}
            continue
        entry = {
            "backend": info.get("backend", "?"),
            "requested_model": info.get("requested_model", info.get("model", "?")),
            "effective_model": info.get("effective_model", info.get("model", "?")),
            "exit_code": info.get("exit_code", -1),
            "fallback_from": info.get("fallback_from", ""),
        }
        # Log hashes
        for log_name in ["stdout_log", "stderr_log"]:
            path = info.get(log_name, "")
            if path and _os.path.exists(path):
                entry[f"{log_name}_sha256"] = _hl.sha256(Path(path).read_bytes()).hexdigest()[:16]
        # Parse tokens from stderr
        stderr_path = info.get("stderr_log", "")
        if stderr_path and _os.path.exists(stderr_path):
            try:
                for line in Path(stderr_path).read_text(encoding="utf-8", errors="replace").split("\n"):
                    if "tokens used" in line.lower():
                        entry["tokens_used"] = line.strip()
                    if "session id" in line.lower():
                        entry["session_id"] = line.split(":")[-1].strip()
            except Exception:
                pass
        evidence["nodes"][node] = entry

    Path(run_dir, "chain-evidence.json").write_text(
        _j.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")


def _render_cli_backend_calls(bc: dict) -> str:
    if not bc:
        return "No backend calls recorded."
    lines = ["| Node | Backend | Model | Exit Code |", "|------|---------|-------|-----------|"]
    for node, info in bc.items():
        if isinstance(info, dict):
            lines.append(f"| {node} | {info.get('backend', '?')} | {info.get('model', '?')} | {info.get('exit_code', '?')} |")
    return "\n".join(lines)


def main():
    app()


if __name__ == "__main__":
    main()
