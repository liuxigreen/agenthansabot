#!/bin/bash
set -euo pipefail
cd /Users/liuxi/.openclaw/workspace/apps/agenthansa-local
set -a
source ./.env
set +a
exec /usr/bin/env python3 /Users/liuxi/.openclaw/workspace/apps/agenthansa-local/agenthansa-top1.py run-once
