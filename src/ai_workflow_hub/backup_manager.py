"""Safe delete/move — 破坏性操作前强制备份，稳定 backup_id."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config_loader import _hub_dir

BACKUP_ROOT = Path("E:/Backups")
BIN_DIR = BACKUP_ROOT / "deleted"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")[:18]


def _hash_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def safe_backup(path: str, reason: str = "") -> dict[str, Any] | None:
    src = Path(path)
    if not src.exists():
        return None

    backup_id = f"{src.name}-{_ts()}"
    is_dir = src.is_dir()
    dest = BIN_DIR / backup_id
    dest.parent.mkdir(parents=True, exist_ok=True)

    if is_dir:
        shutil.copytree(str(src), str(dest))
    else:
        shutil.copy2(str(src), str(dest))

    source_h = _hash_file(str(src)) if not is_dir else ""
    size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file()) if is_dir else dest.stat().st_size

    manifest = {
        "backup_id": backup_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": reason,
        "source": str(src),
        "backup": str(dest),
        "is_dir": is_dir,
        "size": size,
        "source_hash": source_h,
        "backup_hash": _hash_file(str(dest)) if not is_dir else "",
    }

    mf = BIN_DIR / f"manifest-{backup_id}.json"
    mf.parent.mkdir(parents=True, exist_ok=True)
    mf.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest["manifest_path"] = str(mf)

    _audit_backup(manifest)
    return manifest


def safe_delete(path: str, reason: str = "") -> dict[str, Any]:
    manifest = safe_backup(path, reason)
    if manifest is None:
        return {"error": f"Path not found: {path}", "deleted": False}

    src = Path(path)
    if src.is_dir():
        shutil.rmtree(str(src))
    else:
        src.unlink()

    return {"manifest": manifest, "deleted": True, "backup_id": manifest["backup_id"],
            "backup": str(manifest["backup"])}


def safe_move(src_path: str, dst_path: str, reason: str = "") -> dict[str, Any]:
    """安全移动 — 始终备份源路径."""
    manifest = safe_backup(src_path, reason)
    src = Path(src_path)
    dst = Path(dst_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return {"manifest": manifest, "backup_id": manifest["backup_id"] if manifest else None,
            "moved": True, "source": str(src), "dest": str(dst)}


def list_backups(limit: int = 20) -> list[dict[str, Any]]:
    manifests = sorted(BIN_DIR.glob("manifest-*.json"), reverse=True)
    result = []
    for mf in manifests[:limit]:
        try:
            result.append(json.loads(mf.read_text(encoding="utf-8")))
        except Exception:
            pass
    return result


def restore_backup(backup_id: str) -> dict[str, Any]:
    """通过 backup_id 精确恢复."""
    mf = BIN_DIR / f"manifest-{backup_id}.json"
    if not mf.exists():
        return {"error": f"No backup found: {backup_id}"}

    manifest = json.loads(mf.read_text(encoding="utf-8"))
    backup_path = Path(manifest["backup"])
    source_path = Path(manifest["source"])

    if not backup_path.exists():
        return {"error": f"Backup file missing: {backup_path}"}

    source_path.parent.mkdir(parents=True, exist_ok=True)
    if manifest.get("is_dir"):
        if source_path.exists():
            shutil.rmtree(str(source_path))
        shutil.copytree(str(backup_path), str(source_path))
    else:
        shutil.copy2(str(backup_path), str(source_path))

    # Verify restore
    restored_hash = _hash_file(str(source_path)) if not manifest.get("is_dir") else ""
    hash_match = restored_hash == manifest.get("source_hash", "") if restored_hash else True

    _audit_backup({"action": "restore", "backup_id": backup_id,
                    "source": str(source_path), "hash_match": hash_match})
    return {"restored": True, "source": str(source_path), "backup_id": backup_id,
            "hash_match": hash_match}


def _audit_backup(entry: dict) -> None:
    log = BACKUP_ROOT / "backup-log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    entry["_ts"] = datetime.now(timezone.utc).isoformat()
    log.open("a", encoding="utf-8").write(json.dumps(entry, ensure_ascii=False) + "\n")
