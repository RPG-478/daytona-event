# Daytona 担当: 運用の補助スクリプト

サンドボックスでのテスト実行そのものは [`daytona-hello/`](../daytona-hello/README.md) が担っている（Web UI、`sandbox.mjs`、DSH 経路）。このフォルダはその外側を補うもの。

- サンドボックスから Nosana に届くかの切り分け（`check_network.py`）
- 消し残しの確認と削除（`cleanup.py`）
- Web UI を通さずに、コマンド1つを時間制限つきで実行してログと終了コードを回収（`run_in_sandbox.py`）

## 現在の状態

| 項目 | 状態 |
|---|---|
| サンドボックスの作成、pytest、削除 | 確認済み（`daytona-hello/README.md` の記録による） |
| 既定のサンドボックスへの DSH 導入（Node v24.22.1 / DSH 0.2.2-rc.1） | 確認済み（同上） |
| サンドボックスから Nosana への接続 | **届かない**（同上。下の「既知のブロッカー」） |
| このフォルダのスクリプト | 文法と読み込み、手元でできる範囲の動作だけ確認。**Daytona 上では未実行** |

## 既知のブロッカー: サンドボックスから Nosana に届かない

`daytona-hello/README.md` の記録では、サンドボックスから `inference.nosana.com` へは curl exit 35 で遮断され、`github.com` と `registry.npmjs.org` へは届く。

Daytona の文書（[Network Limits](https://www.daytona.io/docs/en/network-limits/)）によると、組織の Tier 1・2 は外向きの通信が制限され、サンドボックス単位の設定では解除できない。パッケージ配布元などの必須サービスだけが届く。Tier 3（500 ドルの入金が条件）以上は既定で全開になる。症状はこの制限と一致する。チームの組織がどの Tier かは未確認。

`job.json` で自前デプロイする接続先（`*.node.k8s.prd.nos.ci`）も、同じ制限にかかる可能性がある。URL が決まったら次で確かめられる:

```sh
NOSANA_BASE_URL='https://<サービスURL>/v1' .venv/bin/python scripts/check_network.py
```

## 環境変数名

`daytona-hello` と `orchestrator_a` と同じ名前。値はチャットにも Git にも書かない。

| 名前 | 内容 |
|---|---|
| `DAYTONA_API_KEY` | Daytona の API キー。スクリプトを動かす側だけに置く |
| `NOSANA_BASE_URL` | OpenAI 互換の接続先。`/v1` まで含める。省略時は `https://inference.nosana.com/v1` |
| `NOSANA_MODEL` | モデルID（`job.json` の場合は `glm-4.7-flash:q4_K_M`） |
| `NOSANA_API_KEY` | Nosana の鍵。下の「鍵の渡し方」を参照 |

### 鍵の渡し方

- **鍵が要らない接続先**（`job.json` の Ollama は標準では鍵を求めない。実際のデプロイで要否を確認すること）: `create_sandbox.py --nosana` が意味のない値 `no-key-required` を入れる。`orchestrator_a/run.py` と DSH は空の `NOSANA_API_KEY` を受け付けないため
- **鍵が要る接続先**（`inference.nosana.com`）: Daytona の Secret に登録し、`--secret-name` で指定する。サンドボックス内には置き換え用の仮の値だけが入り、本物は Daytona の通信の出口で差し替わるので、DSH のツールが実行するコードから本物の鍵が読めない。チームの Daytona でこの機能が使えるかは未確認

`daytona-hello` の DSH 経路は、鍵をコマンドの環境変数としてそのまま渡している。

## 手順

```sh
cd daytona_setup
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export DAYTONA_API_KEY='<値>'
```

作成。最後の1行に `{"sandbox_id": ...}` が出る:

```sh
.venv/bin/python scripts/create_sandbox.py
NOSANA_BASE_URL='<URL>' NOSANA_MODEL='<モデルID>' .venv/bin/python scripts/create_sandbox.py --nosana
```

実行。標準出力は `logs/<実行名>/stdout.log`、標準エラーは `stderr.log`、終了コードは `exit_code` とスクリプト自身の終了コードに入る（時間切れは 124）。送ったファイルはサンドボックス内の `~/work/` に置かれる:

```sh
.venv/bin/python scripts/run_in_sandbox.py --id <sandbox_id> --upload sample --timeout 60 -- python3 -m pytest -q
```

担当A の `run.py` を Web UI を通さずに試す場合（リポジトリ全体を送る。`.env` や `nosana.env` などの鍵入りファイルは送らない）:

```sh
.venv/bin/python scripts/run_in_sandbox.py --id <sandbox_id> --upload .. --timeout 210 -- python3 orchestrator_a/run.py --source samples/solution.py --attempts 3 --timeout 180
```

片付け:

```sh
.venv/bin/python scripts/cleanup.py --list-all          # 鍵で見えるものを全部表示（何も消さない）
.venv/bin/python scripts/cleanup.py --id <sandbox_id>   # 1つ削除し、消えたことを確認
.venv/bin/python scripts/cleanup.py --all               # このフォルダのスクリプトが作ったものを全部削除
```

## タイムアウトと後始末

| 層 | `daytona-hello` | このフォルダ |
|---|---|---|
| コマンド単位 | pytest は `TEST_TIMEOUT_SEC`（既定 60 秒）。DSH 経路は `run.py --timeout` に 30 秒足した値 | `run_in_sandbox.py --timeout`。サンドボックス内の `timeout` コマンドで止め、124 を返す |
| 1件全体 | `RUN_TIMEOUT_SEC`（既定 600 秒） | なし（呼び出し側で決める） |
| サンドボックスの自動停止 | 15 分 | `--auto-stop`（既定 15 分） |
| 停止後の自動削除 | なし | `--auto-delete`（既定 60 分） |
| 作成からの強制削除 | なし | `--ttl`（既定 240 分） |

どちらも成功・失敗・時間切れのすべてで明示的に削除する。違いは削除に失敗したときで、`daytona-hello` が作ったサンドボックスは 15 分で停止するが、消されずに残る。`cleanup.py --list-all` で見つけて `--id` で消す。

## `daytona-hello` への提案（このブランチでは変更していない）

確認済みのコードを未検証の変更で壊さないよう、手を入れていない。採用するかはチームで決める。

- `sandbox.mjs` と `src/backends/dsh-daytona.mjs` の `daytona.create()` に `labels` と `autoDeleteInterval` を足す。消し残しが自動で消え、`cleanup.py --all` の対象にもなる
- 鍵が要る接続先を使う場合は、鍵を Daytona の Secret で渡す

## 未確認のこと

- チームの Daytona 組織の Tier と、Nosana への通信を通す方法
- `ttl_minutes` と Secret がチームの Daytona で使えるか
- DSH から Nosana（Ollama）へのツール呼び出しが通るか。DSH の案内（[モデル設定](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/providers.md)）では、OpenAI 互換の接続先が要求を拒否するときは `compat.supportsDeveloperRole: false` と `compat.maxTokensField: max_tokens` を試すとある
