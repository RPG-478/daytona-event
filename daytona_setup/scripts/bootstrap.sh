#!/usr/bin/env bash
# サンドボックスの中で1回だけ実行する準備スクリプト（何度流しても同じ結果になる）。
#   1. Python + pytest
#   2. Node.js 24.9 以上（DSH の動作条件）
#   3. DSH（DeepSeek Harness）
set -euo pipefail

DSH_VERSION="${DSH_VERSION:-0.2.2-rc.1}"
NODE_MAJOR="${NODE_MAJOR:-24}"
export N_PREFIX="$HOME/.n"
export NPM_CONFIG_PREFIX="$HOME/.npm-global"
export PATH="$N_PREFIX/bin:$NPM_CONFIG_PREFIX/bin:$PATH"

echo "== python / pytest =="
python3 --version
python3 -m pip install --quiet --upgrade pytest
python3 -m pytest --version

node_ok() {
  command -v node >/dev/null 2>&1 && node -e '
    const [major, minor] = process.versions.node.split(".").map(Number);
    process.exit(major > 24 || (major === 24 && minor >= 9) ? 0 : 1);'
}

echo "== node =="
if ! node_ok; then
  mkdir -p "$N_PREFIX" "$NPM_CONFIG_PREFIX"
  npm install --global --silent n
  n "$NODE_MAJOR"
  hash -r
fi
node --version

echo "== dsh =="
npm install --global --silent "@deepseek-ai/dsh@${DSH_VERSION}"
dsh --version

# 以後のログインシェルでも同じ PATH になるようにする。
PROFILE_LINE="export PATH=\"$N_PREFIX/bin:$NPM_CONFIG_PREFIX/bin:\$PATH\""
grep -qxF "$PROFILE_LINE" "$HOME/.profile" 2>/dev/null || echo "$PROFILE_LINE" >> "$HOME/.profile"
echo "bootstrap: ok"
