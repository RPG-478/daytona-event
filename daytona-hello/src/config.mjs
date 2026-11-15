// 設定はすべて環境変数から読む。APIキーの値はログ・画面・成果物に出さない。
const num = (name, def) => {
  const v = Number(process.env[name])
  return Number.isFinite(v) && v > 0 ? v : def
}

export const config = {
  port: num('PORT', 3000),
  maxAttempts: num('MAX_ATTEMPTS', 5),            // 生成→実行の試行上限
  runTimeoutSec: num('RUN_TIMEOUT_SEC', 600),     // 1件全体の上限
  testTimeoutSec: num('TEST_TIMEOUT_SEC', 60),    // pytest 1回の上限
  modelTimeoutSec: num('MODEL_TIMEOUT_SEC', 120), // モデル応答1回の上限
  maxConcurrentRuns: num('MAX_CONCURRENT_RUNS', 2),
  maxCodeBytes: num('MAX_CODE_BYTES', 50_000),
  nosana: {
    baseURL: (process.env.NOSANA_BASE_URL || 'https://inference.nosana.com/v1').replace(/\/+$/, ''),
    apiKey: process.env.NOSANA_API_KEY ?? '',
    model: process.env.NOSANA_MODEL ?? '',
  },
  daytonaApiKey: process.env.DAYTONA_API_KEY ?? '',
}

// マネージド推論(inference.nosana.com)は API キー必須。自前 vLLM ならキーなしも許す
export function nosanaMissing() {
  const { baseURL, apiKey, model } = config.nosana
  return [
    !apiKey && baseURL.includes('inference.nosana.com') && 'NOSANA_API_KEY',
    !model && 'NOSANA_MODEL',
  ].filter(Boolean)
}

// どの生成器・実行器が使えるか(設定の有無だけを返し、値は返さない)
export function availability() {
  return {
    generators: {
      mock: { ready: true },
      nosana: {
        ready: nosanaMissing().length === 0,
        missing: nosanaMissing(),
      },
      // DSH は Daytona 内で動かすので Nosana と Daytona の両方が必要
      dsh: {
        ready: nosanaMissing().length === 0 && Boolean(config.daytonaApiKey),
        missing: [...nosanaMissing(), ...(config.daytonaApiKey ? [] : ['DAYTONA_API_KEY'])],
        requiresRunner: 'daytona',
      },
    },
    runners: {
      mock: { ready: true },
      daytona: {
        ready: Boolean(config.daytonaApiKey),
        missing: config.daytonaApiKey ? [] : ['DAYTONA_API_KEY'],
      },
    },
    limits: {
      maxAttempts: config.maxAttempts,
      runTimeoutSec: config.runTimeoutSec,
      testTimeoutSec: config.testTimeoutSec,
    },
  }
}

// ログに秘密情報が紛れ込んでも画面・モデルに渡す前に伏せる
export function redact(text) {
  let out = String(text ?? '')
  for (const secret of [config.nosana.apiKey, config.daytonaApiKey]) {
    if (secret && secret.length >= 8) out = out.split(secret).join('***')
  }
  return out
}
