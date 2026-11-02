#!/usr/bin/env bash
# 按文件名顺序应用 customizations/patches/*.py。
# 补丁可重复执行：已打过的位置按 [fork:<tag>:<name>] 标记跳过。
set -euo pipefail

cd "$(dirname "$0")/.."

PY=${PYTHON:-python}
if ! command -v "$PY" >/dev/null 2>&1; then
  PY=python3
fi

for patch in customizations/patches/*.py; do
  "$PY" -u "$patch"
done
