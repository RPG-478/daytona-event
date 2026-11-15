// pytestの終了コード: 0=全合格, 1=失敗あり, 2=収集エラー(import/構文), 5=テスト0件
export function judge(r) {
  if (r.timedOut) return { status: 'timeout', summary: 'テストが時間内に終わらなかった' }

  const out = r.stdout + r.stderr
  const last = out.trim().split('\n').at(-1) ?? ''

  if (r.exitCode === 0) return { status: 'pass', summary: last }
  if (r.exitCode === 5) return { status: 'no_tests', summary: 'テストが1件も見つからなかった' }
  if (r.exitCode === 2 || /ERROR collecting|SyntaxError|ImportError/.test(out)) {
    return { status: 'compile_error', summary: last }
  }
  if (r.exitCode === 1) return { status: 'test_fail', summary: last }
  return { status: 'compile_error', summary: `想定外の終了コード ${r.exitCode}: ${last}` }
}

// モデルに戻すログを短くする(R-4)
export function formatLog(r, maxChars = 3000) {
  const text = (r.stdout + r.stderr)
    .replace(/\x1b\[[0-9;]*m/g, '')                 // 色コード
    .split('\n')
    .filter(l => !/^[=_-]{5,}/.test(l.trim()))      // 区切り線
    .filter(l => !/^\.?[.FEsx]+\s+\[\s*\d+%\]$/.test(l.trim())) // 進捗行
    .join('\n')
    .trim()
  return text.length > maxChars ? '...(前略)\n' + text.slice(-maxChars) : text
}
