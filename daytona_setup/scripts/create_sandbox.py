"""サンドボックスを作り、pytest と DSH が動く状態まで準備する。

使い方:
    python scripts/create_sandbox.py                                   # Daytona だけ（Nosana なし）
    NOSANA_MODEL=... python scripts/create_sandbox.py --nosana         # 鍵が要らない接続先（自前デプロイ）
    NOSANA_MODEL=... python scripts/create_sandbox.py --nosana --secret-name NOSANA_API_KEY
                                                                       # 鍵を Daytona の Secret で渡す

出力の最後の1行が JSON（{"sandbox_id": ...}）。後続のスクリプトはこの ID を使う。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from daytona import CreateSandboxFromSnapshotParams

from common import LABELS, bash, client, nosana_base_url

ROOT = Path(__file__).resolve().parent.parent

# orchestrator_a/run.py と DSH は NOSANA_API_KEY が空だと止まる。
# 鍵が要らない接続先（job.json の Ollama など）では、この意味のない値を入れておく。
NO_KEY_PLACEHOLDER = "no-key-required"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", help="サンドボックス名（省略時は自動）")
    parser.add_argument("--auto-stop", type=int, default=15, help="操作がなければ何分で自動停止するか")
    parser.add_argument("--auto-delete", type=int, default=60, help="停止してから何分で自動削除するか")
    parser.add_argument("--ttl", type=int, default=240, help="作成から何分で強制削除するか（保険）")
    parser.add_argument("--nosana", action="store_true", help="Nosana の環境変数を付ける")
    parser.add_argument("--secret-name", help="Nosana の鍵を入れた Daytona Secret の名前（鍵が要る接続先で使う）")
    args = parser.parse_args()

    env_vars: dict[str, str] = {}
    secrets: dict[str, str] | None = None
    if args.nosana:
        if not os.environ.get("NOSANA_MODEL"):
            sys.exit("NOSANA_MODEL が未設定です")
        env_vars["NOSANA_MODEL"] = os.environ["NOSANA_MODEL"]
        env_vars["NOSANA_BASE_URL"] = nosana_base_url()
        if args.secret_name:
            # 環境変数名 -> Daytona Secret 名。サンドボックス内には本物の鍵は入らない。
            secrets = {"NOSANA_API_KEY": args.secret_name}
        elif "inference.nosana.com" in env_vars["NOSANA_BASE_URL"]:
            sys.exit("inference.nosana.com は鍵が必須です。--secret-name で Daytona Secret を指定してください")
        else:
            env_vars["NOSANA_API_KEY"] = NO_KEY_PLACEHOLDER
    elif args.secret_name:
        parser.error("--secret-name は --nosana と一緒に使います")

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
        code, output = bash(sandbox, f"bash {home}/bootstrap.sh 2>&1", timeout=300)
        print(output)
        if code != 0:
            raise RuntimeError(f"bootstrap が失敗しました (exit {code})")
    except Exception:
        # 準備に失敗したサンドボックスは残さない。
        daytona.delete(sandbox)
        print(f"deleted (準備失敗のため): {sandbox.id}", file=sys.stderr)
        raise

    print(json.dumps({"sandbox_id": sandbox.id, "home": home}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
