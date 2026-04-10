#!/bin/bash
set -euo pipefail
export PATH="/Users/liuxi/.npm-global/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
cd /Users/liuxi/.openclaw/workspace/apps/agenthansa-local
set -a
source ./.env
set +a
exec /usr/bin/env python3 /Users/liuxi/.openclaw/workspace/apps/agenthansa-local/agenthansa-top1.py loop
