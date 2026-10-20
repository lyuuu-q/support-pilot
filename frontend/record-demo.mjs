// 自动录制 SupportPilot 控制台演示视频（1280x720 webm）。
// 运行前提：后端已在 http://127.0.0.1:8000 运行，前端已在 http://127.0.0.1:5173 运行，
// 且已完成 alembic upgrade + seed + ingest（确定性 Provider）。
// 用法（在 frontend/ 目录下）：
//   node record-demo.mjs
import { chromium } from 'playwright'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const BASE_URL = process.env.RECORD_BASE_URL ?? 'http://127.0.0.1:5173'
const PASSWORD = 'SupportPilotDemo!2026'
const CUSTOMER_EMAIL = 'alpha.admin@example.com'
const SUPPORT_EMAIL = 'support.agent@example.com'
const TICKET_SUMMARY = '批量导出功能报错，请协助排查并转人工处理'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const outDir = path.resolve(scriptDir, '..', 'recordings')
fs.mkdirSync(outDir, { recursive: true })

const browser = await chromium.launch()
const context = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  recordVideo: { dir: outDir, size: { width: 1280, height: 720 } },
})
const page = await context.newPage()
const pause = (ms) => page.waitForTimeout(ms)

async function login(email) {
  await page.getByLabel('邮箱').fill(email)
  await pause(500)
  await page.getByLabel('密码').fill(PASSWORD)
  await pause(500)
  await page.getByRole('button', { name: '进入工作台' }).click()
}

try {
  // 1. 登录页
  await page.goto(BASE_URL)
  await page.waitForLoadState('networkidle')
  await pause(1500)

  // 2. 客户登录
  await login(CUSTOMER_EMAIL)
  await page.getByText('Alpha Admin（合成用户）').waitFor({ timeout: 30000 })
  await pause(1500)

  // 3. 默认问题（预填 429/Retry-After）→ 带引用的知识回答
  await page.getByRole('button', { name: '开始诊断' }).click()
  await page.getByRole('heading', { name: '引用证据' }).waitFor({ timeout: 60000 })
  await page.getByRole('heading', { name: '逐条主张' }).waitFor()
  await page.getByRole('list', { name: 'Agent 执行轨迹' }).waitFor()
  await pause(2500)

  // 4. 二次提问 → 触发工单草稿
  await page.locator('textarea').first().fill(`${TICKET_SUMMARY}。`)
  await page.getByRole('button', { name: '开始诊断' }).click()
  await page.getByRole('button', { name: '确认创建工单' }).waitFor({ timeout: 60000 })
  await pause(1500)

  // 5. 确认创建工单
  await page.getByRole('button', { name: '确认创建工单' }).click()
  await page.getByText('已按确认创建工单。').waitFor({ timeout: 60000 })
  await pause(2000)

  // 6. 退出，切到支持人员账号
  await page.getByRole('button', { name: '退出' }).click()
  await page.getByLabel('邮箱').waitFor({ timeout: 15000 })
  await login(SUPPORT_EMAIL)
  await page.getByText('Support Agent（合成用户）').waitFor({ timeout: 30000 })
  await pause(1500)

  // 7. 工单队列里定位并打开刚创建的工单
  const ticketRow = page.getByRole('button').filter({ hasText: TICKET_SUMMARY }).first()
  await ticketRow.waitFor({ timeout: 60000 })
  await pause(1000)
  await ticketRow.click()
  await page.getByRole('heading', { name: new RegExp(TICKET_SUMMARY) }).waitFor()
  await pause(1500)

  // 8. 认领并分诊 → 转为 in_progress
  await page.getByRole('button', { name: '认领并分诊' }).click()
  await page.getByText('open → triaged').waitFor({ timeout: 30000 })
  await pause(1200)
  await page.getByRole('button', { name: '转为 in_progress' }).click()
  await page.getByText('triaged → in_progress').waitFor({ timeout: 30000 })
  await page.locator('.status-pill').waitFor()
  await pause(2500)

  console.log('RECORD_OK: 演示链路录制完成')
} finally {
  await context.close()
  await browser.close()

  // Playwright 生成的视频名是随机 uuid，重命名为固定名。
  const files = fs.readdirSync(outDir).filter((f) => f.endsWith('.webm'))
  const newest = files
    .map((f) => ({ f, t: fs.statSync(path.join(outDir, f)).mtimeMs }))
    .sort((a, b) => b.t - a.t)[0]
  if (newest) {
    const dest = path.join(outDir, 'support-pilot-demo.webm')
    if (path.join(outDir, newest.f) !== dest) {
      fs.renameSync(path.join(outDir, newest.f), dest)
    }
    console.log(`VIDEO: ${dest}`)
  }
}
