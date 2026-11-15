# Daytona 担当: サンドボックスの作成・テスト実行・片付け

DSH と pytest を動かす Daytona サンドボックスを、作成から削除までスクリプトで扱う。

## 現在の状態

**Daytona 上ではまだ1回も実行していない。** 下の手順は未検証で、実機で確認した時点でこの節を更新する。

| 項目 | 状態 |
|---|---|
| スクリプトの文法・読み込み | 確認済み |
| `sample/` の pytest（手元で実行） | 3件成功 |
| DSH の版・動作条件・設定方法 | DSH 本体のリポジトリと npm で確認済み（`0.2.2-rc.1`、Node.js 24.9 以上） |
| サンドボックス作成、`bootstrap.sh` | 未検証 |
| DSH の起動とツール呼び出し | 未検証 |
| Nosana への接続、Daytona Secret による鍵の受け渡し | 未検証 |
| タイムアウト、停止・削除 | 未検証 |

## 構成

| ファイル | 役割 |
|---|---|
| `scripts/create_sandbox.py` | サンドボックスを作り、`bootstrap.sh` を流す。最後の1行に `{"sandbox_id": ...}` を出す |
| `scripts/bootstrap.sh` | サンドボックス内の準備（pytest、Node.js 24、DSH） |
| `scripts/run_in_sandbox.py` | フォルダを送り、時間制限つきでコマンドを実行し、ログと終了コードを回収する |
| `scripts/cleanup.py` | 停止・削除・一覧。削除後に本当に消えたかを確認する |
| `dsh/cordis.patch.yml` | DSH を Nosana へ向ける設定（値はすべて環境変数から読む） |
| `sample/` | 動作確認用の小さなコードとテスト |

## 環境変数名

値はチャットにも Git にも書かない。担当A・担当B と同じ名前を使う。

| 名前 | 置き場所 | 内容 |
|---|---|---|
| `DAYTONA_API_KEY` | スクリプトを動かす側 | Daytona の API キー |
| `NOSANA_MODEL` | スクリプトを動かす側 → サンドボックス | モデルID |
| `NOSANA_BASE_URL` | 同上（省略時 `https://inference.nosana.com/v1`） | OpenAI 互換の接続先。`/v1` まで含める |
| `NOSANA_API_KEY` | Daytona の Secret → サンドボックス | Nosana の API キー |

`NOSANA_API_KEY` は Daytona の Secret（名前 `NOSANA_API_KEY`、送信先 `inference.nosana.com`）として登録する想定。サンドボックス内の環境変数には置き換え用の仮の値だけが入り、本物の値は Daytona の通信の出口で差し替わる。DSH のツールが実行するコードから本物の鍵が読めない形になる。チームの Daytona でこの機能が使えるかは未確認。

## 手順

```sh
cd daytona_setup
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export DAYTONA_API_KEY='<値>'
```

作成（Nosana なし／あり）:

```sh
.venv/bin/python scripts/create_sandbox.py
NOSANA_MODEL='<モデルID>' .venv/bin/python scripts/create_sandbox.py --nosana
```

テスト実行。標準出力は `logs/<実行名>/stdout.log`、標準エラーは `stderr.log`、終了コードは `exit_code` とスクリプト自身の終了コードに入る（時間切れは 124）:

```sh
.venv/bin/python scripts/run_in_sandbox.py --id <sandbox_id> --upload sample --timeout 300 -- python3 -m pytest -q
```

送ったファイルはサンドボックス内の `~/work/` に置かれる。担当A の `orchestrator_a/run.py` も同じ形で実行できる想定:

```sh
.venv/bin/python scripts/run_in_sandbox.py --id <sandbox_id> --upload .. --timeout 240 -- python3 orchestrator_a/run.py --source samples/solution.py --attempts 3 --timeout 180
```

片付け:

```sh
.venv/bin/python scripts/cleanup.py --id <sandbox_id>   # 1つ削除
.venv/bin/python scripts/cleanup.py --all               # このプロジェクトのものを全部削除
.venv/bin/python scripts/cleanup.py --list              # 残っているものを表示
```

## タイムアウトと後始末

三重にしてある。

1. コマンド単位: `run_in_sandbox.py --timeout <秒>`。サンドボックス内の `timeout` コマンドで止め、終了コード 124 を返す
2. サンドボックス単位: 作成時の `--auto-stop`（既定 30 分で自動停止）と `--auto-delete`（停止から 60 分で自動削除）
3. 保険: `--ttl`（既定 240 分。状態にかかわらず作成からこの時間で削除）

呼び出し側は成功・失敗・時間切れのどの場合も `cleanup.py --id` を呼ぶ。2 と 3 は呼び忘れたときの保険。

## 未確認のこと

- 既定のサンドボックスに入っている Node.js の版と、`bootstrap.sh` の入れ方が通るか
- `ttl_minutes` と Secret がチームの Daytona で使えるか
- DSH から Nosana へのツール呼び出しが通るか（`compat` の調整が要るか）
- 準備済みの状態をスナップショットにして、作成を速くできるか
