import { openRunner } from './sandbox.mjs'

const runner = await openRunner()
try {
  const files = [
    { path: 'calc.py', content: 'def add(a, b):\n    return a + b\n' },
    { path: 'test_calc.py', content:
      'from calc import add\n\n' +
      'def test_ok():\n    assert add(1, 2) == 3\n\n' +
      'def test_ng():\n    assert add(2, 2) == 5\n' },
  ]
  const r = await runner.run(files, 'python3 -m pytest -q', 60)
  const { judge, formatLog } = await import('./judge.mjs')
  console.log(judge(r)); console.log(formatLog(r))
} finally {
  await runner.close()
}
