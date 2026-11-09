<script setup lang="ts">
import { dateTime, price } from './api'
import type { ClosingQuote } from './types'

defineProps<{ quote: ClosingQuote }>()
</script>

<template>
  <section class="card workspace-card position-summary closing-quote" aria-label="腾讯盘后收盘">
    <div class="summary-title">
      <h3>{{ quote.name }} · {{ quote.tradeDate }} 收盘</h3>
      <span class="small-badge">腾讯已收盘</span>
    </div>
    <p class="summary-position"><strong>{{ price(quote.close) }} 元</strong>
      · 不复权 · 报价时间 {{ dateTime(quote.quotedAt) }}（北京时间）</p>
    <p class="summary-foot">技术指标待 BaoStock 当日日线与复权数据通过校验后更新。</p>
  </section>
</template>
