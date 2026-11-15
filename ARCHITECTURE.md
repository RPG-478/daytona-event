# テスト自動生成・修正ツールの構成

対象コードからテストを生成し、隔離環境で実行する。失敗した場合はログをモデルに渡して修正を依頼する。

```mermaid
flowchart TD
    User["ユーザー"] -->|対象コードを入力して実行| UI["Web UI<br/>入力・進捗・結果表示"]

    UI -->|コードと実行指示| Orch["オーケストレーター<br/>全体の進行を管理"]

    Orch -->|テスト生成・修正を依頼| Nosana["Nosana<br/>LLMがテストコードを生成"]
    Nosana -->|生成したテスト| Orch

    Orch -->|対象コードとテストを渡す| Harness["ハーネス<br/>テスト実行・結果回収"]
    Harness -->|サンドボックスで実行| Daytona["Daytona<br/>隔離された実行環境"]
    Daytona -->|終了コード・ログ| Harness
    Harness -->|実行結果| Orch

    Orch --> Judge{"テスト成功？"}
    Judge -->|成功| Result["結果をまとめる"]
    Judge -->|失敗・上限未到達| Retry["失敗ログを使って<br/>修正を依頼"]
    Retry --> Nosana
    Judge -->|上限・タイムアウト| Result

    Result -->|テスト・ログ・最終状態| UI
```

- **Web UI**: 対象コードの入力、進捗と結果の表示。
- **オーケストレーター**: 生成、実行、判定、修正依頼の流れを管理。
- **ハーネス**: Daytonaでのテスト実行と結果の回収。
- **Nosana**: LLMによるテストコードの生成・修正。
- **Daytona**: テストを実行する隔離環境。

オーケストレーター担当の詳細は [task/orchestrator/task.md](task/orchestrator/task.md) を参照。
