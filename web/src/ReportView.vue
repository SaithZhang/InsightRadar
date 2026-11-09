<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { request, price, officialLink, dateTime } from './api'
import type { Report, Evaluation, Document } from './types'
import PriceChart from './PriceChart.vue'
import PositionSummary from './PositionSummary.vue'
import CloseQuoteCard from './CloseQuoteCard.vue'

const props = defineProps<{ report: Report; reportHash: string | null; historical?: boolean; positionUpdated?: boolean }>()
const evaluations = ref<Evaluation[]>([])
const evaluating = ref(false)
const error = ref('')
const documentOpen = ref(false)
const documentData = ref<{ metadata: Document; pages: { page: number; text: string }[] } | null>(null)
const sources = ref<HTMLElement | null>(null)
const labels:Record<string,string>={UP:'上行',DOWN:'下行',MIXED:'分歧',UNKNOWN:'未知',READY:'可计算',PARTIAL:'部分可用',COMPLETE:'声明范围完整',UNAVAILABLE:'不可用',WAITING_NEXT_BAR:'等待下一日终值',TECHNICAL_CONDITION_MET:'技术条件满足',EXPIRED_NO_SIGNAL:'已过期 · 未触发',INVALIDATED:'计划失效',NEEDS_RECHECK:'资料不足 · 待补验',ADJUSTMENT_CHANGED_RECHECK:'复权口径变化 · 待复核',INVALIDATED_AFTER_TRIGGER:'触发后跌破下沿',PRICE_RISK_REVIEW:'价格风险 · 人工复核',NOT_TRIGGERED:'条件未触发',EVENT_RISK_REVIEW:'事件风险 · 人工复核',DISCLOSED_FACT:'已披露事实',COMPANY_EXPLANATION:'公司解释',MODEL_INFERENCE:'模型推断',POSITIVE:'正向',NEGATIVE:'负向',UNCERTAIN:'不确定'}
const label=(s:string|undefined|null)=>s?(labels[s]??s):'未知'

const phases = { PRE_OPEN: '盘前', IN_SESSION: '盘中', POST_CLOSE: '盘后', NON_TRADING_DAY: '非交易日', UNKNOWN: '交易时段待确认' }
const currentPlan = computed(() => evaluations.value.at(-1)?.status ?? props.report.buyPlan?.status)
const title = computed(() => props.report.identity?.name ?? props.report.officialIssuer?.name ?? props.report.requestedCode)

async function loadEvaluations(id: string) {
  const result = await request<{ items: Evaluation[] }>(`/analyses/${id}/plan-evaluations`)
  if (props.report.runId === id) evaluations.value = result.items
}
watch(() => props.report.runId, async id => {
  evaluations.value = []
  error.value = ''
  try { await loadEvaluations(id) } catch (err) {
    if (props.report.runId === id) error.value = String(err)
  }
}, { immediate: true })
async function review() {
  const plan = props.report.buyPlan
  if (!plan) return
  const id = props.report.runId
  evaluating.value = true
  error.value = ''
  try {
    await request(`/plans/${plan.id}/evaluations`, {})
    await loadEvaluations(id)
  } catch (err) { error.value = String(err) }
  finally { evaluating.value = false }
}
async function openDoc(id: string) {
  documentData.value = null
  documentOpen.value = true
  error.value = ''
  try { documentData.value = await request(`/disclosures/${id}`) }
  catch (err) { error.value = String(err); documentOpen.value = false }
}
function showSources() {
  sources.value?.querySelector('details')?.setAttribute('open', '')
  sources.value?.scrollIntoView({ block: 'start' })
}
</script>
<template>
 <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="status-alert"/>
   <div class="report-heading"><div><div class="eyebrow">{{historical?'HISTORICAL SNAPSHOT / 只读快照':'ANALYSIS SNAPSHOT / 已保存快照'}}</div><h2>{{title}}<span>{{report.canonicalCode??report.requestedCode}}{{report.identity?'':' · 身份待核验'}}</span></h2><p>行情基准日：{{report.asOfTradeDate??'未取得有效终值'}}<span class="separator">·</span>分析时点：{{dateTime(report.knowledgeCutoff)}}（北京时间）<template v-if="report.marketTiming"> · {{ phases[report.marketTiming.phase] }}</template></p></div><span class="state-pill" :class="report.trend.state.toLowerCase()">{{report.trend.state}} · {{label(report.trend.state)}}</span></div>
   <CloseQuoteCard v-if="report.closingQuote" :quote="report.closingQuote"/>
   <div v-if="report.marketTiming?.awaitingPublication" class="gap-banner" role="status">
     <b>{{report.closingQuote ? 'BaoStock 技术日线待发布' : '当日收盘终值待发布'}}</b>
     <span>当日行情和复权数据校验后才能更新日线判断。<template v-if="report.marketTiming.providerReleaseAt">
       最早于 {{dateTime(report.marketTiming.providerReleaseAt)}}（北京时间）重新分析。</template></span>
   </div>
   <div v-else-if="report.marketTiming?.phase === 'POST_CLOSE' && !report.dataQuality.fresh" class="gap-banner" role="status">
     <b>{{report.closingQuote ? 'BaoStock 技术日线尚未确认' : '盘后终值尚未确认'}}</b>
     <span>应有交易日 {{report.dataQuality.expectedSession ?? '待确认'}} · 已确认行情截至 {{report.asOfTradeDate ?? '暂无'}}</span>
   </div>
   <PositionSummary :snapshot="report.positionSnapshot" :historical="historical" :updated="positionUpdated"/>
   <div v-if="report.dataGaps.length" class="gap-banner"><b>资料有缺口</b><span>技术：{{label(report.technicalStatus)}} · 事件：{{label(report.eventStatus)}}。未知不代表没有风险。</span><a href="#sources" @click.prevent="showSources">查看来源与缺口 ↓</a></div>
   <div class="section-kicker"><h2>01 / 趋势与价格结构</h2><span>TECH-R1 · 前复权日 K</span></div>
   <section class="trend-layout"><article class="card chart-card"><div class="card-head"><div><h3>日 K 与均线</h3><p>{{report.candles.length}} / 120 根有效已完成 K 线</p></div><span class="small-badge">{{report.source}}</span></div><PriceChart v-if="report.candles.length" :report="report"/><div v-else class="chart-empty"><span>⌁</span><h3>行情尚不可用</h3><p v-for="e in report.errors" :key="e.code">{{e.message}}</p><p>未绘制替代价格。可稍后重新分析。</p></div></article>
    <aside class="card trend-card"><div class="eyebrow">TREND OVERVIEW</div><h3>{{({UP:'上行结构成立',DOWN:'下行结构成立',MIXED:'价格与均线存在分歧',UNKNOWN:'数据不足，暂不判定'} as Record<string,string>)[report.trend.state]}}</h3><div class="last-price">{{price(report.candles.at(-1)?.close)}}<small>最近有效收盘 / 元</small></div><div class="metric-row"><span>MA20</span><strong class="gold">{{price(report.indicators.ma20,4)}}</strong></div><div class="metric-row"><span>MA55</span><strong class="purple">{{price(report.indicators.ma55,4)}}</strong></div><div class="metric-row"><span>Wilder ATR14</span><strong>{{price(report.indicators.atr14,4)}}</strong></div><details class="formula"><summary>判断依据</summary><p>上行：收盘 &gt; MA20 &gt; MA55，且两条均线均高于 5 根前。下行条件相反；严格比较，等号不满足。</p><p>5 根前 MA20：{{price(report.indicators.ma20FiveBarsAgo,4)}}<br>5 根前 MA55：{{price(report.indicators.ma55FiveBarsAgo,4)}}</p><code>{{report.trend.reasons.join(' · ')}}</code></details></aside></section>
   <div class="middle-layout"><section><div class="section-kicker"><h2>02 / 支撑与压力</h2><span>区间，不是目标价</span></div><article class="card zones-card"><div v-for="(zone,i) in [report.support,report.resistance]" :key="i" class="zone" :class="i?'resistance':'support'"><div class="zone-label"><i></i>{{i?'压力观察区':'支撑观察区'}}</div><strong>{{zone.valid?`${price(zone.lower)} – ${price(zone.upper)}`:'无清晰区域'}}</strong><p v-if="zone.valid">中心 {{price(zone.center,4)}} · {{zone.source}}<br>半宽 {{price(zone.halfWidth,4)}} = 0.5 × ATR14</p><p v-else>{{zone.reason==='ZONE_OVERLAP'?'两区重叠，暂不输出价区':zone.reason==='NO_VALID_CANDIDATE'?'没有有效候选中心':'指标或价格基础尚不足'}}</p></div></article></section>
   <section><div class="section-kicker"><h2>03 / 买卖复核条件</h2><span>无自动交易</span></div><article class="card plan-card"><div class="card-head"><h3>趋势回踩 · D+1 观察计划</h3></div><div class="plan-body"><div class="plan-status">{{report.buyPlan?label(currentPlan):'当前未建立观察计划'}}</div><template v-if="report.buyPlan"><p>D {{report.buyPlan.baseTradeDate}} → 固定 D+1 {{report.buyPlan.targetTradeDate}}</p><p>冻结区间 {{price(report.buyPlan.zone.lower)}}–{{price(report.buyPlan.zone.upper)}}</p><ul class="conditions"><li>最低价进入冻结区间，含两端</li><li>收盘严格高于上沿且高于开盘</li><li>停牌或缺数据不顺延至 D+2</li></ul><el-button size="small" :loading="evaluating" @click="review">检查 D+1 条件</el-button></template><p v-else>需要上行趋势、有效支撑区和可确认的下一开放日。</p><div class="sell-row"><b>卖出复核 · {{label(report.sellReview.state)}}</b><p>连续两个交易所开放日各自收盘 &lt; MA55，才提示人工复核。</p><small v-if="report.sellReview.previousDate">{{report.sellReview.previousDate}}：{{price(report.sellReview.previousClose)}} / MA55 {{price(report.sellReview.previousMa55)}}<br>{{report.sellReview.date}}：{{price(report.sellReview.close)}} / MA55 {{price(report.sellReview.ma55)}}</small></div><div class="quiet-warning">条件成立也不构成买入或卖出指令。</div></div></article></section></div>
   <div class="section-kicker"><h2>04 / 重要事实、风险与下一次核验</h2><span>官方原文优先</span></div>
   <section class="card"><div class="card-head"><div><h3>事件与基本面证据</h3><p>最近 90 个自然日公告 + 最新已披露定期报告</p><p v-if="report.semantic.mode">{{report.semantic.mode==='DEBUG'?'调试模式':'生产模式'}}<template v-if="report.semantic.cacheHit"> · 已复用模型结果</template><template v-else-if="report.semantic.apiDispatched"> · 已请求模型</template><template v-if="report.semantic.pagesReviewed"> · 输入 {{report.semantic.pagesReviewed}} 页</template></p></div><span class="small-badge">{{label(report.eventStatus)}}</span></div><div class="evidence-layout"><div><div class="eyebrow">KEY FACTS / 最多 5 条</div><div v-if="!report.facts.length" class="empty-copy"><h3>暂无通过验证的语义摘要</h3><p>{{report.semantic.reason==='LLM_NOT_CONFIGURED'?'本工程尚未配置模型。下方保留已取得的官方公告。':report.semantic.reason==='LLM_MONTHLY_BUDGET_REACHED'?'本月模型预算已达到上限，仍可查看公告与历史报告。':'模型或引用校验未完成；请查看官方原文与覆盖详情。'}}</p><small>不能据此得出“没有重大风险”。</small></div><article v-for="(fact,i) in report.facts" :key="i" class="fact"><div class="fact-title"><span class="fact-number">{{String(i+1).padStart(2,'0')}}</span><h3>{{fact.statement}}</h3></div><div class="fact-tags"><span>{{label(fact.classification)}}</span><span>{{label(fact.impact)}}</span><span>{{fact.asOf}}</span></div><p>{{fact.whyItMatters}}</p><details v-for="e in fact.evidence" :key="e.documentId+e.page"><summary>原文证据 · 第 {{e.page}} 页</summary><blockquote>{{e.quote}}</blockquote><el-button text @click="openDoc(e.documentId)">查看文档与完整页文 →</el-button></details></article></div><aside class="followups"><div class="eyebrow">NEXT VERIFICATION / 人工核验</div><p v-if="!report.followUps.length" class="muted">暂无已生成核验点。原文不足时不制造问题或标准。</p><article v-for="(follow,i) in report.followUps" :key="i"><span>{{i+1}}</span><div><b>{{follow.question}}</b><p>{{follow.criterion}}</p><small>{{follow.evidenceSource}} · {{follow.expectedVerificationTime}}</small></div></article></aside></div>
   <div class="document-list"><details><summary>官方公告清单 <span>{{report.documents.length}} 份 · 已抽取 {{report.coverage.processedDocuments??0}} 份</span></summary><div v-if="!report.documents.length" class="muted">官方目录尚不可用。</div><div v-for="doc in report.documents" :key="doc.documentId" class="document-row"><div><b>{{doc.title}}</b><small>{{doc.publishedAt.slice(0,10)}} · {{doc.textExtractionStatus}}<span v-if="doc.correctionOrSupplement"> · 更正/补充</span><span v-if="doc.latestPeriodicReport"> · 最新检索定期报告</span></small></div><el-button text @click="openDoc(doc.documentId)">查看来源 →</el-button></div></details></div></section>
   <section ref="sources" class="source-details"><details><summary>数据来源、截止时间与覆盖缺口 <span>{{report.dataGaps.length}} 项</span></summary><p>知识截止：{{dateTime(report.knowledgeCutoff)}}（北京时间）</p><p v-for="gap in report.dataGaps" :key="gap" class="gap-code">{{gap}}</p><h4>复权与终值</h4><pre>{{JSON.stringify(report.priceBasis,null,2)}}</pre><h4>公告处理范围</h4><pre>{{JSON.stringify(report.coverage,null,2)}}</pre></details><details><summary>规则版本与复现指纹</summary><pre>{{JSON.stringify(report.provenance,null,2)}}</pre><p class="mono">报告 {{report.runId}}<br>SHA-256 {{reportHash}}</p><p>重复分析产生新快照；历史报告不随来源修订而改写。</p></details><details><summary>D+1 后验记录 <span>{{evaluations.length}} 条</span></summary><p v-if="!evaluations.length">尚无追加核验记录。</p><article v-for="e in evaluations" :key="e.id" class="evaluation"><b>{{label(e.status)}}</b><p>固定目标 {{e.targetTradeDate}} · 观测 {{e.observedTradeDate??'未取得'}} · {{dateTime(e.evaluatedAt)}}</p><code>{{e.reason}}</code><p v-for="(v,k) in e.conditions" :key="k">{{k}}：{{v?'满足':'未满足'}}</p></article></details></section>
 <el-dialog v-model="documentOpen" title="官方文档与原文页" width="min(92vw, 850px)"><template v-if="documentData"><h3>{{documentData.metadata.title}}</h3><p><a :href="officialLink(documentData.metadata.officialUrl)" target="_blank" rel="noopener noreferrer">官方公告 ↗</a>　<a :href="officialLink(documentData.metadata.pdfUrl)" target="_blank" rel="noopener noreferrer">原始 PDF ↗</a></p><p class="mono">SHA-256 {{documentData.metadata.pdfSha256??'尚未下载'}}<br>{{documentData.metadata.textExtractionStatus}}</p><details v-for="page in documentData.pages" :key="page.page" class="pdf-page"><summary>PDF 第 {{page.page}} 页</summary><pre>{{page.text}}</pre></details><p v-if="!documentData.pages.length">尚无可抽取文本；不展示虚构引文。</p></template><p v-else>正在读取文档…</p></el-dialog>
</template>
