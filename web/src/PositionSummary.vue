<script setup lang="ts">
import { computed } from 'vue'
import { dateTime, price } from './api'
import type { PositionSnapshot } from './types'

const props = defineProps<{ snapshot?: PositionSnapshot; historical?: boolean; updated?: boolean }>()
const positionLabels: Record<PositionSnapshot['positionStatus'], string> = {
  HOLDING: '持有', CLEARED: '已清仓', UNREGISTERED: '未登记',
  IDENTITY_UNCONFIRMED: '持仓无法匹配', READ_FAILED: '持仓读取失败',
}
const prices: Record<PositionSnapshot['priceState'], string> = {
  TRIGGERED: '已触发', NOT_TRIGGERED: '未触发', DATA_INSUFFICIENT: '数据不足',
}
const actions: Record<PositionSnapshot['action'], string> = {
  CONFIRM_POSITION: '先确认持仓', OBSERVE: '空仓观察', WAIT_FOR_DATA: '暂不能判断 MA55 退出条件',
  EXIT_CONDITION_NOT_MET: 'MA55 退出条件未触发', SET_EXIT_RULE: '价格风险条件已触发，待补退出规则',
  REVIEW_REDUCTION: '进入减仓评估', REVIEW_EXIT: '进入退出评估',
}
const rows = computed(() => {
  const evidence = props.snapshot?.evidence
  if (!evidence) return []
  return [
    { date: evidence.previousDate, close: evidence.previousClose, ma55: evidence.previousMa55 },
    { date: evidence.date, close: evidence.close, ma55: evidence.ma55 },
  ].filter(row => row.date && row.close !== null && row.ma55 !== null)
})
</script>

<template>
  <section class="card workspace-card position-summary" aria-label="持仓与下一步">
    <div v-if="!snapshot" class="summary-legacy"><h3>持仓与下一步</h3><p>当时未记录持仓上下文。</p></div>
    <template v-else>
      <div class="summary-title"><h3>持仓与下一步</h3>
        <span class="small-badge" :class="snapshot.priceState.toLowerCase()">MA55 条件 {{ prices[snapshot.priceState] }}</span>
      </div>
      <p class="summary-position">
        <strong>{{ positionLabels[snapshot.positionStatus] }}</strong>
        <template v-if="snapshot.position">
          · {{ snapshot.position.quantity.toLocaleString('zh-CN') }} 股
          <template v-if="snapshot.position.unitCost !== null"> · 成本 {{ snapshot.position.unitCost }} 元/股</template>
          · 确认于 {{ dateTime(snapshot.position.confirmedAt) }}
        </template>
        <strong v-if="snapshot.confirmationStatus === 'STALE'" class="attention"> · 持仓待确认</strong>
      </p>
      <p v-if="updated" class="attention" role="status">持仓已更新，请重新生成以查看当前动作。下方为当次快照。</p>
      <div class="summary-grid">
        <div>
          <div class="eyebrow">{{ historical || updated ? '当次动作' : '下一步动作' }}</div>
          <h4>{{ actions[snapshot.action] }}</h4>
          <p>{{ snapshot.reason }}</p>
          <a v-if="!historical && snapshot.canonicalCode &&
                   (updated || snapshot.action === 'SET_EXIT_RULE' ||
                   (snapshot.action === 'CONFIRM_POSITION' && snapshot.positionStatus !== 'READ_FAILED'))"
             class="text-link" :href="'#/positions?code=' + snapshot.canonicalCode">
            {{ snapshot.positionStatus === 'UNREGISTERED' ? '登记持仓' : '前往持仓管理' }} →
          </a>
        </div>
        <div>
          <div class="eyebrow">决定性证据</div>
          <p>触发条件为连续两个开放日的收盘均低于各自 MA55。</p>
          <ul v-if="rows.length" class="evidence-dates">
            <li v-for="row in rows" :key="row.date!">{{ row.date }} · 收盘 {{ price(row.close, 4) }} / MA55 {{ price(row.ma55, 4) }}</li>
          </ul>
          <p v-if="snapshot.priceState === 'DATA_INSUFFICIENT' && snapshot.action !== 'WAIT_FOR_DATA'">{{ snapshot.nextCheck.message }}</p>
          <div class="eyebrow next-check">下次检查</div>
          <p v-if="snapshot.nextCheck.earliestAnalysisAt">
            {{ snapshot.nextCheck.tradeDate }} 收盘 · 最早 {{ dateTime(snapshot.nextCheck.earliestAnalysisAt) }}（北京时间）
            <br>{{ snapshot.nextCheck.message }}
          </p>
          <p v-else-if="snapshot.nextCheck.earliestAnalysisDate">
            {{ snapshot.nextCheck.tradeDate }} 收盘 · 最早 {{ snapshot.nextCheck.earliestAnalysisDate }} 生成分析
          </p>
          <p v-else>{{ snapshot.nextCheck.message }}</p>
        </div>
      </div>
      <p class="summary-foot">持仓读取时间 {{ dateTime(snapshot.capturedAt) }} · 本机手工记录 · {{ snapshot.ruleVersion }}</p>
    </template>
  </section>
</template>
