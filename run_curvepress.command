#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
# Recover after a failed first installation, and install updates on each launch.
.venv/bin/python -m pip install -e '.[cad]' || {
  echo "Installation failed. Check your network connection and run this launcher again."
  exit 1
}
exec .venv/bin/python -m curvepress serve
