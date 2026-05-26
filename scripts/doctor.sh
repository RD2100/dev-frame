#!/usr/bin/env bash
# ============================================================
# ai-workflow-hub doctor — 环境检查脚本
# ============================================================
set -euo pipefail

echo "============================================"
echo " ai-workflow-hub Doctor"
echo "============================================"
echo ""

PASS=0
FAIL=0

check() {
    local name="$1"
    local cmd="$2"
    if eval "$cmd" &>/dev/null; then
        echo "  [PASS] $name"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $name"
        FAIL=$((FAIL + 1))
    fi
}

echo "--- Python ---"
check "python >= 3.10" "python3 -c 'import sys; assert sys.version_info >= (3, 10)'"

echo ""
echo "--- Git ---"
check "git" "git --version"

echo ""
echo "--- Codex CLI ---"
check "codex" "codex --version"

echo ""
echo "--- OpenCode CLI ---"
check "opencode" "opencode --version"

echo ""
echo "--- Python Dependencies ---"
check "langgraph" "python3 -c 'import langgraph'"
check "typer" "python3 -c 'import typer'"
check "rich" "python3 -c 'import rich'"
check "pydantic" "python3 -c 'import pydantic'"
check "yaml (pyyaml)" "python3 -c 'import yaml'"
check "dotenv" "python3 -c 'import dotenv'"

echo ""
echo "--- Environment Variables ---"
check "CODEX_API_KEY set" 'test -n "${CODEX_API_KEY:-}"'
check "OPENCODE_API_KEY set" 'test -n "${OPENCODE_API_KEY:-}"'

echo ""
echo "--- Config Files ---"
HUB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
for f in projects.yaml tasks.yaml configs/model-router.yaml configs/risk-policy.yaml configs/execution-policy.yaml; do
    if [ -f "$HUB_DIR/$f" ]; then
        echo "  [PASS] $f"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $f (missing)"
        FAIL=$((FAIL + 1))
    fi
done

echo ""
echo "============================================"
echo " Results: $PASS passed, $FAIL failed"
echo "============================================"

if [ $FAIL -gt 0 ]; then
    echo ""
    echo "Fix missing items before running aihub."
    exit 1
else
    echo ""
    echo "All checks passed. Ready to use aihub."
fi
