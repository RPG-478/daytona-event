// Nosana 接続確認: モデル一覧 → チャット応答 → ツール呼び出し の順に試す。
//   npm run check:nosana
// API キーの値は表示しない。
import { config, nosanaMissing, redact } from '../src/config.mjs'

const { baseURL, apiKey, model } = config.nosana
const headers = { 'content-type': 'application/json', ...(apiKey ? { authorization: `Bearer ${apiKey}` } : {}) }
const ok = m => console.log(`  OK  ${m}`)
const ng = m => { console.log(`  NG  ${m}`); process.exitCode = 1 }

async function call(path, body) {
  const res = await fetch(baseURL + path, {
    method: body ? 'POST' : 'GET', headers, body: body && JSON.stringify(body),
    signal: AbortSignal.timeout(config.modelTimeoutSec * 1000),
  })
  const text = await res.text()
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${redact(text.slice(0, 300))}`)
  return JSON.parse(text)
}

console.log(`接続先: ${baseURL}`)
console.log(`API キー: ${apiKey ? '設定あり' : '未設定'} / モデル: ${model || '未設定'}\n`)
if (!apiKey && nosanaMissing().includes('NOSANA_API_KEY')) {
  ng('nosana.env の NOSANA_API_KEY を埋めてください')
  process.exit()
}

console.log('1. モデル一覧 (GET /models)')
let ids = []
try {
  ids = (await call('/models')).data?.map(m => m.id) ?? []
  ok(`${ids.length} 件`)
  for (const id of ids) console.log(`      ${id === model ? '*' : '-'} ${id}`)
  if (model && ids.length && !ids.includes(model)) ng(`NOSANA_MODEL「${model}」は一覧にない。上の名前をそのままコピーしてください`)
} catch (e) { ng(`取得失敗: ${e.message}`) }

if (!model) {
  ng('nosana.env の NOSANA_MODEL に上の一覧から1つ書いて、もう一度実行してください')
  process.exit()
}

console.log('\n2. チャット応答 (POST /chat/completions)')
try {
  const t = Date.now()
  const r = await call('/chat/completions', {
    model, max_tokens: 20, messages: [{ role: 'user', content: 'Reply with exactly: pong' }],
  })
  const content = r.choices?.[0]?.message?.content ?? ''
  content.trim() ? ok(`${Date.now() - t}ms 「${content.trim().slice(0, 60)}」`) : ng('応答が空')
} catch (e) { ng(e.message) }

console.log('\n3. ツール呼び出し (tools / tool_calls) — DSH で必要')
try {
  const r = await call('/chat/completions', {
    model, max_tokens: 200,
    messages: [{ role: 'user', content: 'Run the command "pytest -q" using the run_command tool.' }],
    tools: [{
      type: 'function',
      function: {
        name: 'run_command', description: 'Run a shell command',
        parameters: { type: 'object', properties: { command: { type: 'string' } }, required: ['command'] },
      },
    }],
    tool_choice: 'auto',
  })
  const tc = r.choices?.[0]?.message?.tool_calls?.[0]
  if (tc) ok(`${tc.function?.name}(${tc.function?.arguments})`)
  else ng(`tool_calls が返らなかった(本文: ${String(r.choices?.[0]?.message?.content ?? '').slice(0, 120)})。テスト生成の直接接続は動くが、DSH のツール実行には使えない可能性あり`)
} catch (e) { ng(`ツール付きリクエストが拒否された: ${e.message}`) }

console.log(process.exitCode ? '\n一部 NG。上のメッセージを確認してください' : '\nすべて OK。UI の「テスト生成」で Nosana(直接)を選べます')
