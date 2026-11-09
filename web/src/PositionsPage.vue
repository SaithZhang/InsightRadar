<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { dateTime, price, request, SECURITY_CODE } from './api'
import type { Position, PositionAction, PositionItem } from './types'

const props = defineProps<{ active: boolean; routeCode: string | null }>()
const filter = ref<'holding' | 'cleared' | 'all'>('holding')
const items = ref<PositionItem[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const formError = ref('')
const notice = ref('')
const editing = ref(false)
const latest = ref<Position | null>(null)
const original = ref<Position | null>(null)
const form = ref({ code: '', quantity: '', unitCost: '', action: '' as PositionAction | '' })
const actionLabels: Record<PositionAction, string> = {
  REVIEW_REDUCTION: '进入减仓评估', REVIEW_EXIT: '进入退出评估',
}
const visibleItems = computed(() => items.value.filter(({ position }) =>
  filter.value === 'all' || (filter.value === 'holding' ? position.quantity > 0 : position.quantity === 0)))

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await request<{ items: PositionItem[] }>('/positions?status=all')
    items.value = response.items
    return true
  } catch (err) {
    error.value = String(err instanceof Error ? err.message : err)
    return false
  } finally { loading.value = false }
}
function openEditor(position: Position | null, code = '') {
  original.value = position
  form.value = {
    code: position?.canonicalCode ?? code,
    quantity: position ? String(position.quantity) : '',
    unitCost: position?.unitCost ?? '',
    action: position?.onMa55Trigger ?? '',
  }
  latest.value = null
  formError.value = ''
  notice.value = ''
  editing.value = true
}
function findPosition(code: string) {
  return items.value.find(item => item.position.canonicalCode === code)?.position ?? null
}

watch(() => [props.active, props.routeCode] as const, async ([active, target], _, cleanup) => {
  if (!active) return
  let cancelled = false
  cleanup(() => { cancelled = true })
  const loaded = await load()
  if (!cancelled && loaded && target && SECURITY_CODE.test(target)) {
    openEditor(findPosition(target), target)
  }
}, { immediate: true })

async function write(code: string, quantity: number, unitCost: string | null, action: PositionAction | null,
                     expectedVersion: number) {
  await request<Position>('/positions/' + code, { quantity, unitCost, onMa55Trigger: action, expectedVersion }, 'PUT', 190000)
}
async function save() {
  if (saving.value) return
  formError.value = ''
  latest.value = null
  let code = form.value.code.trim().toUpperCase()
  const quantityText = form.value.quantity.trim()
  const unitCost = form.value.unitCost.trim()
  if (!SECURITY_CODE.test(code)) { formError.value = '请输入六位证券代码，可带交易所后缀'; return }
  if (!/^\d{1,9}$/.test(quantityText)) { formError.value = '股数须为 0 至 999,999,999 的整数'; return }
  const quantity = Number(quantityText)
  if (quantity > 0 && unitCost && !/^-?\d{1,12}(\.\d{1,6})?$/.test(unitCost)) {
    formError.value = '每股成本最多 12 位整数及 6 位小数'
    return
  }
  if (quantity === 0 && original.value?.quantity !== 0 && !window.confirm('确认将该证券标记为清仓？成本和预设动作将清空。')) return
  saving.value = true
  try {
    if (!original.value) {
      const identity = await request<{ canonicalCode: string }>('/securities/resolve?code=' + code, undefined, undefined, 190000)
      code = identity.canonicalCode
    }
    await write(code, quantity, quantity ? unitCost || null : null, quantity ? form.value.action || null : null,
      original.value?.version ?? 0)
    notice.value = '已保存 ' + code
    editing.value = false
    if (quantity === 0 && filter.value === 'holding') filter.value = 'all'
    if (quantity > 0 && filter.value === 'cleared') filter.value = 'holding'
    await load()
  } catch (err) {
    formError.value = String(err instanceof Error ? err.message : err)
    if (code.length === 9 && await load()) {
      latest.value = findPosition(code)
      if (latest.value && latest.value.version === original.value?.version) latest.value = null
    }
  } finally { saving.value = false }
}
function adoptVersion() {
  if (!latest.value) return
  original.value = latest.value
  form.value.code = latest.value.canonicalCode
  latest.value = null
  formError.value = '已读取最新版本，确认上方输入后可再次保存。'
}
async function updateRow(position: Position, clear = false) {
  if (saving.value) return
  if (clear && !window.confirm('确认标记 ' + position.canonicalCode + ' 为清仓？成本和预设动作将清空。')) return
  saving.value = true
  notice.value = ''
  try {
    await write(position.canonicalCode, clear ? 0 : position.quantity, clear ? null : position.unitCost,
      clear ? null : position.onMa55Trigger, position.version)
    if (clear && filter.value === 'holding') filter.value = 'all'
    notice.value = clear ? '已标记清仓' : '已确认持仓未变'
    await load()
  } catch (err) {
    await load()
    error.value = String(err instanceof Error ? err.message : err) + '。请核对列表最新记录。'
  } finally { saving.value = false }
}
</script>

<template>
  <section class="intro">
    <div><div class="eyebrow">MY POSITIONS</div><h1>持仓管理<span class="title-dot">.</span></h1>
      <p>维护本机持仓和退出纪律。从持仓直接进入个股分析。</p></div>
    <el-button type="primary" :disabled="saving" @click="openEditor(null)">新增持仓</el-button>
  </section>
  <section class="card workspace-card positions-card">
    <div class="workspace-toolbar">
      <label for="positions-filter">显示</label>
      <select id="positions-filter" v-model="filter">
        <option value="holding">持有</option><option value="cleared">已清仓</option><option value="all">全部</option>
      </select>
      <span v-if="loading && !items.length" role="status" class="muted">正在读取…</span>
      <span v-if="notice" role="status">{{ notice }}</span>
      <el-button size="small" :disabled="loading || saving" @click="load">刷新列表</el-button>
    </div>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="status-alert"/>
    <p v-if="!visibleItems.length && !loading && !error" class="positions-empty">
      {{ filter === 'holding' ? '暂无持有记录。可手工新增，或切换查看已清仓记录。' : '暂无符合条件的持仓记录。' }}
    </p>
    <table v-if="visibleItems.length" class="positions-table" aria-label="持仓列表">
      <thead><tr><th scope="col">证券</th><th scope="col">股数与成本</th><th scope="col">参考收盘</th>
        <th scope="col">参考市值与浮动盈亏</th><th scope="col">确认与规则</th><th scope="col">操作</th></tr></thead>
      <tbody>
        <tr v-for="item in visibleItems" :key="item.position.canonicalCode">
          <td data-label="证券">
            <a class="text-link position-stock" :href="'#/analysis?code=' + item.position.canonicalCode">{{ item.name }}</a>
            <small>{{ item.position.canonicalCode }} · {{ item.position.quantity > 0 ? '持有' : '已清仓' }}</small>
          </td>
          <td data-label="股数与成本"><strong>{{ item.position.quantity.toLocaleString('zh-CN') }} 股</strong>
            <small>每股 {{ item.position.unitCost ?? '—' }}</small></td>
          <td data-label="参考收盘"><strong>{{ price(item.referenceClose) }}</strong><small>{{ item.quoteDate ?? '无已核验报价' }}</small></td>
          <td data-label="参考市值与浮动盈亏"><strong>{{ price(item.marketValue) }}</strong>
            <small>浮盈亏 {{ price(item.unrealizedPnl) }}<template v-if="item.unrealizedPnlPercent !== null">
              · {{ price(item.unrealizedPnlPercent) }}%</template></small></td>
          <td data-label="确认与规则">
            <span :class="{ attention: !item.confirmedToday }">{{ item.confirmedToday ? '今日已确认' : '持仓待确认' }}</span>
            <small>{{ dateTime(item.position.confirmedAt) }}</small>
            <small v-if="item.position.quantity > 0">{{ item.position.onMa55Trigger ? actionLabels[item.position.onMa55Trigger] : '未设退出动作' }}</small>
          </td>
          <td data-label="操作">
            <div class="position-actions">
              <el-button size="small" :disabled="saving" @click="openEditor(item.position)">编辑</el-button>
              <el-button size="small" :disabled="saving" @click="updateRow(item.position)">确认未变</el-button>
              <el-button v-if="item.position.quantity > 0" size="small" :disabled="saving" @click="updateRow(item.position, true)">标记清仓</el-button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
    <p class="muted workspace-note">估值使用注明交易日的已核验不复权收盘价，金额为人民币。持仓确认时间为北京时间。</p>
  </section>

  <el-dialog v-model="editing" :title="original ? '编辑持仓' : '新增持仓'" width="min(92vw, 500px)"
             :close-on-click-modal="!saving" :close-on-press-escape="!saving" :show-close="!saving" destroy-on-close>
    <form class="workspace-form position-form" @submit.prevent="save">
      <label>证券代码<input v-model="form.code" :disabled="saving || !!original" maxlength="12" placeholder="例如 002463 或 002463.SZ" required></label>
      <label>持有股数<input v-model="form.quantity" :disabled="saving" inputmode="numeric" maxlength="9" placeholder="零股表示清仓" required></label>
      <label>每股成本（选填）<input v-model="form.unitCost" :disabled="saving || form.quantity === '0'" inputmode="decimal" maxlength="20" placeholder="按券商记录录入"></label>
      <label>MA55 触发动作<select v-model="form.action" :disabled="saving || form.quantity === '0'">
        <option value="">暂不设置</option>
        <option value="REVIEW_REDUCTION">进入减仓评估</option><option value="REVIEW_EXIT">进入退出评估</option>
      </select></label>
      <p class="muted">连续两个开放日收盘低于各自 MA55 时，报告显示你选定的动作。</p>
      <el-alert v-if="formError" :title="formError" type="warning" show-icon :closable="false"/>
      <div v-if="latest" class="conflict-info">
        <p>最新记录 {{ latest.quantity }} 股 · 成本 {{ latest.unitCost ?? '—' }} · {{ dateTime(latest.confirmedAt) }}</p>
        <p>预设动作 {{ latest.onMa55Trigger ? actionLabels[latest.onMa55Trigger] : '未设置' }}</p>
        <el-button size="small" :disabled="saving" @click="adoptVersion">使用最新版本并保留输入</el-button>
      </div>
      <div class="form-actions">
        <el-button :disabled="saving" @click="editing = false">取消</el-button>
        <el-button type="primary" native-type="submit" :loading="saving" :disabled="!!latest">保存持仓</el-button>
      </div>
    </form>
  </el-dialog>
</template>
