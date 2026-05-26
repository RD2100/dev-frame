#!/usr/bin/env bash
# ============================================================
# ai-workflow-hub env checker — 检查环境变量和密钥
# ============================================================
set -euo pipefail

echo "Environment Variable Check"
echo "==========================="

vars=(
    "CODEX_API_KEY"
    "CODEX_API_BASE"
    "CODEX_MODEL_PLANNER"
    "CODEX_MODEL_REVIEWER"
    "CODEX_MODEL_FINALIZER"
    "OPENCODE_API_KEY"
    "OPENCODE_API_BASE"
    "OPENCODE_MODEL_EXECUTOR"
    "OPENCODE_MODEL_FIXER"
    "OPENROUTER_API_KEY"
    "OPENROUTER_API_BASE"
)

for var in "${vars[@]}"; do
    value="${!var:-}"
    if [ -n "$value" ]; then
        masked="${value:0:4}..."
        echo "  [SET]  $var = $masked"
    else
        echo "  [MISS] $var (not set)"
    fi
done

echo ""
echo "Copy .env.example to .env and fill in the values if any are missing."
