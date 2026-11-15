// 生成 → Daytona で実行 → 判定 → 失敗ログで修正 を上限付きで回す。
// 状態は run オブジェクトに書き込み、update() で UI へ通知する。
import { config, redact } from './config.mjs'
import { judge, formatLog } from '../judge.mjs'

// 中止されたら即座に reject する。元の処理は止まらないので、後始末は呼び出し側で行う
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

export async function executeRun(run, { generator, openRunner, signal, update }) {
  const { filename, code, instructions } = run.input
  const testFilename = `test_${filename}`
  const log = msg => { run.events.push({ at: new Date().toISOString(), msg: redact(msg) }); update() }
  const setPhase = phase => { run.phase = phase; update() }
  const finish = (status, reason) => { run.status = status; run.reason = redact(reason); log(`終了: ${status} — ${run.reason}`) }

  let runner = null
  run.status = 'running'
  try {
    setPhase('preparing')
    log(`実行環境を準備中 (${run.input.runner})`)
    const opening = openRunner()
    // 準備中に中止されたら、作成されたサンドボックスを後から必ず削除する
    opening.then(r => { if (signal.aborted) r.close().catch(() => {}) }, () => {})
    runner = await raceAbort(opening, signal)
    run.sandbox = { id: runner.info?.id ?? null, deleted: false }
    log(`実行環境の準備完了${run.sandbox.id ? ` (sandbox ${run.sandbox.id})` : ''}`)

    let previous = null
    for (let n = 1; n <= run.maxAttempts; n++) {
      const attempt = { n, status: 'generating', test: null, log: '', summary: '', startedAt: new Date().toISOString() }
      run.attempts.push(attempt)
      run.attempt = n

      setPhase('generating')
      log(`試行 ${n}/${run.maxAttempts}: テストを${previous ? '修正' : '生成'}中 (${run.input.generator})`)
      const g = await raceAbort(
        generator.generate({ code, filename, testFilename, instructions, attempt: n, previous, signal }),
        signal,
      )
      if (!g.ok) {
        attempt.status = g.kind
        attempt.summary = redact(g.message)
        attempt.log = redact(g.raw ?? '')
        attempt.finishedAt = new Date().toISOString()
        if (g.kind === 'bad_response') {
          // 形式の問題はモデルに伝えて再試行する
          log(`試行 ${n}: 応答からテストを取り出せなかった — ${g.message}`)
          previous = { test: null, status: 'コードブロックの形式不正', log: `${g.message}。\`\`\`python のコードブロック1つだけで出力してください。` }
          continue
        }
        return finish('error', `モデル呼び出しに失敗 (${g.kind}): ${g.message}`)
      }
      attempt.test = g.test

      setPhase('executing')
      attempt.status = 'executing'
      log(`試行 ${n}: pytest を実行中`)
      const files = [{ path: filename, content: code }, { path: testFilename, content: g.test }]
      const r = await raceAbort(runner.run(files, `python3 -m pytest -q ${testFilename}`, config.testTimeoutSec), signal)
      const j = judge(r)
      attempt.status = j.status
      attempt.summary = redact(j.summary)
      attempt.exitCode = r.exitCode
      attempt.log = redact(formatLog(r, 8000))
      attempt.finishedAt = new Date().toISOString()
      log(`試行 ${n}: ${j.status} — ${attempt.summary}`)

      if (j.status === 'pass') {
        run.finalTest = g.test
        return finish('passed', `試行 ${n} 回目でテストが通った`)
      }
      if (j.status === 'timeout') {
        return finish('timeout', `テスト実行が ${config.testTimeoutSec} 秒を超えた`)
      }
      previous = { test: g.test, status: j.status, log: redact(formatLog(r)) }
    }
    return finish('failed', `試行上限 ${run.maxAttempts} 回に達した`)
  } catch (e) {
    const cur = run.attempts.at(-1)
    if (cur && !cur.finishedAt) { cur.status = 'aborted'; cur.finishedAt = new Date().toISOString() }
    if (signal.aborted && signal.reason === 'timeout') return finish('timeout', `全体の上限 ${config.runTimeoutSec} 秒を超えた`)
    if (signal.aborted) return finish('cancelled', 'ユーザーが中止した')
    return finish('error', `内部エラー: ${e?.message ?? e}`)
  } finally {
    if (runner) {
      setPhase('cleanup')
      try {
        await runner.close()
        run.sandbox.deleted = true
        log('実行環境を削除した')
      } catch (e) {
        run.sandbox.deleteError = redact(e?.message ?? String(e))
        log(`実行環境の削除に失敗: ${run.sandbox.deleteError}(手動で削除してください)`)
      }
    }
    run.phase = null
    run.finishedAt = new Date().toISOString()
    update()
  }
}
