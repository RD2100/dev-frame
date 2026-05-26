"""Codex readiness — 缓存 codex probe 结果，apply 前检查."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from .config_loader import _hub_dir

CACHE_FILE = _hub_dir() / "runs" / "codex-readiness" / "latest.json"
CACHE_TTL_MINUTES = 10


def readiness_cache_valid() -> bool:
    if not CACHE_FILE.exists():
        return False
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        age = datetime.now(timezone.utc) - datetime.fromisoformat(data["timestamp"])
        return age < timedelta(minutes=CACHE_TTL_MINUTES)
    except Exception:
        return False


def refresh_readiness(timeout: int = 180) -> dict[str, Any]:
    """运行 codex probe 3 次，缓存结果."""
    from .codex_client import codex_auth_check, codex_exec
    import time, os

    auth = codex_auth_check()
    proxy_set = bool(os.environ.get("HTTPS_PROXY") or os.environ.get("ALL_PROXY"))

    results = []
    for _ in range(3):
        start = time.time()
        r = codex_exec(
            prompt="Reply with OK only.",
            model="gpt-5.5-codex",
            timeout=timeout // 2,
            cwd=str(_hub_dir()),
        )
        dur = round(time.time() - start, 1)
        exit_code = r.get("exit_code", -1)
        stderr_lower = (r.get("stderr", "") or "").lower()
        # Only flag stderr errors when exit_code != 0 OR no useful output.
        # Codex CLI often writes git warnings ("fatal: not a git repository")
        # to stderr even on success — these are NOT readiness-blocking.
        stdout = r.get("stdout", "")
        has_stderr_error_blocking = (
            exit_code != 0
            and any(w in stderr_lower for w in
                ("fatal:", "unsupported model", "invalid_request_error", "unauthorized", "auth failed"))
            and not ("tls handshake" in stderr_lower)
        )
        results.append({
            "backend": r.get("backend", "?"),
            "exit_code": exit_code,
            "duration": dur,
            "stderr_has_error": has_stderr_error_blocking,
            "stdout": stdout[:100],
        })

    passes = sum(1 for r2 in results if r2["exit_code"] == 0 and r2["backend"] == "codex_cli")
    durs = [r2["duration"] for r2 in results]
    p95 = sorted(durs)[-1] if len(durs) >= 3 else (max(durs) if durs else 0)
    has_stderr_errors = any(r2["stderr_has_error"] for r2 in results)

    ready = (
        passes == 3
        and p95 < 60
        and auth["authenticated"]
        and proxy_set
        and not has_stderr_errors
    )

    degraded = (
        passes >= 2
        and p95 < 60
        and auth["authenticated"]
        and proxy_set
        and not has_stderr_errors
    )

    cache = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ready": ready,
        "passes": f"{passes}/3",
        "p95_duration": p95,
        "auth": auth["authenticated"],
        "auth_mode": auth.get("auth_mode", ""),
        "proxy_set": proxy_set,
        "stderr_clean": not has_stderr_errors,
        "effective_model": "gpt-5.5",
        "results": results,
        "failure_reasons": [],
    }

    if not ready:
        reasons = []
        if passes < 3:
            reasons.append(f"probe passes {passes}/3, require 3/3")
        if p95 >= 60:
            reasons.append(f"p95 {p95}s >= 60s")
        if not auth["authenticated"]:
            reasons.append("codex not authenticated")
        if not proxy_set:
            reasons.append("HTTPS_PROXY not set")
        if has_stderr_errors:
            reasons.append("stderr contains errors")
        cache["failure_reasons"] = reasons

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")

    # Append to history
    history = CACHE_FILE.parent / "history.jsonl"
    with open(str(history), "a", encoding="utf-8") as hf:
        hf.write(json.dumps(cache, ensure_ascii=False) + "\n")

    return cache


def check_apply_readiness() -> tuple[bool, str]:
    """apply 前检查 readiness."""
    if not readiness_cache_valid():
        refresh_readiness()

    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return False, "readiness cache corrupted"

    if data.get("ready"):
        return True, "ready"

    reasons = data.get("failure_reasons", ["unknown"])
    proxy_hint = ""
    if not data.get("proxy_set"):
        proxy_hint = " Set: HTTPS_PROXY=http://127.0.0.1:7897"

    return False, "; ".join(reasons) + proxy_hint
