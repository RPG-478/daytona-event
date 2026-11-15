# テスト自動生成・修正ループ(Web UI / 状態管理)

対象の Python ファイルを入力すると、テスト生成 → Daytona で pytest → 失敗ログで修正 を上限付きで回し、状態・テスト・ログを画面に出す。

## 起動

```sh
cp .env.example .env   # DAYTONA_API_KEY を入れる
# nosana.env の NOSANA_API_KEY と NOSANA_MODEL を埋める(テンプレートは nosana.env.example)
npm run check:nosana   # モデル一覧 → チャット → ツール呼び出しを確認。モデル名はここに出る一覧から選ぶ
npm start              # http://127.0.0.1:3000
```

Nosana の接続先は既定でマネージド推論 `https://inference.nosana.com/v1` を使う。API キーは deploy.nosana.com → Account → API Keys で発行する。自分で vLLM を Nosana にデプロイした場合だけ、`NOSANA_BASE_URL` をそのサービス URL(`.../v1`)に変える。

起動ログに、生成器・実行器ごとの設定状況(OK / 未設定)が出る。未設定のものは UI でも選べない。

## 構成

| ファイル | 役割 | 担当 |
|---|---|---|
| `server.mjs` | HTTP API・SSE・静的配信。Ctrl+C で実行中の処理を中止し、サンドボックスを削除してから終了 | B |
| `public/index.html` | 入力・進捗・結果表示 | B |
| `src/runs.mjs` | 受付・入力検証・同時実行数・全体タイムアウト・中止 | B |
| `src/loop.mjs` | 生成 → 実行 → 判定 → 修正のループ、必ず後始末 | B(A と調整) |
| `nosana.env` / `scripts/check-nosana.mjs` | Nosana の接続設定と接続確認 | Nosana 担当 |
| `src/generators/nosana.mjs` | Nosana(OpenAI 互換)へ直接依頼 | A が調整 |
| `src/generators/prompt.mjs` | プロンプトとコードブロック抽出 | A が調整 |
| `src/backends/dsh-daytona.mjs` | DSH 経路: Daytona に DSH を入れ、`../orchestrator_a/run.py` を実行して結果 JSON を取り込む | B(run.py は A) |
| `src/generators/mock.mjs` / `src/runners/mock.mjs` | 接続なしで状態遷移を確認するモック | B |
| `src/runners/daytona.mjs` → `sandbox.mjs`, `judge.mjs` | Daytona 実行・判定 | Daytona 担当 |

## 状態

- 全体: `queued` → `running`(phase: `preparing` / `generating` / `executing` / `cleanup`)→ `passed` / `failed`(試行上限)/ `timeout` / `error` / `cancelled`
- 試行ごと: `pass` / `test_fail` / `compile_error` / `no_tests` / `timeout` / `bad_response` / `api_error` / `empty_response` / `aborted`
- `no_tests` と `bad_response` は成功にせず、修正を依頼して再試行する。`api_error` などのモデル側エラーと pytest タイムアウトは、その時点で終了する

## DSH 経路(生成「DSH + Nosana」)

1件ごとにサンドボックスを作り、`pytest` と `@deepseek-ai/dsh@0.2.2-rc.1`(`DSH_VERSION` で変更可)を入れる。そこに `orchestrator_a/run.py` と対象コード(`solution.py` として配置)を置き、`python3 run.py --source solution.py --attempts N --timeout T` を実行する。Daytona 側のコマンドタイムアウトは T+30 秒にしている。

- 生成・pytest 実行・修正のループは run.py(DSH)が担う。B 側はサンドボックスの用意、結果 JSON の取り込み、削除だけを行う
- サンドボックスには `NOSANA_BASE_URL` / `NOSANA_MODEL` / `NOSANA_API_KEY` だけを渡す。`DAYTONA_API_KEY` は渡さない
- run.py は結果を終了時にまとめて返すため、試行ごとの状態は終了後に表示される
- **既知のブロッカー**: 現状の Daytona 組織では、サンドボックスから `inference.nosana.com` へ接続できない(curl exit 35 で遮断。github.com と registry.npmjs.org へは通る)。DSH は TRANSPORT エラーで終了する。Daytona 側でネットワーク制限を解除する(Tier を上げる、または許可リストに追加する)まで、DSH 経路での実接続はできない

## API

- `GET /api/config`: 使える生成器・実行器と上限(秘密の値は返さない)
- `POST /api/runs` `{ filename, code, instructions?, generator: mock|nosana|dsh, runner: mock|daytona, scenario? }`(dsh は runner=daytona のみ)
- `GET /api/runs` / `GET /api/runs/:id` / `GET /api/runs/:id/events`(SSE)/ `POST /api/runs/:id/cancel`

## デモ手順

1. 生成「モック」+ 実行「モック」+ シナリオ「1回目失敗 → 2回目で修正」で、画面の流れを見せる(モックであることは画面に表示される)
2. 生成「モック」+ 実行「Daytona」で、本物のサンドボックスで pytest が走り、削除されるところを見せる
3. 生成「Nosana」+ 実行「Daytona」+ サンプル `calc.py` で、実接続の1件を通す。最終的なテストのアサーション内容も確認する

## 確認済み(2026-11-15)

- モックの全シナリオ(初回成功 / 修正後成功 / 上限到達 / テスト0件 / タイムアウト / 応答形式不正 / API エラー)と中止
- 生成モック + 実行 Daytona: サンドボックスの作成、pytest の失敗 → 成功、削除まで
- DSH 経路(ダミーの Nosana 認証情報): サンドボックス作成、Node v24.22.1、DSH 0.2.2-rc.1 のインストール、run.py の実行、結果 JSON の取り込み、削除。DSH は上記のネットワーク制限により TRANSPORT で終了
- 未確認: 実際の API キーでの Nosana 実接続、DSH + Nosana で1件を通すこと

## 既知の制限

- 状態はメモリ上にのみ保持(再起動で消える)。認証なしで 127.0.0.1 のみで待ち受ける
- 言語は Python / pytest、単一ファイルのみ
- 中止しても、実行中の Daytona コマンドそのものは止まらない(サンドボックスごと削除する)
