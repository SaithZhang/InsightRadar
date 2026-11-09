import { test, expect } from '@playwright/test'
import type { Position, PositionItem, Report, Run } from '../../src/types'

const today = '2026-11-09'
const now = '2026-11-09T00:00:00Z'
const code = '601799.SH'
const runId = '682e5d56-6650-434d-bf36-5a722b09843a'

function position(canonicalCode: string, quantity: number, version = 1): Position {
  return { canonicalCode, quantity, version, unitCost: null, onMa55Trigger: null, source: 'MANUAL', confirmedAt: now, updatedAt: now }
}

function item(record: Position, name: string): PositionItem {
  return { position: record, name, confirmedToday: true, quoteDate: null, referenceClose: null,
    marketValue: record.quantity ? null : '0', unrealizedPnl: null, unrealizedPnlPercent: null }
}

test('manual positions can be saved, confirmed and cleared, then navigate without generating analysis', async ({ page }) => {
  const records = Array.from({ length: 16 }, (_, index) => item(position(String(601800 + index) + '.SH', 100), '测试标的 ' + index))
  let analyses = 0
  page.on('request', request => {
    if (request.method() === 'POST' && request.url().endsWith('/analyses')) analyses++
  })
  await page.route('**/api/v1/positions?**', route => route.fulfill({ json: { items: records } }))
  await page.route('**/api/v1/securities/resolve?**', route => route.fulfill({ json: { canonicalCode: code } }))
  await page.route('**/api/v1/positions/' + code, async route => {
    const data = route.request().postDataJSON()
    expect(route.request().method()).toBe('PUT')
    const current = records.find(row => row.position.canonicalCode === code)
    expect(data.expectedVersion).toBe(current?.position.version ?? 0)
    const updated: Position = {
      ...position(code, data.quantity, data.expectedVersion + 1), unitCost: data.unitCost, onMa55Trigger: data.onMa55Trigger,
    }
    if (current) Object.assign(current, item(updated, '测试新增标的'))
    else records.unshift(item(updated, '测试新增标的'))
    await route.fulfill({ json: updated })
  })

  await page.goto('/#/positions')
  await expect(page.getByRole('heading', { name: /持仓管理/ })).toBeVisible()
  await page.getByRole('button', { name: '新增持仓' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('证券代码').fill('601799')
  await dialog.getByLabel('持有股数').fill('900')
  await dialog.getByLabel('每股成本（选填）').fill('12.340005')
  await dialog.getByLabel('MA55 触发动作').selectOption('REVIEW_REDUCTION')
  await dialog.getByRole('button', { name: '保存持仓' }).click()
  const added = page.getByRole('row').filter({ hasText: '测试新增标的' })
  await expect(added).toContainText('900 股')
  await expect(added).toContainText('12.340005')
  await added.getByRole('button', { name: '编辑' }).click()
  await dialog.getByLabel('持有股数').fill('800')
  await dialog.getByRole('button', { name: '保存持仓' }).click()
  await expect(added).toContainText('800 股')
  await added.getByRole('button', { name: '确认未变' }).click()
  await expect(page.getByText('已确认持仓未变')).toBeVisible()
  page.once('dialog', dialog => dialog.accept())
  await added.getByRole('button', { name: '标记清仓' }).click()
  await expect(added).toContainText('已清仓')
  await page.getByLabel('显示', { exact: true }).selectOption('holding')
  await expect(added).toHaveCount(0)
  const last = page.getByRole('link', { name: '测试标的 15', exact: true })
  await last.scrollIntoViewIfNeeded()
  const initialScroll = await page.evaluate(() => window.scrollY)
  expect(initialScroll).toBeGreaterThan(0)
  await last.click()
  await expect(page.getByRole('navigation')).toContainText('个股分析')
  await expect(page.getByRole('textbox', { name: '证券代码', exact: true })).toHaveValue('601815.SH')
  await page.goBack()
  await expect(page.getByLabel('显示', { exact: true })).toHaveValue('holding')
  await expect(last).toBeInViewport()
  await expect.poll(async () => Math.abs(await page.evaluate(() => window.scrollY) - initialScroll)).toBeLessThan(48)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(analyses).toBe(0)
})

test('history preserves the submitted position and refreshed live analysis shows edits', async ({ page }) => {
  const submitted = { ...position(code, 900), unitCost: '12.340005', onMa55Trigger: 'REVIEW_REDUCTION' as const }
  const latest = position(code, 0, 2)
  const evidence = {
    state: 'PRICE_RISK_REVIEW', reason: 'test', previousDate: '2026-11-05', date: '2026-11-06',
    previousClose: '14.0000', previousMa55: '15.0000', close: '13.0000', ma55: '14.5000',
  }
  const zone = { valid: false, reason: 'NO_VALID_CANDIDATE', source: null, center: null, halfWidth: null, lower: null, upper: null }
  const report: Report = {
    runId, requestedCode: code, canonicalCode: code, identity: { name: '合成测试标的', exchange: 'SH' },
    officialIssuer: {}, createdAt: now, asOfTradeDate: '2026-11-06', knowledgeCutoff: now, status: 'PARTIAL',
    marketTiming: { phase: 'PRE_OPEN', requestedThrough: '2026-11-08', awaitingPublication: false, providerReleaseAt: '2026-11-09T18:00:00+08:00' },
    technicalStatus: 'READY', eventStatus: 'UNAVAILABLE', source: 'SYNTHETIC_TEST_ONLY', priceBasis: null,
    dataGaps: [], trade_authority: 'none', candles: [], indicators: { ma20: null, ma55: null, ma20FiveBarsAgo: null, ma55FiveBarsAgo: null, atr14: null },
    indicatorSeries: [], trend: { state: 'DOWN', reasons: [] }, support: zone, resistance: zone, buyPlan: null,
    buyPlanNotCreatedReason: null, sellReview: evidence, eventReview: { state: 'UNKNOWN', reason: '' },
    facts: [], followUps: [], documents: [], coverage: {}, semantic: {}, provenance: {}, errors: [],
    dataQuality: { barsValid: 60, targetBars: 120, reliable: true, fresh: true, lastFinalizedDate: '2026-11-06', expectedSession: '2026-11-06', gaps: [] },
    positionSnapshot: { schemaVersion: 'position-v1', capturedAt: now, canonicalCode: code, position: submitted,
      positionStatus: 'HOLDING', confirmationStatus: 'CONFIRMED', priceState: 'TRIGGERED', action: 'REVIEW_REDUCTION',
      reason: '两日收盘均低于各自 MA55，已达到你设定的评估条件。', ruleId: 'TWO_CLOSES_BELOW_MA55', ruleVersion: 'TECH-R1',
      evidence, nextCheck: { tradeDate: today, earliestAnalysisDate: '2026-11-10', message: '等待终值' } },
  }
  let envelope: Run = { runId, status: 'PARTIAL', stage: 'FINISHED', report, reportHash: 'synthetic-hash', error: null }
  let submissions = 0
  await page.route('**/api/v1/positions?**', route => route.fulfill({ json: { items: [item(latest, '合成测试标的')] } }))
  await page.route('**/api/v1/analyses/' + runId, route => route.fulfill({ json: envelope }))
  await page.route('**/api/v1/analyses/' + runId + '/plan-evaluations', route => route.fulfill({ json: { items: [] } }))
  await page.route('**/api/v1/analyses', route => {
    submissions++
    return route.fulfill({ json: { runId } })
  })
  await page.route('**/api/v1/analyses?**', route => {
    const query = new URL(route.request().url()).searchParams
    const matches = query.get('code') === code && query.get('from') === today && query.get('to') === today
    return route.fulfill({ json: { items: matches ? [{
      runId, status: 'PARTIAL', createdAt: now, canonicalCode: code, asOfTradeDate: report.asOfTradeDate,
    }] : [] } })
  })

  await page.goto('/#/history')
  await page.locator('.history-filters').getByLabel('证券代码').fill(code)
  await page.getByLabel('开始日期').fill(today)
  await page.getByLabel('结束日期').fill(today)
  await page.getByRole('button', { name: '筛选' }).click()
  await page.locator('.history-row').click()
  const summary = page.getByRole('region', { name: '持仓与下一步' })
  await expect(page.locator('.report-heading')).toContainText('盘前')
  await expect(summary).toContainText('当次动作')
  await expect(summary).toContainText('进入减仓评估')
  await expect(summary).toContainText('900 股')
  await expect(summary).toContainText('13.0000')
  await page.reload()
  await expect(summary).toContainText('进入减仓评估')
  expect(submissions).toBe(0)

  await page.goto('/#/analysis?code=' + code)
  await page.getByRole('button', { name: '开始分析' }).click()
  await expect(summary).toContainText('持仓已更新，请重新生成以查看当前动作')
  expect(submissions).toBe(1)

  const pending = structuredClone(report)
  pending.knowledgeCutoff = '2026-11-09T08:00:00Z'
  pending.marketTiming = { ...report.marketTiming!, phase: 'POST_CLOSE', awaitingPublication: true }
  pending.dataQuality = { ...report.dataQuality, fresh: false, expectedSession: today }
  pending.trend = { state: 'UNKNOWN', reasons: ['LATEST_FINAL_SESSION_UNAVAILABLE'] }
  pending.technicalStatus = 'UNKNOWN'
  pending.positionSnapshot = { ...report.positionSnapshot!, priceState: 'DATA_INSUFFICIENT',
    action: 'WAIT_FOR_DATA', reason: '今日已收盘，等待行情源发布当日终值及复权数据。' }
  envelope = { ...envelope, report: pending }
  await page.getByRole('button', { name: '开始分析' }).click()
  await expect(page.locator('.report-heading')).toContainText('盘后')
  await expect(page.getByText('当日收盘终值待发布', { exact: true })).toBeVisible()
  await expect(summary).toContainText('数据不足')
  expect(submissions).toBe(2)
})

test('Tencent confirms the close while the daily analysis is still running', async ({ page }) => {
  await page.route('**/api/v1/securities/close?code=002463', route => route.fulfill({ json: {
    canonicalCode: '002463.SZ', name: '沪电股份', tradeDate: '2026-11-09',
    close: '77.10', quotedAt: '2026-11-09T15:01:00+08:00', source: 'tencent',
  } }))
  await page.route('**/api/v1/analyses', route => route.fulfill({ json: { runId } }))
  await page.route('**/api/v1/analyses/' + runId, route => route.fulfill({ json: {
    runId, status: 'RUNNING', stage: 'MARKET', report: null, error: null,
  } }))
  await page.goto('/')
  await page.getByRole('button', { name: '开始分析' }).click()
  const preview = page.getByRole('region', { name: '腾讯盘后收盘' })
  await expect(preview).toContainText('77.10 元')
  await expect(preview).toContainText('技术指标待 BaoStock')
  await expect(page.locator('.progress-banner')).toBeVisible()
  await expect(page.locator('.price-chart')).toHaveCount(0)
})
