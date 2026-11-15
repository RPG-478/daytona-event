import { Daytona } from '@daytona/sdk'

const daytona = new Daytona({ apiKey: process.env.DAYTONA_API_KEY })

// 1タスクにつきサンドボックスを1つ作り、試行ごとに使い回す
export async function openRunner() {
  const sandbox = await daytona.create({ autoStopInterval: 15 })

  const setup = await sandbox.process.executeCommand(
    'mkdir -p work && python3 -m pip install -q pytest'
  )
  if (setup.exitCode !== 0) {
    await daytona.delete(sandbox)
    throw new Error(`setup failed: ${setup.result}`)
  }

  async function run(files, command, timeoutSec = 60) {
    for (const f of files) {
      await sandbox.fs.uploadFile(Buffer.from(f.content), `work/${f.path}`)
    }
    const env = { PYTEST_DISABLE_PLUGIN_AUTOLOAD: '1' }
    try {
      const r = await sandbox.process.executeCommand(command, 'work', env, timeoutSec)
      return { exitCode: r.exitCode, stdout: r.result, stderr: '', timedOut: false }
    } catch (e) {
      const timedOut = /timeout/i.test(String(e?.message))
      return { exitCode: -1, stdout: '', stderr: String(e?.message ?? e), timedOut }
    }
  }

  async function close() {
    await daytona.delete(sandbox)
  }

  return { run, close, id: sandbox.id }
}
