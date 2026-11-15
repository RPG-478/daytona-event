// Nosana / DSH につながらない間に UI と状態遷移を確かめるためのモック生成器。
// 生成したテストに `# MOCK: <結果>` を埋め込み、モック実行器がそれを見て結果を返す。

export const MOCK_SCENARIOS = {
  fix: '1回目失敗 → 2回目で修正して成功',
  pass: '初回成功',
  exhaust: '毎回失敗して上限到達',
  no_tests: 'テストが1件も見つからない',
  timeout: 'テスト実行がタイムアウト',
  bad_response: '1回目はコードブロックなしの応答 → 2回目成功',
  api_error: 'モデル API エラー',
}

const sleep = (ms, signal) => new Promise((resolve, reject) => {
  const t = setTimeout(resolve, ms)
  signal?.addEventListener('abort', () => { clearTimeout(t); reject(signal.reason) }, { once: true })
})

export function createMockGenerator({ scenario = 'fix' } = {}) {
  async function generate({ filename, attempt, signal }) {
    await sleep(700, signal)
    const mod = filename.replace(/\.py$/, '')

    if (scenario === 'api_error') return { ok: false, kind: 'api_error', message: 'HTTP 503: (mock) model is loading' }
    if (scenario === 'bad_response' && attempt === 1) {
      return { ok: false, kind: 'bad_response', message: 'コードブロックが見つからなかった', raw: '(mock) テストを書きました!' }
    }

    let outcome = 'pass'
    if (scenario === 'fix' && attempt === 1) outcome = 'fail'
    if (scenario === 'exhaust') outcome = 'fail'
    if (scenario === 'no_tests') outcome = 'no_tests'
    if (scenario === 'timeout') outcome = 'timeout'

    const expected = outcome === 'fail' ? 'None  # 誤った期待値' : 'not None'
    const test = `# MOCK: ${outcome}  (モック生成器の出力。実際のモデル出力ではない)
import ${mod}


def test_module_imports():
    assert ${mod} is ${expected}
`
    return { ok: true, test, raw: '```python\n' + test + '```' }
  }
  return { name: 'mock', generate }
}
