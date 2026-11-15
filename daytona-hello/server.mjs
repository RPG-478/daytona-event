// Web UI とオーケストレーター API。依存なしの node:http で動かす。
//   node --env-file-if-exists=.env server.mjs
import http from 'node:http'
import { readFile } from 'node:fs/promises'
import { config, availability } from './src/config.mjs'
import { MOCK_SCENARIOS } from './src/generators/mock.mjs'
import { startRun, cancelRun, getRun, listRuns, subscribe, shutdown, InputError } from './src/runs.mjs'

const json = (res, status, body) => {
  res.writeHead(status, { 'content-type': 'application/json; charset=utf-8' })
  res.end(JSON.stringify(body))
}

async function readJson(req, limit = config.maxCodeBytes * 2 + 10_000) {
  let size = 0
  const chunks = []
  for await (const c of req) {
    size += c.length
    if (size > limit) throw new InputError('リクエストが大きすぎます')
    chunks.push(c)
  }
  try { return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}') }
  catch { throw new InputError('JSON が不正です') }
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost')
  const parts = url.pathname.split('/').filter(Boolean)
  try {
    if (req.method === 'GET' && (url.pathname === '/' || url.pathname === '/index.html')) {
      res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' })
      return res.end(await readFile(new URL('./public/index.html', import.meta.url)))
    }
    if (req.method === 'GET' && url.pathname === '/api/config') {
      return json(res, 200, { ...availability(), mockScenarios: MOCK_SCENARIOS })
    }
    if (parts[0] === 'api' && parts[1] === 'runs') {
      if (req.method === 'GET' && parts.length === 2) return json(res, 200, listRuns())
      if (req.method === 'POST' && parts.length === 2) {
        const run = startRun(await readJson(req))
        return json(res, 201, run)
      }
      const run = getRun(parts[2])
      if (!run) return json(res, 404, { error: '見つかりません' })
      if (req.method === 'GET' && parts.length === 3) return json(res, 200, run)
      if (req.method === 'POST' && parts[3] === 'cancel') return json(res, 200, { cancelled: cancelRun(run.id) })
      if (req.method === 'GET' && parts[3] === 'events') {
        // Server-Sent Events: 変化があるたびに run 全体を送る
        res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache', connection: 'keep-alive' })
        const send = r => res.write(`data: ${JSON.stringify(r)}\n\n`)
        send(run)
        const unsubscribe = subscribe(run.id, send)
        const ping = setInterval(() => res.write(': ping\n\n'), 15_000)
        req.on('close', () => { unsubscribe(); clearInterval(ping) })
        return
      }
    }
    json(res, 404, { error: 'not found' })
  } catch (e) {
    if (e instanceof InputError) return json(res, 400, { error: e.message })
    console.error(e)
    json(res, 500, { error: '内部エラー' })
  }
})

server.listen(config.port, '127.0.0.1', () => {
  const a = availability()
  console.log(`Web UI: http://127.0.0.1:${config.port}`)
  for (const [kind, items] of Object.entries({ 生成器: a.generators, 実行器: a.runners })) {
    for (const [name, v] of Object.entries(items)) {
      console.log(`  ${kind} ${name.padEnd(7)} ${v.ready ? 'OK' : `未設定 (${v.missing.join(', ')})`}`)
    }
  }
})

let stopping = false
for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, async () => {
    if (stopping) process.exit(1)
    stopping = true
    console.log('\n停止中: 実行中の処理を中止し、サンドボックスを削除しています…(もう一度押すと強制終了)')
    server.close()
    server.closeAllConnections()
    await shutdown()
    process.exit(0)
  })
}
