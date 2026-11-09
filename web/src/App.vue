<script setup lang="ts">
import { nextTick, onMounted, onBeforeUnmount, ref } from 'vue'
import AnalysisPage from './AnalysisPage.vue'
import PositionsPage from './PositionsPage.vue'
import HistoryPage from './HistoryPage.vue'

const tabs = [
  { path: '/positions', title: '持仓' },
  { path: '/analysis', title: '个股分析' },
  { path: '/history', title: '分析记录' },
] as const

function readRoute() {
  const [path, search = ''] = window.location.hash.slice(1).split('?', 2)
  return {
    path: path === '/positions' || path === '/history' ? path : '/analysis',
    params: new URLSearchParams(search),
  }
}

const route = ref(readRoute())
const visitedPositions = ref(route.value.path === '/positions')
let positionsScroll = 0
async function updateRoute() {
  const previousPath = route.value.path
  if (previousPath === '/positions') positionsScroll = window.scrollY
  route.value = readRoute()
  if (route.value.path === '/positions') visitedPositions.value = true
  await nextTick()
  window.scrollTo(0, route.value.path === '/positions' ? positionsScroll : 0)
}
onMounted(() => {
  window.history.scrollRestoration = 'manual'
  window.addEventListener('hashchange', updateRoute)
})
onBeforeUnmount(() => window.removeEventListener('hashchange', updateRoute))
</script>

<template>
  <header class="topbar">
    <a class="brand" href="#/analysis" aria-label="InsightRadar 首页">
      <span class="brand-mark">◎</span><strong>InsightRadar</strong><span class="version">V0.02</span>
    </a>
    <nav class="primary-nav" aria-label="主导航">
      <a v-for="tab in tabs" :key="tab.path" :href="'#' + tab.path"
         :aria-current="route.path === tab.path ? 'page' : undefined">{{ tab.title }}</a>
    </nav>
    <div class="top-right"><span class="local-dot"></span>本地研究工作台</div>
  </header>
  <main>
    <div v-show="route.path === '/analysis'">
      <AnalysisPage :active="route.path === '/analysis'" :route-code="route.params.get('code')"/>
    </div>
    <div v-if="visitedPositions" v-show="route.path === '/positions'">
      <PositionsPage :active="route.path === '/positions'" :route-code="route.params.get('code')"/>
    </div>
    <HistoryPage v-if="route.path === '/history'" :code-filter="route.params.get('code')"
                 :from-filter="route.params.get('from')" :to-filter="route.params.get('to')"
                 :page-filter="route.params.get('page')" :run-id="route.params.get('runId')"/>
  </main>
  <footer>INSIGHTRADAR / V0.02 <span>证据辅助判断 · 未验证收益能力 · 无交易执行</span></footer>
</template>
