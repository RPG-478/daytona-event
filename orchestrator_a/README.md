# 担当A: DSH によるテスト生成・修正

単一の Python ファイルを対象に、DSH の headless モードで pytest テストを生成し、実行結果を受けて最大指定回数まで修正する。生成されたテストは別プロセスで `pytest` を実行して判定する。通常のテストが1件以上成功する必要があり、テスト0件・全件スキップ・XPASSのみの場合は成功にならない。

**実行場所**: Daytona の使い捨てサンドボックス内を想定。DSH や生成されたコードはコマンドを実行でき、プロンプトだけでは権限・通信を制限できない。信頼できないコードをホストで実行しない。現時点では Daytona の作成・削除、Nosana への実接続、担当Bの画面との結合は未実装・未検証。

## 前提

- Python 3 と `pytest`、Node.js 24.9 以上、[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) の `dsh` コマンド（本実装の確認対象: `0.2.2-rc.1`）
- OpenAI Chat Completions 互換の Nosana エンドポイントとモデル。ツール呼び出しに対応していることを別途確認する
- Daytona 側でネットワーク・ファイルアクセス・実行時間を制限し、終了時にサンドボックスを削除する

DSH が Nosana に接続するため `NOSANA_API_KEY` は DSH プロセス内に存在する。DSH のツールが実行するコードから参照できる可能性があるため、専用の最小権限・短期間の認証情報を使用し、サンドボックスへの入力は信頼できるものに限る。独立した pytest 実行では同環境変数を外すが、これは完全な秘密情報の隔離を保証しない。DSHの標準エラーは推論や認証情報を含み得るため、結果には出力しない。生成コードや pytest ログを共有する前にも内容を確認する。

## 起動

Daytona サンドボックス内で依存を準備し、認証情報を安全な方法で設定する。値は共有チャットや Git に載せない。

```sh
python3 -m pip install pytest
npm install --global @deepseek-ai/dsh@0.2.2-rc.1
export NOSANA_BASE_URL='https://<nosana-endpoint>/v1'
export NOSANA_MODEL='<model-id>'
export NOSANA_API_KEY='<credential>'
python3 orchestrator_a/run.py --source samples/solution.py --attempts 3 --timeout 180
```

`NOSANA_BASE_URL` はチャットAPIのベースURL、`NOSANA_MODEL` はモデルID。エンドポイント側の認証が不要な場合も、DSH の環境変数要件に合う値が必要か確認する。`--dsh /path/to/dsh` で実行ファイルを指定可能。設定は一時的な DSH ホームとパッチに書き出し、ジョブ終了後に削除する。

## 担当B・Daytona担当への受け渡し

- `python3 orchestrator_a/run.py --source <sandbox内のPythonファイル>` をサンドボックスで実行する。ソースは `solution.py`、テストは `test_solution.py` として一時ワークスペースに配置する。
- 標準出力は JSON オブジェクト1つ。`status` は `succeeded` / `failed` / `timed_out`、`attempts`、`test_code`、`logs`、`message`、通常実行時の `duration_seconds` を返す。終了コードは成功時0、それ以外1。
- `--attempts` は1〜5、`--timeout` は全試行を通した秒数。タイムアウト時は子プロセスグループを終了する。これは Daytona サンドボックス自体の削除ではないため、呼び出し側が成功・失敗・タイムアウトのすべてで削除する。
- Daytona のコマンド実行側にも別途タイムアウトを設定する。既定値のままにせず、`--timeout` に終了処理と結果回収の余裕（少なくとも15秒）を加えた値以上にする。Daytona API 自体がタイムアウトした場合も、担当B側で `timed_out` として扱い、プロセス・サンドボックスの後始末を行う。[Daytona のコマンド実行](https://www.daytona.io/docs/en/process-code-execution/)の利用中の SDK 版で設定方法と単位を確認する。
- ログは各項目最大約16,000文字。`test_code` のファイル上限は100KB。JSON は処理終了後に返り、ライブ配信は未対応。
- DSH のエラーは `error_code` に一部の既知コードだけを返し、それ以外は `DSH_ERROR` とする。詳細な標準エラーは外部に返さない。
- DSH に渡す修正指示には pytest の終了コードとログを含める。テストが通っても内容の妥当性は人が確認する。

## 確認

```sh
python3 -m pytest -q tests
```

テストは DSH を模したプロセスで成功・修正・未検出・エラー・タイムアウトを検証する。実際の DSH、Nosana、Daytona の結合テストの代わりではない。
