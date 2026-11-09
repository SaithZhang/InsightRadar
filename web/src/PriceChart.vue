<script setup lang="ts">
import { onMounted,onBeforeUnmount,ref,watch } from 'vue'
import * as echarts from 'echarts/core'
import { CandlestickChart,LineChart } from 'echarts/charts'
import { GridComponent,TooltipComponent,DataZoomComponent,MarkAreaComponent,LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { Report } from './types'
echarts.use([CandlestickChart,LineChart,GridComponent,TooltipComponent,DataZoomComponent,MarkAreaComponent,LegendComponent,CanvasRenderer])
const props=defineProps<{report:Report}>();const element=ref<HTMLDivElement>();let chart:echarts.ECharts|undefined;let observer:ResizeObserver|undefined
function draw(){if(!chart)return;const r=props.report;const areas=[r.support,r.resistance].filter(z=>z.valid).map(z=>[{name:z===r.support?'支撑区':'压力区',yAxis:Number(z.lower),itemStyle:{color:z===r.support?'rgba(190,148,123,.13)':'rgba(138,127,219,.11)'}},{yAxis:Number(z.upper)}]);chart.setOption({animation:false,grid:{left:12,right:66,top:35,bottom:60,containLabel:false},legend:{data:['日 K','MA20','MA55'],top:0,textStyle:{color:'#7e8a9c'}},tooltip:{trigger:'axis',axisPointer:{type:'cross'}},xAxis:{type:'category',data:r.candles.map(b=>b.date),axisLabel:{color:'#8c98a9'},axisLine:{lineStyle:{color:'#e9edf3'}}},yAxis:{scale:true,position:'right',axisLabel:{color:'#8c98a9'},splitLine:{lineStyle:{color:'#edf1f7'}}},dataZoom:[{type:'inside'},{type:'slider',height:17,bottom:8,borderColor:'transparent'}],series:[{name:'日 K',type:'candlestick',data:r.candles.map(b=>[b.open,b.close,b.low,b.high].map(Number)),itemStyle:{color:'#cd5466',color0:'#219980',borderColor:'#cd5466',borderColor0:'#219980'},markArea:{silent:true,label:{fontSize:10,color:'#888'},data:areas}},{name:'MA20',type:'line',data:r.indicatorSeries.map(p=>p.ma20===null?null:Number(p.ma20)),symbol:'none',lineStyle:{width:2,color:'#cfa563'},itemStyle:{color:'#cfa563'}},{name:'MA55',type:'line',data:r.indicatorSeries.map(p=>p.ma55===null?null:Number(p.ma55)),symbol:'none',lineStyle:{width:2,color:'#8580cb'},itemStyle:{color:'#8580cb'}}]},true)}
onMounted(()=>{chart=echarts.init(element.value!);draw();observer=new ResizeObserver(()=>chart?.resize());observer.observe(element.value!)})
watch(()=>props.report,draw)
onBeforeUnmount(()=>{observer?.disconnect();chart?.dispose()})
</script>
<template><div ref="element" class="price-chart" role="img" aria-label="后端报告的前复权日 K 与 MA20、MA55，支持缩放" /></template>
