// DSH 経路: Daytona サンドボックス内で担当 A の orchestrator_a/run.py を動かす。
// 生成・実行・修正のループは run.py(DSH)が担い、こちらはサンドボックスの用意・
// 起動・結果の取り込み・後始末だけを行う。
//
// run.py の受け渡し(orchestrator_a/README.md):
//   python3 run.py --source solution.py --attempts N --timeout SEC
//   → 標準出力に JSON 1つ { status: succeeded|failed|timed_out, attempts, test_code, logs[], message, error_code?, duration_seconds }
//
// 注意: DSH が Nosana に接続するため NOSANA_* はサンドボックス内に渡す(task-dsh.md の方針どおり、
// Nosana 用の認証情報だけを渡す)。DAYTONA_API_KEY は渡さない。
import { readFile } from 'node:fs/promises'
import { Daytona } from '@daytona/sdk'
import { config, redact } from '../config.mjs'

export const DSH_VERSION = process.env.DSH_VERSION || '0.2.2-rc.1'
const RUN_PY = new URL('../../../orchestrator_a/run.py', import.meta.url)
const SETUP_TIMEOUT_SEC = 300
const MARGIN_SEC = 30 // run.py の --timeout に足す、終了処理と結果回収の余裕

function raceAbort(promise, signal) {
  if (signal.aborted) return Promise.reject(signal.reason)
  return new Promise((resolve, reject) => {
    const onAbort = () => reject(signal.reason)
    signal.addEventListener('abort', onAbort, { once: true })
    promise.then(
      v => { signal.removeEventListener('abort', onAbort); resolve(v) },
      e => { signal.removeEventListener('abort', onAbort); reject(e) },
    )
  })
}

// run.py の logs を試行ごとにまとめる("Attempt k/N: ..." が区切り)
export function attemptsFromLogs(logs, finalStatus, testCode) {
  const attempts = []
  for (const line of logs) {
    const m = /^Attempt (\d+)\/\d+/.exec(line)
    if (m) { attempts.push({ n: Number(m[1]), status: 'generating', test: null, lines: [line], summary: '' }); continue }
    const cur = attempts.at(-1)
    if (!cur) continue
    cur.lines.push(line)
    const py = /^pytest exited (-?\d+)/.exec(line)
    if (py) {
      const code = Number(py[1])
      cur.exitCode = code
      cur.status = code === 0 ? 'pass' : code === 5 ? 'no_tests' : code === 1 ? 'test_fail' : 'compile_error'
      cur.summary = line.trim().split('\n').at(-1)
    } else if (/did not create a regular test_solution\.py/.test(line)) {
      cur.status = 'bad_response'
      cur.summary = 'テストファイルが作られなかった'
    } else if (/No test passed/.test(line)) {
      cur.status = 'no_tests'
      cur.summary = '成功したテストが0件(全件スキップ等)'
    }
  }
  const last = attempts.at(-1)
  if (last) {
    if (last.status === 'generating') last.status = finalStatus === 'timed_out' ? 'timeout' : 'api_error'
    if (finalStatus === 'succeeded') last.test = testCode
  }
  return attempts.map(({ lines, ...a }) => ({ ...a, log: redact(lines.join('\n')) }))
}

export async function executeDshRun(run, { signal, update }) {
  const log = msg => { run.events.push({ at: new Date().toISOString(), msg: redact(msg) }); update() }
  const setPhase = phase => { run.phase = phase; update() }
  const finish = (status, reason) => { run.status = status; run.reason = redact(reason); log(`終了: ${status} — ${run.reason}`) }

  const daytona = new Daytona({ apiKey: config.daytonaApiKey })
  let sandbox = null
  run.status = 'running'
  try {
    setPhase('preparing')
    log('Daytona サンドボックスを作成中')
    const creating = daytona.create({ autoStopInterval: 15 })
    creating.then(s => { if (signal.aborted) daytona.delete(s).catch(() => {}) }, () => {})
    sandbox = await raceAbort(creating, signal)
    run.sandbox = { id: sandbox.id, deleted: false }
    log(`サンドボックス ${sandbox.id} を作成`)

    log(`pytest と DSH ${DSH_VERSION} をインストール中`)
    const setup = await raceAbort(sandbox.process.executeCommand(
      `mkdir -p dshjob && python3 -m pip install -q pytest && node -v && npm install --global --silent @deepseek-ai/dsh@${DSH_VERSION} && dsh --version`,
      undefined, undefined, SETUP_TIMEOUT_SEC,
    ), signal)
    if (setup.exitCode !== 0) {
      return finish('error', `サンドボックスの準備に失敗 (exit ${setup.exitCode}): ${String(setup.result).trim().split('\n').slice(-5).join(' / ')}`)
    }
    log(`準備完了: ${String(setup.result).trim().split('\n').slice(-2).join(' / ')}`)

    await sandbox.fs.uploadFile(await readFile(RUN_PY), 'dshjob/run.py')
    await sandbox.fs.uploadFile(Buffer.from(run.input.code), 'dshjob/solution.py')

    // 全体の残り時間から run.py の --timeout を決める(Daytona 側はそれ+余裕)
    const remaining = Math.floor((Date.parse(run.deadline) - Date.now()) / 1000) - MARGIN_SEC - 15
    const innerTimeout = Math.max(30, Math.min(1800, remaining))
    const attempts = Math.min(5, run.maxAttempts)
    run.maxAttempts = attempts
    setPhase('executing')
    log(`DSH を実行中(試行上限 ${attempts} 回 / ${innerTimeout} 秒)。結果は終了時にまとめて返る`)

    const env = {
      NOSANA_BASE_URL: config.nosana.baseURL,
      NOSANA_MODEL: config.nosana.model,
      NOSANA_API_KEY: config.nosana.apiKey,
    }
    let r
    try {
      r = await raceAbort(sandbox.process.executeCommand(
        `python3 run.py --source solution.py --attempts ${attempts} --timeout ${innerTimeout}`,
        'dshjob', env, innerTimeout + MARGIN_SEC,
      ), signal)
    } catch (e) {
      if (signal.aborted) throw e
      if (/timeout/i.test(String(e?.message))) return finish('timeout', 'Daytona のコマンド実行がタイムアウトした')
      throw e
    }

    const line = String(r.result).trim().split('\n').reverse().find(l => l.trim().startsWith('{'))
    let out
    try { out = JSON.parse(line) } catch {
      return finish('error', `run.py の出力を JSON として読めなかった (exit ${r.exitCode}): ${String(r.result).slice(-300)}`)
    }

    run.attempts = attemptsFromLogs(out.logs ?? [], out.status, out.test_code ?? '')
    run.attempt = out.attempts ?? run.attempts.length
    if (out.test_code) run.finalTest = out.status === 'succeeded' ? out.test_code : null
    if (out.test_code && out.status !== 'succeeded' && run.attempts.at(-1)) run.attempts.at(-1).test = out.test_code
    update()

    const msg = `${out.message ?? ''}${out.error_code ? ` [${out.error_code}]` : ''} (DSH ${out.duration_seconds ?? '?'} 秒)`
    if (out.status === 'succeeded') return finish('passed', msg)
    if (out.status === 'timed_out') return finish('timeout', msg)
    if (out.error_code || out.attempts === 0) return finish('error', msg)
    return finish('failed', msg)
  } catch (e) {
    if (signal.aborted && signal.reason === 'timeout') return finish('timeout', `全体の上限 ${config.runTimeoutSec} 秒を超えた`)
    if (signal.aborted) return finish('cancelled', 'ユーザーが中止した')
    return finish('error', `内部エラー: ${e?.message ?? e}`)
  } finally {
    if (sandbox) {
      setPhase('cleanup')
      try {
        await daytona.delete(sandbox)
        run.sandbox.deleted = true
        log('サンドボックスを削除した')
      } catch (e) {
        run.sandbox.deleteError = redact(e?.message ?? String(e))
        log(`サンドボックスの削除に失敗: ${run.sandbox.deleteError}(手動で削除してください)`)
      }
    }
    run.phase = null
    run.finishedAt = new Date().toISOString()
    update()
  }
}
