#!/usr/bin/env bash
# Copy the service to the Windows PC and install/refresh dependencies.
set -euo pipefail
cd "$(dirname "$0")/../service"
ssh my-windows-pc 'if not exist %USERPROFILE%\sunlight\service mkdir %USERPROFILE%\sunlight\service'
scp -q -r sunlight requirements.txt my-windows-pc:sunlight/service/
ssh my-windows-pc 'cd %USERPROFILE%\sunlight && venv\Scripts\python -m pip install -q -r service\requirements.txt'
echo "deployed"
