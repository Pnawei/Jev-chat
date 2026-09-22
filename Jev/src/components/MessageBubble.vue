<script setup lang="ts">
import type { AnalysisData } from '../api'
import AnalysisCard from './AnalysisCard.vue'

const props = defineProps<{
  sender: string
  text: string
  isSelf: boolean
  status?: 'idle' | 'analyzing' | 'done' | 'error'
  analysis?: AnalysisData | null
  errorMessage?: string
}>()

function avatarChar(name: string): string {
  return (name || '?').slice(0, 1).toUpperCase()
}

function bubbleClass(): string {
  if (props.status === 'analyzing') return 'bubble analyzing'
  if (props.status === 'done') return 'bubble has-result'
  if (props.status === 'error') return 'bubble has-error'
  return 'bubble'
}
</script>

<template>
  <div class="message-container" :class="{ self: props.isSelf }">
    <div class="message-row">
      <div class="avatar">{{ avatarChar(props.sender) }}</div>
      <div class="bubble-wrap">
        <div :class="bubbleClass()">{{ props.text }}</div>
        <div v-if="props.status === 'analyzing'" class="bubble-hint">⏳ 分析中…</div>
      </div>
    </div>
    <!-- 分析卡脱离气泡宽度限制，独立舒展展示 -->
    <AnalysisCard
      v-if="props.status === 'done' && props.analysis"
      :data="props.analysis"
      class="message-analysis"
    />
    <div
      v-if="props.status === 'error' && props.errorMessage"
      class="analysis-card message-analysis"
    >
      <div class="analysis-error">{{ props.errorMessage }}</div>
    </div>
  </div>
</template>
