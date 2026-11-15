#!/usr/bin/env bash
# サンドボックスの中で実行する準備。
# 入れるものは daytona-hello/src/backends/dsh-daytona.mjs と同じ（pytest と DSH）。
# そちらは既定のサンドボックスで確認済み（Node v24.22.1 / DSH 0.2.2-rc.1）。
set -euo pipefail

DSH_VERSION="${DSH_VERSION:-0.2.2-rc.1}"

python3 --version
python3 -m pip install -q pytest
python3 -m pytest --version

# DSH は Node.js 24.9 以上が必要。足りなければここで止める。
node -e '
  const [major, minor] = process.versions.node.split(".").map(Number);
  if (!(major > 24 || (major === 24 && minor >= 9))) {
    console.error(`Node.js ${process.versions.node} は古い（24.9 以上が必要）`);
    process.exit(1);
  }
  console.log(`node ${process.versions.node}`);'

npm install --global --silent "@deepseek-ai/dsh@${DSH_VERSION}"
dsh --version
echo "bootstrap: ok"
