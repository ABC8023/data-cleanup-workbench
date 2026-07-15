import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { expect, test } from '@playwright/test'

const FIXTURE = join(tmpdir(), 'workbench-e2e-fixture.csv')
const FIXTURE_BYTES = [
  'customer_id,name,amount,signup_date',
  'c1, Ada ,RM 1200,2026-01-02',
  'c2,lin,x,3/4/2026',
  'c3,N/A,10,2026-05-06',
  'c1, Ada ,RM 1200,2026-01-02',
  '',
].join('\n')

function sha256(path: string): string {
  return createHash('sha256').update(readFileSync(path)).digest('hex')
}

test.beforeAll(() => {
  writeFileSync(FIXTURE, FIXTURE_BYTES, 'utf-8')
})

test('completes local cleanup without changing the source', async ({ page }) => {
  const before = sha256(FIXTURE)

  await page.goto(process.env.WORKBENCH_URL!)
  await page.getByLabel('Choose dataset').setInputFiles(FIXTURE)
  await page.getByRole('button', { name: 'Profile dataset' }).click()
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible({
    timeout: 30_000,
  })

  await page.getByRole('button', { name: /review mixed date/i }).click()
  await expect(page.getByRole('table', { name: 'After' })).toBeVisible()
  await page.getByLabel(/i reviewed the before and after/i).check()
  await page.getByRole('button', { name: 'Approve transformation' }).click()

  await page.getByRole('button', { name: 'Execute recipe' }).click()
  const download = page.getByRole('button', { name: /download quality report/i })
  await expect(download).toBeEnabled({ timeout: 60_000 })

  expect(sha256(FIXTURE)).toBe(before)
})
