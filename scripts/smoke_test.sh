#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PRIVATE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/water-ledger-smoke-private.XXXXXX")"
PORT="${WATER_LEDGER_SMOKE_PORT:-8799}"
PYTHON_BIN="${PYTHON:-python3}"

cleanup() {
  WATER_LEDGER_PRIVATE_DIR="$PRIVATE_DIR" "$PYTHON_BIN" -m water_ledger stop >/dev/null 2>&1 || true
  rm -rf "$PRIVATE_DIR"
}
trap cleanup EXIT

cd "$ROOT_DIR"

echo "==> init"
WATER_LEDGER_PRIVATE_DIR="$PRIVATE_DIR" "$PYTHON_BIN" -m water_ledger init --no-balance-prompts

echo "==> copy example bills"
cp examples/支付宝交易明细_sample.csv "$PRIVATE_DIR/imports/alipay/"
cp examples/微信支付账单流水文件_sample.xlsx "$PRIVATE_DIR/imports/wechat/"

echo "==> import"
WATER_LEDGER_PRIVATE_DIR="$PRIVATE_DIR" "$PYTHON_BIN" -m water_ledger import

echo "==> privacy check"
"$PYTHON_BIN" -m water_ledger privacy-check

echo "==> start dashboard"
WATER_LEDGER_PRIVATE_DIR="$PRIVATE_DIR" "$PYTHON_BIN" -m water_ledger start --port "$PORT"
WATER_LEDGER_PRIVATE_DIR="$PRIVATE_DIR" "$PYTHON_BIN" -m water_ledger status

echo "==> check dashboard response"
curl -fsS "http://127.0.0.1:$PORT/" >/dev/null

echo "==> stop dashboard"
WATER_LEDGER_PRIVATE_DIR="$PRIVATE_DIR" "$PYTHON_BIN" -m water_ledger stop

echo "Smoke test passed."
