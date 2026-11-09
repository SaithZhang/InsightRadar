import { test,expect } from '@playwright/test'

test('empty state is honest and invalid security stays local', async ({page},info) => {
  await page.goto('/')
  await expect(page.getByRole('heading',{name:'先看证据，再做判断。'})).toBeVisible()
  let requests=0
  page.on('request',r=>{if(r.method()==='POST')requests++})
  await page.getByLabel('证券代码',{exact:true}).fill('not-stock')
  await page.getByRole('button',{name:'开始分析'}).click()
  await expect(page.getByRole('alert')).toContainText('请输入六位')
  expect(requests).toBe(0)
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  await page.screenshot({path:`../data/acceptance/empty-${info.project.name}.png`,fullPage:true})
})

test('real saved report, source details and unchanged historical snapshot', async ({page,request},info) => {
  const history=await request.get('http://127.0.0.1:18080/api/v1/analyses?code=002463')
  const list=await history.json()
  const item=list.items.find((x:{status:string})=>['COMPLETED','PARTIAL'].includes(x.status))
  test.skip(!item,'Requires an actual saved live-source report; never substitute a mock')
  const before=await (await request.get(`http://127.0.0.1:18080/api/v1/analyses/${item.runId}`)).json()
  await page.goto('/')
  await expect(page.getByLabel('模型模式')).toHaveValue('production')
  await page.getByRole('button',{name:'历史分析'}).click()
  await expect(page.getByText('直接读取已保存的结果',{exact:false})).toBeVisible()
  await page.locator('a.history-row[href*="runId=' + item.runId + '"]').click()
  await expect(page.locator('.report-heading')).toContainText('只读快照')
  if (before.report.marketTiming?.phase === 'POST_CLOSE') {
    await expect(page.locator('.report-heading')).toContainText('盘后')
    await expect(page.locator('.report-heading')).toContainText(before.report.asOfTradeDate)
  }
  await expect(page.getByRole('heading',{name:'04 / 重要事实、风险与下一次核验'})).toBeVisible()
  if(before.report.facts.length){
    await expect(page.locator('.fact')).toHaveCount(before.report.facts.length)
    await expect(page.locator('.fact').first()).toContainText(before.report.facts[0].statement)
    if(before.report.semantic.cacheHit) await expect(page.getByText('已复用模型结果',{exact:false})).toBeVisible()
  }else{
    await expect(page.locator('.empty-copy')).toContainText('暂无通过验证的语义摘要')
  }
  await page.getByText('官方公告清单',{exact:false}).click()
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  if(before.report.documents.length){
    await page.getByRole('button',{name:'查看来源 →'}).first().click()
    await expect(page.getByRole('dialog')).toContainText('SHA-256')
    await page.getByRole('button',{name:'Close this dialog'}).click()
    await expect(page.getByRole('dialog')).not.toBeVisible()
  }
  await page.getByText('官方公告清单',{exact:false}).click()
  await page.evaluate(()=>window.scrollTo(0,0))
  await page.screenshot({path:`../data/acceptance/report-${info.project.name}.png`,fullPage:true})
  const after=await (await request.get(`http://127.0.0.1:18080/api/v1/analyses/${item.runId}`)).json()
  expect(after.reportHash).toBe(before.reportHash)
  expect(after.report).toEqual(before.report)
})

test('test-only Java vector renders backend indicators and chart', async ({page,request}) => {
  // Explicit test fixture only. No production fallback and no claim of live market acceptance.
  const fs=await import('node:fs/promises')
  const vector=JSON.parse(await fs.readFile('../server/target/technical-vector.json','utf8'))
  const saved=await (await request.get('http://127.0.0.1:18080/api/v1/analyses?code=002463')).json()
  const item=saved.items.find((x:{status:string})=>x.status==='PARTIAL')
  test.skip(!item,'Needs a saved envelope to exercise the component contract')
  const envelope=await (await request.get(`http://127.0.0.1:18080/api/v1/analyses/${item.runId}`)).json()
  Object.assign(envelope.report,{source:'SYNTHETIC_TEST_ONLY',candles:vector.bars,indicators:vector.result.indicators,indicatorSeries:vector.result.series,trend:{state:vector.result.trend,reasons:vector.result.reasons},support:vector.result.support,resistance:vector.result.resistance,identity:{name:'合成测试向量',exchange:'TEST'},asOfTradeDate:vector.bars.at(-1).date})
  await page.route(`**/api/v1/analyses/${item.runId}`,route=>route.fulfill({json:envelope}))
  await page.goto('/')
  await page.getByRole('button',{name:'历史分析'}).click()
  await page.locator('a.history-row[href*="runId=' + item.runId + '"]').click()
  await expect(page.locator('.price-chart canvas')).toBeVisible()
  await expect(page.locator('.chart-card')).toContainText('120 / 120')
  await expect(page.locator('.metric-row').first()).toContainText(Number(vector.result.indicators.ma20).toLocaleString('zh-CN',{minimumFractionDigits:4,maximumFractionDigits:4}))
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
})
