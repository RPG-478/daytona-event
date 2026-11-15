// テスト生成・修正の指示文と、応答からのコード抽出。
// プロンプトの中身は担当 A が調整する前提の初期版。

const SYSTEM = `あなたは Python のテストを書くエンジニアです。
pytest で実行できるテストファイルを1つだけ書いてください。
- 出力は \`\`\`python のコードブロック1つだけにする。説明文は不要
- 対象モジュールは同じディレクトリにあるものとして import する
- 正常系・境界値・異常系を含め、assert を3つ以上書く
- 対象コードを書き換えたり、テストを skip したりしない
- ネットワークやファイルシステムに依存しない`

export function buildMessages({ code, filename, testFilename, instructions, previous }) {
  const moduleName = filename.replace(/\.py$/, '')
  const user = [
    `対象ファイル: ${filename}(import 名: ${moduleName})`,
    `テストファイル名: ${testFilename}`,
    instructions ? `追加の指示:\n${instructions}` : '',
    `\`\`\`python\n${code}\n\`\`\``,
  ].filter(Boolean).join('\n\n')

  const messages = [{ role: 'system', content: SYSTEM }, { role: 'user', content: user }]
  if (previous) {
    messages.push(
      { role: 'assistant', content: previous.test ? `\`\`\`python\n${previous.test}\n\`\`\`` : '(コードなし)' },
      {
        role: 'user',
        content: `前回のテストは「${previous.status}」でした。ログを読んでテストを修正し、修正後のテストファイル全体を再出力してください。` +
          `対象コードにバグがあると判断した場合も、テストの期待値を実装に合わせて歪めず、仕様として正しい期待値を書いてください。\n\n` +
          `\`\`\`\n${previous.log}\n\`\`\``,
      },
    )
  }
  return messages
}

// コードブロックがない・複数あるなど曖昧な応答は成功扱いにしない
export function extractSingleCodeBlock(content) {
  const blocks = [...content.matchAll(/```(?:python|py)?[^\S\n]*\n([\s\S]*?)```/g)].map(m => m[1].trim())
  const nonEmpty = blocks.filter(Boolean)
  if (nonEmpty.length === 0) {
    return { ok: false, kind: 'bad_response', message: 'コードブロックが見つからなかった', raw: content }
  }
  if (nonEmpty.length > 1) {
    return { ok: false, kind: 'bad_response', message: `コードブロックが ${nonEmpty.length} 個あり、どれを使うか決められない`, raw: content }
  }
  return { ok: true, test: nonEmpty[0] + '\n', raw: content }
}
