<script setup lang="ts">
import { SCORE_LABELS, type Dashboard, type ScoreKey } from '../api'

const props = defineProps<{
  data: Dashboard
}>()

const SCORE_ORDER: ScoreKey[] = [
  'initiative',
  'engagement',
  'warmth',
  'intimacy',
  'flirtiness',
  'vulnerability',
  'attention_toward_user',
]

function trendMark(t: string): string {
  if (t === 'rising') return '↑'
  if (t === 'falling') return '↓'
  return '→'
}

function trendClass(t: string): string {
  if (t === 'rising') return 'trend-up'
  if (t === 'falling') return 'trend-down'
  return 'trend-flat'
}
</script>

<template>
  <div class="dashboard">
    <div class="dash-title">对话总览</div>

    <div class="dash-chips">
      <div class="dash-chip">
        <span class="chip-label">互动方向</span>
        <span class="chip-value">{{ props.data.overall_direction.label }}</span>
      </div>
      <div class="dash-chip">
        <span class="chip-label">主要动机</span>
        <span class="chip-value">{{ props.data.dominant_motivation.label }}</span>
      </div>
    </div>

    <div class="dash-scores">
      <div v-for="key in SCORE_ORDER" :key="key" class="dash-score-row">
        <span class="score-name">{{ SCORE_LABELS[key] }}</span>
        <span class="score-val">{{ props.data.scores[key]?.avg ?? '-' }}</span>
        <span class="trend" :class="trendClass(props.data.scores[key]?.trend)">
          {{ trendMark(props.data.scores[key]?.trend || 'stable') }}
        </span>
      </div>
    </div>

    <div class="dash-strategy">
      <div class="section-title">💬 回复策略</div>
      <div v-if="props.data.reply_strategy" class="strategy-text">
        {{ props.data.reply_strategy }}
      </div>
      <div v-else class="strategy-text hint">{{ props.data.strategy_hint }}</div>
      <div
        v-for="(reply, i) in props.data.reply_suggestions"
        :key="i"
        class="reply-item"
      >
        {{ reply }}
      </div>
      <div v-if="props.data.reply_error" class="reply-error">
        {{ props.data.reply_error }}
      </div>
    </div>
  </div>
</template>
