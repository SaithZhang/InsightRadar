<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { request, SECURITY_CODE } from './api'
import type { ClosingQuote, PositionItem, Run } from './types'
import ReportView from './ReportView.vue'
import CloseQuoteCard from './CloseQuoteCard.vue'

const props = defineProps<{ routeCode: string | null; active: boolean }>()
const code = ref('002463')
const busy = ref(false)
const stage = ref('')
const error = ref('')
const run = ref<Run | null>(null)
const closePreview = ref<ClosingQuote | null>(null)
const positionUpdated = ref(false)
const llmMode = ref<'production' | 'debug'>('production')
const stages: Record<string, string> = { QUEUED: '数据', MARKET: '行情', DISCLOSURE: '官方公告', SEMANTIC: '原文证据' }
let timer: ReturnType<typeof setTimeout> | undefined
let generation = 0

watch(() => [props.active, props.routeCode] as const, ([active, routeCode]) => {
  if (!active) return
  const target = routeCode?.trim().toUpperCase()
  if (!target || !SECURITY_CODE.test(target) || target === code.value) return
  code.value = target
  generation++
  clearTimeout(timer)
  busy.value = false
  error.value = ''
  run.value = null
  closePreview.value = null
}, { immediate: true })

async function checkPositionVersion() {
  const current = run.value?.report
  const snapshot = current?.positionSnapshot
  positionUpdated.value = false
  if (!props.active || !current?.canonicalCode || !snapshot ||
      ['READ_FAILED', 'IDENTITY_UNCONFIRMED'].includes(snapshot.positionStatus)) return
  try {
    const { items } = await request<{ items: PositionItem[] }>('/positions?status=all')
    if (run.value?.report?.runId !== current.runId) return
    const latest = items.find(item => item.position.canonicalCode === current.canonicalCode)?.position
    positionUpdated.value = latest?.version !== snapshot.position?.version
  } catch {
    // The saved report still represents the position as of its own capture time.
  }
}
watch(() => [run.value?.runId, props.active], checkPositionVersion)
onMounted(() => window.addEventListener('focus', checkPositionVersion))
onBeforeUnmount(() => {
  generation++
  clearTimeout(timer)
  window.removeEventListener('focus', checkPositionVersion)
})

async function poll(id: string, token: number) {
  try {
    const result = await request<Run>('/analyses/' + id)
    if (token !== generation) return
    stage.value = result.stage
    if (['QUEUED', 'RUNNING'].includes(result.status)) {
      timer = setTimeout(() => poll(id, token), 1400)
      return
    }
    busy.value = false
    if (result.error) throw new Error(result.error.code + ' · ' + result.error.message)
    run.value = result
  } catch (err) {
    if (token !== generation) return
    busy.value = false
    error.value = String(err instanceof Error ? err.message : err)
  }
}
async function loadClosePreview(input: string, token: number) {
  try {
    const quote = await request<ClosingQuote | null>('/securities/close?code=' + input, undefined, undefined, 7000)
    if (token === generation) closePreview.value = quote
  } catch {
    // A missing preview never blocks the BaoStock analysis.
  }
}
async function analyze() {
  if (busy.value) return
  error.value = ''
  const input = code.value.trim().toUpperCase()
  if (!SECURITY_CODE.test(input)) {
    error.value = '请输入六位普通 A 股代码，可带 .SH / .SZ / .BJ'
    return
  }
  code.value = input
  busy.value = true
  stage.value = 'QUEUED'
  run.value = null
  closePreview.value = null
  const token = ++generation
  void loadClosePreview(input, token)
  try {
    const result = await request<{ runId: string }>('/analyses', { code: input, mode: llmMode.value })
    if (token === generation) await poll(result.runId, token)
  } catch (err) {
    if (token !== generation) return
    busy.value = false
    error.value = String(err instanceof Error ? err.message : err)
  }
}
</script>

<template>
  <section class="intro">
    <div><div class="eyebrow">CLARITY THROUGH EVIDENCE</div><h1>股票分析<span class="title-dot">.</span></h1>
      <p>看清趋势，核对条件，让每一个判断都有出处。</p></div>
    <div class="authority"><span>技术观察 · 人工决策</span><small>交易权限：无</small></div>
  </section>
  <section class="search-panel">
    <form @submit.prevent="analyze">
      <label for="stock-code">证券代码</label>
      <div class="search-controls">
        <el-input id="stock-code" v-model="code" maxlength="12" placeholder="例如 002463 或 002463.SZ"
                  :disabled="busy" aria-label="证券代码" clearable/>
        <el-button type="primary" native-type="submit" :loading="busy">
          {{ busy ? '正在分析' : '开始分析' }}<span v-if="!busy" class="button-arrow">↗</span>
        </el-button>
        <a class="workspace-link history-button" role="button"
           :href="'#/history?code=' + (SECURITY_CODE.test(code.trim().toUpperCase()) ? code.trim().toUpperCase() : '')">历史分析</a>
      </div>
      <div class="search-note"><label for="llm-mode">模型模式</label>
        <select id="llm-mode" v-model="llmMode" :disabled="busy">
          <option value="production">生产 · 优先复用</option>
          <option value="debug">调试 · 重新请求</option>
        </select>
      </div>
    </form>
    <div class="search-note"><span class="tiny-ring"></span>盘前和盘中使用上一交易日终值 · 盘后先显示腾讯已确认收盘，技术指标待 BaoStock 校验 · 最近目标 120 根</div>
  </section>
  <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="status-alert"/>
  <div v-if="busy" class="progress-banner" role="status">
    <span class="spinner"></span>正在获取并核验{{ stages[stage] ?? '数据' }}
    <small>报告完成后自动保存，可从分析记录查看。</small>
  </div>
  <CloseQuoteCard v-if="!run?.report && closePreview" :quote="closePreview"/>
  <el-button v-if="run?.report && !run.report.dataQuality.fresh &&
                   (run.report.closingQuote || run.report.marketTiming?.phase === 'POST_CLOSE')"
             class="back-link" @click="analyze">更新技术指标</el-button>
  <ReportView v-if="run?.report" :report="run.report" :report-hash="run.reportHash" :position-updated="positionUpdated"/>
  <section v-else-if="!busy" class="welcome card">
    <div class="welcome-orbit">◎<i></i></div><div class="eyebrow">ONE STOCK. FOUR QUESTIONS.</div>
    <h2>先看证据，再做判断。</h2>
    <p>输入普通 A 股代码，查看趋势、支撑压力、观察条件与官方披露。<br>来源缺失会明确显示为未知。</p>
    <div class="welcome-grid"><div><b>01</b><span>趋势与日 K</span></div><div><b>02</b><span>支撑与压力</span></div>
      <div><b>03</b><span>买卖复核条件</span></div><div><b>04</b><span>风险与原文</span></div></div>
  </section>
</template>
