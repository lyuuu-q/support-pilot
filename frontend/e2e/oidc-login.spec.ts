import { expect, test } from '@playwright/test'

test('signs in through the local enterprise identity provider', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: '使用企业账号登录' }).click()

  await expect(page).toHaveURL(/127\.0\.0\.1:18002\/authorize/)
  await page.getByLabel('邮箱').fill('alpha.admin@example.com')
  await page.getByLabel('密码').fill('SupportPilotDemo!2026')
  await page.getByRole('button', { name: '登录' }).click()

  await expect(page).toHaveURL('http://127.0.0.1:15174/')
  await expect(page.getByText('Alpha Admin（合成用户）')).toBeVisible({ timeout: 60_000 })

  // 令牌只存在于 HttpOnly Cookie 中，页面脚本接触不到任何令牌。
  const storageKeys = await page.evaluate(() => Object.keys(window.localStorage))
  expect(storageKeys).toHaveLength(0)
  const cookies = await page.context().cookies()
  const access = cookies.find((cookie) => cookie.name === 'support_pilot_access')
  const csrf = cookies.find((cookie) => cookie.name === 'support_pilot_csrf')
  expect(access?.httpOnly).toBe(true)
  expect(csrf?.httpOnly).toBe(false)
})
