// 実行の受付・状態保持・通知・中止。状態はメモリ上だけに持つ(サーバー再起動で消える)。
import { randomUUID } from 'node:crypto'
import { config, availability } from './config.mjs'
import { executeRun } from './loop.mjs'
import { createMockGenerator, MOCK_SCENARIOS } from './generators/mock.mjs'
import { createNosanaGenerator } from './generators/nosana.mjs'
import { executeDshRun } from './backends/dsh-daytona.mjs'
import { openMockRunner } from './runners/mock.mjs'
import { openDaytonaRunner } from './runners/daytona.mjs'

const KEEP_RUNS = 50
const runs = new Map()        // id -> run
const controllers = new Map() // id -> AbortController(実行中のみ)
const listeners = new Map()   // id -> Set<fn>
const tasks = new Set()       // 実行中の Promise(終了時に待つ)

export class InputError extends Error {}

function validate(input) {
  const filename = String(input.filename ?? '').trim()
  const code = String(input.code ?? '')
  const instructions = String(input.instructions ?? '').slice(0, 2000)
  const generator = String(input.generator ?? 'mock')
  const runner = String(input.runner ?? 'mock')
  const scenario = String(input.scenario ?? 'fix')

  if (!/^[A-Za-z_][A-Za-z0-9_]*\.py$/.test(filename) || filename.startsWith('test_')) {
    throw new InputError('ファイル名は calc.py のような Python モジュール名にしてください(test_ で始めない)')
  }
  if (!code.trim()) throw new InputError('対象コードが空です')
  if (Buffer.byteLength(code) > config.maxCodeBytes) throw new InputError(`対象コードは ${config.maxCodeBytes} バイト以内にしてください`)

  const avail = availability()
  if (!avail.generators[generator]) throw new InputError(`不明な生成器: ${generator}`)
  if (!avail.runners[runner]) throw new InputError(`不明な実行器: ${runner}`)
  if (!avail.generators[generator].ready) throw new InputError(`生成器 ${generator} は未設定: ${avail.generators[generator].missing.join(', ')}`)
  if (!avail.runners[runner].ready) throw new InputError(`実行器 ${runner} は未設定: ${avail.runners[runner].missing.join(', ')}`)
  if (generator === 'dsh' && runner !== 'daytona') throw new InputError('DSH は Daytona 上で動かすため、実行環境は Daytona を選んでください')
  if (generator === 'mock' && !MOCK_SCENARIOS[scenario]) throw new InputError(`不明なモックシナリオ: ${scenario}`)
  if (generator === 'mock' && runner !== 'mock' && scenario === 'timeout') {
    throw new InputError('timeout シナリオはモック実行器でのみ使えます')
  }
  return { filename, code, instructions, generator, runner, scenario: generator === 'mock' ? scenario : null }
}

function makeGenerator({ generator, scenario }) {
  if (generator === 'nosana') return createNosanaGenerator()
  if (generator === 'dsh') return null // ループごと DSH(orchestrator_a/run.py)に任せる
  return createMockGenerator({ scenario })
}

export function startRun(rawInput) {
  const input = validate(rawInput)
  if (controllers.size >= config.maxConcurrentRuns) {
    throw new InputError(`同時に実行できるのは ${config.maxConcurrentRuns} 件までです。終わるまで待ってください`)
  }
  const generator = makeGenerator(input)
  const openRunner = input.runner === 'daytona' ? openDaytonaRunner : openMockRunner

  const run = {
    id: randomUUID(),
    createdAt: new Date().toISOString(),
    finishedAt: null,
    input,
    status: 'queued',
    phase: null,
    attempt: 0,
    maxAttempts: config.maxAttempts,
    deadline: new Date(Date.now() + config.runTimeoutSec * 1000).toISOString(),
    attempts: [],
    events: [],
    finalTest: null,
    reason: null,
    sandbox: null,
  }
  runs.set(run.id, run)
  pruneOld()

  const controller = new AbortController()
  controllers.set(run.id, controller)
  const timer = setTimeout(() => controller.abort('timeout'), config.runTimeoutSec * 1000)
  const update = () => notify(run.id)

  const task = (input.generator === 'dsh'
    ? executeDshRun(run, { signal: controller.signal, update })
    : executeRun(run, { generator, openRunner, signal: controller.signal, update }))
    .catch(e => { run.status = 'error'; run.reason = `内部エラー: ${e?.message ?? e}` })
    .finally(() => {
      clearTimeout(timer)
      controllers.delete(run.id)
      tasks.delete(task)
      notify(run.id)
    })
  tasks.add(task)
  return run
}

export function cancelRun(id) {
  const c = controllers.get(id)
  if (!c) return false
  c.abort('cancel')
  return true
}

export const getRun = id => runs.get(id)

export const listRuns = () =>
  [...runs.values()].reverse().map(r => ({
    id: r.id, createdAt: r.createdAt, status: r.status, filename: r.input.filename,
    generator: r.input.generator, runner: r.input.runner, attempt: r.attempt,
  }))

export function subscribe(id, fn) {
  if (!listeners.has(id)) listeners.set(id, new Set())
  listeners.get(id).add(fn)
  return () => listeners.get(id)?.delete(fn)
}

function notify(id) {
  const run = runs.get(id)
  for (const fn of listeners.get(id) ?? []) fn(run)
}

function pruneOld() {
  for (const id of runs.keys()) {
    if (runs.size <= KEEP_RUNS) break
    if (!controllers.has(id)) { runs.delete(id); listeners.delete(id) }
  }
}

// サーバー停止時: 実行中のものを中止し、サンドボックスの削除が終わるまで待つ
export async function shutdown() {
  for (const c of controllers.values()) c.abort('cancel')
  await Promise.allSettled([...tasks])
}
