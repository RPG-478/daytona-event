// Daytona 担当の sandbox.mjs(1件につきサンドボックス1つ、試行ごとに使い回す)をそのまま使う。
// DAYTONA_API_KEY はオーケストレーター側だけに置き、サンドボックス内へは渡さない。
export async function openDaytonaRunner() {
  const { openRunner } = await import('../../sandbox.mjs')
  const r = await openRunner()
  return { name: 'daytona', run: r.run, close: r.close, info: { id: r.id } }
}
