import { Daytona } from '@daytona/sdk'

const daytona = new Daytona({ apiKey: process.env.DAYTONA_API_KEY })
const sandbox = await daytona.create()

try {
  const response = await sandbox.process.codeRun('print("Hello World")')
  console.log(response.result)
} finally {
  await daytona.delete(sandbox) // 消し忘れによる課金を防ぐ
}
