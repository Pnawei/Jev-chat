<script setup lang="ts">
import { SCORE_LABELS, type AnalysisData, type ChoiceDim, type ScoreKey } from '../api'

const props = defineProps<{
  data: AnalysisData
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

const DIMS: { title: string; dim: ChoiceDim }[] = [
  { title: '意图', dim: props.data.intent },
  { title: '动机', dim: props.data.motivation },
  { title: '关系', dim: props.data.relationship_signal },
  { title: '方向', dim: props.data.conversation_direction },
]

function pct(v: number | null): number {
  return v == null ? 0 : Math.max(v, 2)
}

function fillClass(v: number | null): string {
  if (v == null) return 'fill-weak'
  if (v >= 60) return 'fill-strong'
  if (v >= 30) return 'fill-mid'
  return 'fill-weak'
}
</script>

<template>
  <div class="analysis-card compact" @click.stop>
    <!-- 四个判断维度：top 选项 + 概率分布 -->
    <div v-for="d in DIMS" :key="d.title" class="dim-row">
      <span class="label">{{ d.title }}</span>
      <template v-if="d.dim.probabilities && d.dim.probabilities.length">
        <span class="prob-top">{{ d.dim.probabilities[0].label }}</span>
        <span class="prob-pct">{{ Math.round(d.dim.probabilities[0].probability * 100) }}%</span>
        <span
          v-for="p in d.dim.probabilities.slice(1)"
          :key="p.key"
          class="prob-alt"
        >{{ p.label }} {{ Math.round(p.probability * 100) }}%</span>
      </template>
      <template v-else>
        <span class="prob-top">{{ d.dim.label }}</span>
      </template>
    </div>

    <!-- 七个指标 -->
    <div class="score-grid">
      <div v-for="key in SCORE_ORDER" :key="key" class="score-row">
        <span class="score-name">{{ SCORE_LABELS[key] }}</span>
        <div class="intent-bar-track score-track">
          <div
            class="intent-bar-fill"
            :style="{ width: pct(props.data.scores[key]?.value) + '%' }"
            :class="fillClass(props.data.scores[key]?.value)"
          ></div>
        </div>
        <span class="score-val">{{ props.data.scores[key]?.value ?? '-' }}</span>
      </div>
    </div>

    <!-- 证据 -->
    <div v-if="props.data.evidence.length" class="evidence-list">
      <div v-for="(ev, i) in props.data.evidence" :key="i" class="evidence-item">
        <span class="evidence-type">{{ ev.label }}</span>
        <span class="evidence-text">「{{ ev.text }}」</span>
      </div>
    </div>

    <!-- 回复建议 -->
    <div
      v-if="props.data.suggested_replies && props.data.suggested_replies.length"
      class="reply-section"
    >
      <div class="section-title">💬 你可以这样回</div>
      <div v-for="(reply, i) in props.data.suggested_replies" :key="i" class="reply-item">
        {{ reply }}
      </div>
    </div>
  </div>
</template>
