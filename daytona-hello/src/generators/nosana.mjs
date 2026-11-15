// Nosana の OpenAI 互換 Chat Completions API でテストを生成・修正する。
// DSH を使わず直接つなぐ経路。DSH 接続が決まるまでの実接続確認にも使う。
import { config, redact, nosanaMissing } from '../config.mjs'
import { buildMessages, extractSingleCodeBlock } from './prompt.mjs'

export function createNosanaGenerator() {
  const { baseURL, apiKey, model } = config.nosana
  const missing = nosanaMissing()
  if (missing.length) throw new Error(`nosana.env に ${missing.join(', ')} を設定してください`)

  async function generate(req) {
    const timeout = AbortSignal.timeout(config.modelTimeoutSec * 1000)
    const signal = req.signal ? AbortSignal.any([req.signal, timeout]) : timeout
    let res, body
    try {
      res = await fetch(`${baseURL}/chat/completions`, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          ...(apiKey ? { authorization: `Bearer ${apiKey}` } : {}),
        },
        body: JSON.stringify({ model, messages: buildMessages(req), temperature: 0.2 }),
        signal,
      })
      body = await res.text()
    } catch (e) {
      if (req.signal?.aborted) throw e // 中止はループ側で扱う
      if (timeout.aborted) {
        return { ok: false, kind: 'timeout', message: `モデルが ${config.modelTimeoutSec} 秒以内に応答しなかった` }
      }
      return { ok: false, kind: 'api_error', message: redact(`接続エラー: ${e?.cause?.message ?? e?.message ?? e}`) }
    }

    if (!res.ok) {
      return { ok: false, kind: 'api_error', message: redact(`HTTP ${res.status}: ${body.slice(0, 500)}`) }
    }
    let content
    try {
      content = JSON.parse(body).choices?.[0]?.message?.content ?? ''
    } catch {
      return { ok: false, kind: 'api_error', message: redact(`JSON ではない応答: ${body.slice(0, 300)}`) }
    }
    if (!content.trim()) return { ok: false, kind: 'empty_response', message: 'モデルの応答が空だった' }
    return extractSingleCodeBlock(content)
  }

  return { name: 'nosana', generate }
}
