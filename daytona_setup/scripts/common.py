"""Daytona 担当スクリプトの共通処理。

秘密の値（API キー）は環境変数からだけ読み、表示もファイル保存もしない。
"""

from __future__ import annotations

import os
import shlex
import sys

from daytona import Daytona

# このラベルが付いたサンドボックスだけを「このフォルダのスクリプトが作ったもの」として扱う。
# daytona-hello（Web UI）が作るサンドボックスにはラベルが付かないので、一括削除の対象にならない。
LABELS = {"project": "hackathon-dsh", "role": "test-runner"}

# daytona-hello/src/config.mjs と同じ既定値。
DEFAULT_NOSANA_BASE_URL = "https://inference.nosana.com/v1"


def client() -> Daytona:
    """DAYTONA_API_KEY（必須）と DAYTONA_API_URL / DAYTONA_TARGET（任意）を環境変数から読む。"""
    if not os.environ.get("DAYTONA_API_KEY"):
        sys.exit("DAYTONA_API_KEY が未設定です（値は環境変数で渡してください）")
    return Daytona()


def nosana_base_url() -> str:
    return (os.environ.get("NOSANA_BASE_URL") or DEFAULT_NOSANA_BASE_URL).rstrip("/")


def bash(sandbox, script: str, *, cwd: str | None = None, timeout: int = 120):
    """サンドボックス内で bash として実行し、(終了コード, 出力) を返す。"""
    response = sandbox.process.exec(f"bash -c {shlex.quote(script)}", cwd=cwd, timeout=timeout)
    return response.exit_code, response.result
