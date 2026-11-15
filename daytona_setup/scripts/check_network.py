"""サンドボックスの中から、外の接続先に届くかを調べる。

daytona-hello/README.md の「既知のブロッカー」（サンドボックスから Nosana に届かない）を
切り分けるためのもの。サンドボックスを1つ作り、接続先ごとに curl を打ち、必ず削除して終わる。

使い方:
    python scripts/check_network.py                      # NOSANA_BASE_URL（省略時は既定値）と比較用の3つ
    python scripts/check_network.py --host example.com   # 調べる先を足す（複数可）

終了コード: Nosana の接続先に届けば 0、届かなければ 1。
"""

from __future__ import annotations

import argparse
import shlex
import sys
from urllib.parse import urlsplit

from daytona import CreateSandboxFromSnapshotParams

from common import LABELS, bash, client, nosana_base_url

# 比較用。Daytona の制限つきの組織でも届くはずの接続先。
REFERENCE_HOSTS = ["registry.npmjs.org", "pypi.org", "github.com"]

CURL_EXIT = {
    0: "届いた",
    6: "名前を引けない（DNS）",
    7: "接続を拒否された",
    28: "時間切れ",
    35: "暗号通信の開始で遮断された",
    60: "証明書を検証できない",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", action="append", default=[], help="追加で調べるホスト名")
    args = parser.parse_args()

    nosana_host = urlsplit(nosana_base_url()).hostname
    hosts = list(dict.fromkeys([nosana_host, *args.host, *REFERENCE_HOSTS]))

    daytona = client()
    sandbox = daytona.create(
        CreateSandboxFromSnapshotParams(language="python", labels=LABELS, auto_stop_interval=15, ephemeral=True),
        timeout=180,
    )
    print(f"created: {sandbox.id}", flush=True)
    results: dict[str, int] = {}
    try:
        for host in hosts:
            url = shlex.quote(f"https://{host}/")
            script = f"curl -sS -o /dev/null -w 'http=%{{http_code}}' --max-time 15 {url} 2>&1; echo \" exit=$?\""
            _, output = bash(sandbox, script, timeout=30)
            last = output.strip().splitlines()[-1] if output.strip() else ""
            exit_code = int(last.rsplit("exit=", 1)[-1]) if "exit=" in last else -1
            results[host] = exit_code
            meaning = CURL_EXIT.get(exit_code, "その他の失敗")
            print(f"{host:32} curl exit {exit_code:>3}  {meaning}  [{output.strip()}]", flush=True)
    finally:
        daytona.delete(sandbox, timeout=120, wait=True)
        print(f"deleted: {sandbox.id}", flush=True)

    reachable = results.get(nosana_host) == 0
    print(f"\nNosana ({nosana_host}): {'届く' if reachable else '届かない'}")
    if not reachable and all(results.get(host) == 0 for host in REFERENCE_HOSTS):
        print("比較用の接続先には届くので、Daytona 側の通信制限の可能性が高い（README の「既知のブロッカー」を参照）")
    return 0 if reachable else 1


if __name__ == "__main__":
    sys.exit(main())
