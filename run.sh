#!/bin/sh
# ShelfClear — one-command run. Python 3.8+ only, no dependencies to install.
cd "$(dirname "$0")"
exec python3 app.py
