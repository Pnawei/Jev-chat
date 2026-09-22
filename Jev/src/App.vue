<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  parseChat,
  analyzeMessages,
  type Message,
  type AnalysisData,
  type Dashboard,
} from './api'
import MessageBubble from './components/MessageBubble.vue'
import DashboardCard from './components/DashboardCard.vue'

const SAMPLE = `A：你晚上有空吗？
B：应该有吧，怎么了？
A：没什么，就问问。
B：哦哦。
A：那算了，你忙吧。`

const rawText = ref(SAMPLE)
const messages = ref<Message[]>([])
const senders = ref<string[]>([])
const otherSender = ref<string>('')

const parsing = ref(false)
const analyzing = ref(false)
const statusText = ref('')
const statusError = ref(false)

const statusMap = ref<Record<number, 'idle' | 'analyzing' | 'done' | 'error'>>({})
const analysisMap = ref<Record<number, AnalysisData>>({})
const errorMsgMap = ref<Record<number, string>>({})
const dashboard = ref<Dashboard | null>(null)

const hasParsed = computed(() => messages.value.length > 0)

async function onParse() {
  if (!rawText.value.trim()) {
    statusText.value = '请先粘贴聊天文本'
    statusError.value = true
    return
  }
  parsing.value = true
  statusError.value = false
  statusText.value = '解析中…'
  try {
    const res = await parseChat(rawText.value)
    messages.value = res.messages
    senders.value = res.senders
    otherSender.value = res.senders[1] ?? res.senders[0] ?? ''
    statusMap.value = {}
    analysisMap.value = {}
    errorMsgMap.value = {}
    dashboard.value = null
    statusText.value = `已解析 ${res.messages.length} 条消息，发送者：${res.senders.join('、')}`
  } catch (e: any) {
    statusText.value = `解析失败：${e?.response?.data?.detail || e.message}`
    statusError.value = true
  } finally {
    parsing.value = false
  }
}

async function onAnalyze() {
  if (!otherSender.value) {
    statusText.value = '请先选择"对方"发送者'
    statusError.value = true
    return
  }
  const otherMsgs = messages.value.filter((m) => m.sender === otherSender.value)
  if (otherMsgs.length === 0) {
    statusText.value = '该发送者没有消息可分析'
    statusError.value = true
    return
  }

  analyzing.value = true
  statusError.value = false
  dashboard.value = null
  otherMsgs.forEach((m) => {
    statusMap.value[m.id] = 'analyzing'
  })
  statusText.value = `正在分析 ${otherMsgs.length} 条对方消息…`

  try {
    const res = await analyzeMessages(
      messages.value.map((m) => ({ sender: m.sender, text: m.text })),
      otherSender.value
    )
    res.results.forEach((r, i) => {
      const msg = otherMsgs[i]
      if ('error' in r.analysis) {
        statusMap.value[msg.id] = 'error'
        errorMsgMap.value[msg.id] = r.analysis.error
      } else {
        statusMap.value[msg.id] = 'done'
        analysisMap.value[msg.id] = r.analysis
      }
    })
    dashboard.value = res.dashboard
    const okCount = res.results.filter((r) => !('error' in r.analysis)).length
    statusText.value = `分析完成：${okCount}/${otherMsgs.length} 条成功`
  } catch (e: any) {
    statusText.value = `分析失败：${e?.response?.data?.detail || e.message}`
    statusError.value = true
    otherMsgs.forEach((m) => {
      if (statusMap.value[m.id] === 'analyzing') statusMap.value[m.id] = 'error'
    })
  } finally {
    analyzing.value = false
  }
}

function isSelf(sender: string): boolean {
  return sender !== otherSender.value
}
</script>

<template>
  <header class="app-header">
    <h1>💬 微信聊天判断</h1>
    <span class="subtitle">理解对方信号 · 判断互动状态 · 决定下一步怎么聊</span>
  </header>

  <main class="app-main">
    <!-- 左侧：微信气泡列表（对方消息下方内联展示分析） -->
    <section class="panel panel-left">
      <div class="panel-header">聊天记录</div>
      <div class="message-list">
        <div v-if="!hasParsed" class="empty-state">
          在右侧粘贴聊天文本并点击「解析」<br />
          支持 <code>A：内容</code> 或 <code>A:内容</code> 格式
        </div>
        <MessageBubble
          v-for="m in messages"
          :key="m.id"
          :sender="m.sender"
          :text="m.text"
          :is-self="isSelf(m.sender)"
          :status="statusMap[m.id] || 'idle'"
          :analysis="analysisMap[m.id] || null"
          :error-message="errorMsgMap[m.id]"
        />
      </div>
    </section>

    <!-- 右侧：输入与控制 + 对话总览 -->
    <section class="panel panel-right input-panel">
      <div class="panel-header">输入与控制</div>
      <div class="chat-input-area">
        <textarea
          v-model="rawText"
          placeholder="格式示例：A：你好 B：你好呀"
          :disabled="parsing || analyzing"
        ></textarea>
        <div class="controls-row">
          <button
            class="btn btn-primary"
            :disabled="parsing || analyzing"
            @click="onParse"
          >
            {{ parsing ? '解析中…' : '🔍 解析' }}
          </button>
        </div>
        <div v-if="hasParsed" class="controls-row">
          <div class="sender-select">
            <label>对方：</label>
            <select v-model="otherSender" :disabled="analyzing">
              <option v-for="s in senders" :key="s" :value="s">{{ s }}</option>
            </select>
          </div>
          <button
            class="btn btn-secondary"
            :disabled="analyzing || !otherSender"
            @click="onAnalyze"
          >
            {{ analyzing ? '分析中…' : '🧠 分析对方消息' }}
          </button>
        </div>
        <div v-if="statusText" class="status-text" :class="{ error: statusError }">
          {{ statusText }}
        </div>
        <DashboardCard v-if="dashboard" :data="dashboard" class="dash-in-panel" />
      </div>
    </section>
  </main>
</template>
