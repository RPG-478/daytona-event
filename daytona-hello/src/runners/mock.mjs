// Daytona を使わずに状態遷移を確かめるモック実行器。コードは実行しない。
// テストに埋め込まれた `# MOCK: <結果>` を読み、pytest 風の結果を返す。

const sleep = ms => new Promise(r => setTimeout(r, ms))

export async function openMockRunner() {
  await sleep(500)
  async function run(files, _command, timeoutSec) {
    await sleep(900)
    const test = files.find(f => f.path.startsWith('test_'))?.content ?? ''
    const outcome = test.match(/# MOCK: (\w+)/)?.[1] ?? 'pass'
    const name = files.find(f => f.path.startsWith('test_'))?.path ?? 'test_x.py'
    switch (outcome) {
      case 'fail':
        return {
          exitCode: 1, timedOut: false, stderr: '',
          stdout: `F\n${name}:5: in test_module_imports\n    assert mod is None\nE   AssertionError: assert <module> is None\n` +
            `FAILED ${name}::test_module_imports - AssertionError\n1 failed in 0.01s (mock)`,
        }
      case 'no_tests':
        return { exitCode: 5, timedOut: false, stderr: '', stdout: 'no tests ran in 0.01s (mock)' }
      case 'timeout':
        return { exitCode: -1, timedOut: true, stdout: '', stderr: `(mock) command timed out after ${timeoutSec}s` }
      default:
        return { exitCode: 0, timedOut: false, stderr: '', stdout: '.\n1 passed in 0.01s (mock)' }
    }
  }
  return { name: 'mock', run, close: async () => {}, info: { id: 'mock' } }
}
