"""ローカルのフォルダをサンドボックスへ送り、コマンドを時間制限つきで実行する。

使い方:
    python scripts/run_in_sandbox.py --id <sandbox_id> --upload sample -- python3 -m pytest -q

結果:
    - 標準出力   -> logs/<実行名>/stdout.log
    - 標準エラー -> logs/<実行名>/stderr.log
    - 終了コード -> logs/<実行名>/exit_code、かつこのスクリプト自身の終了コード
      （時間切れは 124）
"""

from __future__ import annotations

import argparse
import shlex
import sys
import time
from pathlib import Path

from daytona import FileUpload

from common import bash, client

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules", "logs"}


def is_env_file(name: str) -> bool:
    """鍵が入りうるファイル（.env、nosana.env、.env.local など）。見本の *.example は送ってよい。"""
    if name.endswith(".example"):
        return False
    return name == ".env" or name.endswith(".env") or name.startswith(".env.")


def collect(local_dir: Path, remote_dir: str) -> list[FileUpload]:
    uploads = []
    for path in sorted(local_dir.rglob("*")):
        relative = path.relative_to(local_dir)
        if path.is_file() and not SKIP_DIRS.intersection(relative.parts) and not is_env_file(path.name):
            uploads.append(FileUpload(source=str(path), destination=f"{remote_dir}/{relative.as_posix()}"))
    return uploads


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--id", required=True, help="サンドボックスID")
    parser.add_argument("--upload", help="送るローカルフォルダ（省略時は送らない）")
    parser.add_argument("--workdir", default="work", help="サンドボックス内の作業フォルダ（ホームからの相対）")
    parser.add_argument("--timeout", type=int, default=300, help="コマンドの制限時間（秒）")
    parser.add_argument("--run-name", default=time.strftime("%Y%m%d-%H%M%S"), help="ログの保存名")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- の後ろに実行コマンド")
    args = parser.parse_args()

    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("実行コマンドがありません（-- の後ろに書いてください）")

    sandbox = client().get(args.id)
    home = sandbox.get_user_home_dir()
    workdir = f"{home}/{args.workdir}"
    remote_logs = f"{home}/.runs/{args.run_name}"
    bash(sandbox, f"mkdir -p {shlex.quote(workdir)} {shlex.quote(remote_logs)}")

    if args.upload:
        uploads = collect(Path(args.upload).resolve(), workdir)
        sandbox.fs.upload_files(uploads)
        print(f"uploaded: {len(uploads)} files -> {workdir}", flush=True)

    # 時間制限はサンドボックスの中の timeout コマンドでかける（切れたら 124）。
    # 外側の SDK の制限は少し長めにして、中の制限が先に働くようにする。
    inner = f"cd {shlex.quote(workdir)} && timeout --kill-after=10 {args.timeout} {shlex.join(command)}"
    script = (
        f"({inner}) > {remote_logs}/stdout.log 2> {remote_logs}/stderr.log; "
        f"echo $? > {remote_logs}/exit_code; cat {remote_logs}/exit_code"
    )
    _, output = bash(sandbox, script, timeout=args.timeout + 60)
    exit_code = int(output.strip().splitlines()[-1])

    local_logs = ROOT / "logs" / args.run_name
    local_logs.mkdir(parents=True, exist_ok=True)
    for name in ("stdout.log", "stderr.log", "exit_code"):
        (local_logs / name).write_bytes(sandbox.fs.download_file(f"{remote_logs}/{name}"))

    print((local_logs / "stdout.log").read_text(errors="replace"), end="")
    stderr_text = (local_logs / "stderr.log").read_text(errors="replace")
    if stderr_text:
        print(stderr_text, end="", file=sys.stderr)
    print(f"\nexit_code: {exit_code}  (logs: {local_logs})", flush=True)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
