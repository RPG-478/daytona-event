"""サンドボックスの停止・削除（片付け）。

使い方:
    python scripts/cleanup.py --id <sandbox_id>          # 1つ削除
    python scripts/cleanup.py --id <sandbox_id> --stop   # 停止だけ（中身は残る）
    python scripts/cleanup.py --all                      # このプロジェクトのラベルが付いたものを全部削除
    python scripts/cleanup.py --list                     # 残っているものを一覧表示（何も消さない）

削除後に一覧を取り直し、本当に消えたかを確認してから終了する（残っていれば終了コード 1）。
"""

from __future__ import annotations

import argparse
import sys

from daytona import DaytonaNotFoundError, ListSandboxesQuery

from common import LABELS, client


def ours(daytona):
    return list(daytona.list(ListSandboxesQuery(labels=LABELS)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--id", help="対象のサンドボックスID")
    target.add_argument("--all", action="store_true", help="このプロジェクトのサンドボックスを全部")
    target.add_argument("--list", action="store_true", help="一覧表示だけ")
    parser.add_argument("--stop", action="store_true", help="削除せず停止だけ")
    args = parser.parse_args()

    daytona = client()

    if args.list:
        for sandbox in ours(daytona):
            print(f"{sandbox.id}  {sandbox.state}")
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
            state = str(daytona.get(sandbox.id).state)
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
