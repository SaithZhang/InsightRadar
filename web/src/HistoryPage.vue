<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { dateTime, request, SECURITY_CODE } from './api'
import type { HistoryItem, Run } from './types'
import ReportView from './ReportView.vue'

const props = defineProps<{
  codeFilter: string | null; fromFilter: string | null; toFilter: string | null; pageFilter: string | null; runId: string | null
}>()
const code = ref('')
const from = ref('')
const to = ref('')
const error = ref('')
const busy = ref(false)
const items = ref<HistoryItem[]>([])
const run = ref<Run | null>(null)
const size = 10
const page = computed(() => /^\d{1,5}$/.test(props.pageFilter ?? '') ? Math.min(10000, Number(props.pageFilter)) : 0)
const statuses: Record<string, string> = {
  COMPLETED: '完成', PARTIAL: '部分可用', FAILED: '失败', QUEUED: '排队中', RUNNING: '生成中',
}
function filters(currentPage = 0) {
  const query = new URLSearchParams()
  if (props.codeFilter) query.set('code', props.codeFilter)
  if (props.fromFilter) query.set('from', props.fromFilter)
  if (props.toFilter) query.set('to', props.toFilter)
  if (currentPage) query.set('page', String(currentPage))
  return query
}
function url(query: URLSearchParams) {
  return '#/history' + (query.size ? '?' + query.toString() : '')
}
function detailLink(id: string) {
  const query = filters(page.value)
  query.set('runId', id)
  return url(query)
}
function search() {
  const value = code.value.trim().toUpperCase()
  if (value && !SECURITY_CODE.test(value)) {
    error.value = '请输入六位普通 A 股代码，可带交易所后缀'
    return
  }
  if (from.value && to.value && from.value > to.value) {
    error.value = '开始日期应早于或等于结束日期'
    return
  }
  const query = new URLSearchParams()
  if (value) query.set('code', value)
  if (from.value) query.set('from', from.value)
  if (to.value) query.set('to', to.value)
  const target = url(query)
  if (window.location.hash === target) void load()
  else window.location.hash = target
}
let generation = 0
async function load() {
  const token = ++generation
  busy.value = true
  error.value = ''
  run.value = null
  items.value = []
  try {
    if (props.runId) {
      if (!/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(props.runId)) throw new Error('报告编号无效')
      const result = await request<Run>('/analyses/' + props.runId)
      if (token !== generation) return
      if (!result.report) throw new Error(result.error?.message ?? '该分析尚无可查看的终态快照，可稍后返回查看。')
      run.value = result
    } else {
      const query = filters(page.value)
      query.set('size', String(size))
      const result = await request<{ items: HistoryItem[] }>('/analyses?' + query)
      if (token === generation) items.value = result.items
    }
  } catch (err) {
    if (token === generation) error.value = String(err instanceof Error ? err.message : err)
  } finally {
    if (token === generation) busy.value = false
  }
}
watch(() => [props.codeFilter, props.fromFilter, props.toFilter, page.value, props.runId], () => {
  code.value = props.codeFilter ?? ''
  from.value = props.fromFilter ?? ''
  to.value = props.toFilter ?? ''
  void load()
}, { immediate: true })
</script>

<template>
  <section class="intro">
    <div><div class="eyebrow">RESEARCH HISTORY</div><h1>分析记录<span class="title-dot">.</span></h1>
      <p>直接读取已保存的结果。生成日期按北京时间筛选。</p></div>
  </section>
  <a v-if="runId" class="workspace-link back-link" :href="url(filters(page))">← 返回分析记录</a>
  <section v-else class="card workspace-card">
    <form class="workspace-form history-filters" @submit.prevent="search">
      <label>证券代码<input v-model="code" maxlength="12" placeholder="全部标的"></label>
      <label>开始日期<input v-model="from" type="date"></label>
      <label>结束日期<input v-model="to" type="date"></label>
      <el-button type="primary" native-type="submit" :disabled="busy">筛选</el-button>
    </form>
    <div class="history-list" aria-label="历史报告列表">
      <a v-for="item in items" :key="item.runId" class="history-row" :href="detailLink(item.runId)">
        <div><b>{{ item.canonicalCode ?? item.requestedCode }}</b><small>{{ dateTime(item.createdAt) }}</small></div>
        <div><b>{{ statuses[item.status] ?? item.status }}</b><small>行情基准 {{ item.asOfTradeDate ?? '未知' }}</small></div>
      </a>
      <p v-if="!items.length && !busy && !error" class="muted">暂无符合条件的分析记录。</p>
    </div>
    <div class="pagination">
      <a v-if="page > 0 && !busy" class="workspace-link" :href="url(filters(page - 1))">上一页</a>
      <span>第 {{ page + 1 }} 页</span>
      <a v-if="items.length === size && page < 10000 && !busy" class="workspace-link" :href="url(filters(page + 1))">下一页</a>
    </div>
  </section>
  <p v-if="busy" role="status" class="muted">正在读取分析记录…</p>
  <el-alert v-if="error" :title="error" type="error" :closable="false" class="status-alert"/>
  <ReportView v-if="run?.report" :report="run.report" :report-hash="run.reportHash" historical/>
</template>
