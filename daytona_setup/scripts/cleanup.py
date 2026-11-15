"""サンドボックスの停止・削除（片付け）。

使い方:
    python scripts/cleanup.py --list-all                 # 鍵で見えるものを全部表示（何も消さない）
    python scripts/cleanup.py --list                     # このフォルダのスクリプトが作ったものだけ表示
    python scripts/cleanup.py --id <sandbox_id>          # 1つ削除
    python scripts/cleanup.py --id <sandbox_id> --stop   # 停止だけ（中身は残る）
    python scripts/cleanup.py --all                      # このフォルダのスクリプトが作ったものを全部削除

Web UI（daytona-hello）が作ったサンドボックスにはラベルがないので --all では消えない。
--list-all で見つけて --id で消す。

削除後に取り直し、本当に消えたかを確認してから終了する（残っていれば終了コード 1）。
"""

from __future__ import annotations

import argparse
import sys

from daytona import DaytonaNotFoundError, ListSandboxesQuery

from common import LABELS, client


def state_of(sandbox) -> str:
    return str(getattr(sandbox.state, "value", sandbox.state))


def describe(sandbox) -> str:
    labels = ",".join(f"{key}={value}" for key, value in (sandbox.labels or {}).items()) or "-"
    return f"{sandbox.id}  {state_of(sandbox):10}  created={sandbox.created_at}  labels={labels}"


def ours(daytona):
    return list(daytona.list(ListSandboxesQuery(labels=LABELS)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--id", help="対象のサンドボックスID")
    target.add_argument("--all", action="store_true", help="このフォルダのスクリプトが作ったものを全部")
    target.add_argument("--list", action="store_true", help="このフォルダのスクリプトが作ったものを表示")
    target.add_argument("--list-all", action="store_true", help="鍵で見えるものを全部表示（ラベルなしも含む）")
    parser.add_argument("--stop", action="store_true", help="削除せず停止だけ")
    args = parser.parse_args()

    daytona = client()

    if args.list or args.list_all:
        sandboxes = ours(daytona) if args.list else list(daytona.list())
        for sandbox in sandboxes:
            print(describe(sandbox))
        print(f"{len(sandboxes)} 件")
        return 0

    if args.id:
        try:
            targets = [daytona.get(args.id)]
        except DaytonaNotFoundError:
            print(f"already gone: {args.id}")
            return 0
    else:
        targets = ours(daytona)

    for sandbox in targets:
        if args.stop:
            daytona.stop(sandbox)
            print(f"stopped: {sandbox.id}")
        else:
            daytona.delete(sandbox, timeout=120, wait=True)
            print(f"deleted: {sandbox.id}")

    if args.stop:
        return 0

    # 消えたことの確認。
    remaining = []
    for sandbox in targets:
        try:
            state = state_of(daytona.get(sandbox.id))
        except DaytonaNotFoundError:
            continue
        if "destroy" not in state.lower():
            remaining.append((sandbox.id, state))
    for sandbox_id, state in remaining:
        print(f"STILL PRESENT: {sandbox_id}  {state}", file=sys.stderr)
    print(f"verified: {len(targets) - len(remaining)}/{len(targets)} deleted")
    return 1 if remaining else 0


if __name__ == "__main__":
    sys.exit(main())
