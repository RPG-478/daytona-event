"""サンドボックスを作り、Python/pytest と DSH が動く状態まで準備する。

使い方:
    python scripts/create_sandbox.py                 # Daytona だけ（Nosana なし）
    python scripts/create_sandbox.py --nosana        # Nosana 接続つき

出力の最後の1行が JSON（{"sandbox_id": ...}）。後続のスクリプトはこの ID を使う。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from daytona import CreateSandboxFromSnapshotParams

from common import DSH_PROFILE_DIR, LABELS, bash, client

ROOT = Path(__file__).resolve().parent.parent

# 担当B の nosana.env.example と同じ既定値。自前でデプロイした場合だけ NOSANA_BASE_URL で上書きする。
DEFAULT_NOSANA_BASE_URL = "https://inference.nosana.com/v1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", help="サンドボックス名（省略時は自動）")
    parser.add_argument("--auto-stop", type=int, default=30, help="操作がなければ何分で自動停止するか")
    parser.add_argument("--auto-delete", type=int, default=60, help="停止してから何分で自動削除するか")
    parser.add_argument("--ttl", type=int, default=240, help="作成から何分で強制削除するか（保険）")
    parser.add_argument("--nosana", action="store_true", help="Nosana の環境変数と Secret を付ける")
    parser.add_argument("--secret-name", default="NOSANA_API_KEY", help="Daytona に登録した Secret の名前")
    args = parser.parse_args()

    env_vars: dict[str, str] = {}
    secrets: dict[str, str] | None = None
    if args.nosana:
        if not os.environ.get("NOSANA_MODEL"):
            sys.exit("NOSANA_MODEL が未設定です")
        env_vars["NOSANA_MODEL"] = os.environ["NOSANA_MODEL"]
        env_vars["NOSANA_BASE_URL"] = os.environ.get("NOSANA_BASE_URL") or DEFAULT_NOSANA_BASE_URL
        # 環境変数名 -> Daytona Secret 名。サンドボックス内には本物のキーは入らない。
        secrets = {"NOSANA_API_KEY": args.secret_name}

    daytona = client()
    sandbox = daytona.create(
        CreateSandboxFromSnapshotParams(
            name=args.name,
            language="python",
            labels=LABELS,
            env_vars=env_vars or None,
            secrets=secrets,
            auto_stop_interval=args.auto_stop,
            auto_delete_interval=args.auto_delete,
            ttl_minutes=args.ttl,
        ),
        timeout=180,
    )
    print(f"created: {sandbox.id}", flush=True)

    try:
        home = sandbox.get_user_home_dir()
        sandbox.fs.upload_file(str(ROOT / "scripts" / "bootstrap.sh"), f"{home}/bootstrap.sh")
        code, output = bash(sandbox, f"bash {home}/bootstrap.sh 2>&1", timeout=900)
        print(output)
        if code != 0:
            raise RuntimeError(f"bootstrap が失敗しました (exit {code})")

        if args.nosana:
            bash(sandbox, f"mkdir -p {home}/{DSH_PROFILE_DIR}")
            sandbox.fs.upload_file(
                str(ROOT / "dsh" / "cordis.patch.yml"), f"{home}/{DSH_PROFILE_DIR}/cordis.patch.yml"
            )
    except Exception:
        # 準備に失敗したサンドボックスは残さない。
        daytona.delete(sandbox)
        print(f"deleted (準備失敗のため): {sandbox.id}", file=sys.stderr)
        raise

    print(json.dumps({"sandbox_id": sandbox.id, "home": home}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
