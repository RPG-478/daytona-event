import { Daytona } from '@daytona/sdk'

const daytona = new Daytona({ apiKey: process.env.DAYTONA_API_KEY })
const sandbox = await daytona.create()

try {
  // 1. ツールチェーンの確認(D-2)
  for (const cmd of ['python3 --version', 'go version', 'node -v']) {
    const r = await sandbox.process.executeCommand(cmd)
    console.log(`${cmd} -> exit ${r.exitCode}: ${r.result.trim()}`)
  }

  // 2. 対象ファイルとテストを置く(R-2)
  const src = 'def add(a, b):\n    return a + b\n'
  const test = 'from calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n'
  await sandbox.fs.createFolder('work', '755')
  await sandbox.fs.uploadFile(Buffer.from(src), 'work/calc.py')
  await sandbox.fs.uploadFile(Buffer.from(test), 'work/test_calc.py')

  // 3. テストを実行して結果を取る(R-3)
  await sandbox.process.executeCommand('pip install -q pytest')
  const r = await sandbox.process.executeCommand('python3 -m pytest -q', 'work')
  console.log('exit code:', r.exitCode)
  console.log(r.result)
} finally {
  await daytona.delete(sandbox)
}
