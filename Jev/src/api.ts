import axios from 'axios'

export interface Message {
  id: number
  sender: string
  text: string
}

export interface ParseResponse {
  messages: Message[]
  senders: string[]
}

export interface AnalysisResult {
  index: number
  sender: string
  text: string
  analysis: AnalysisData | { error: string }
}

export interface ProbItem {
  key: string
  label: string
  probability: number
}

export interface ChoiceDim {
  key: string
  label: string
  confidence: number
  probabilities?: ProbItem[]
}

export interface EvidenceItem {
  type: string
  label: string
  text: string
  index?: number
}

export type ScoreKey =
  | 'initiative'
  | 'engagement'
  | 'warmth'
  | 'intimacy'
  | 'flirtiness'
  | 'vulnerability'
  | 'attention_toward_user'

export interface AnalysisData {
  intent: ChoiceDim
  motivation: ChoiceDim
  relationship_signal: ChoiceDim
  conversation_direction: ChoiceDim
  emotion: ChoiceDim
  scores: Record<ScoreKey, { value: number | null }>
  evidence: EvidenceItem[]
  confidence: number
  /** 针对该条消息的回复建议（DeepSeek 批量生成后分发） */
  suggested_replies?: string[]
}

export interface ScoreTrend {
  avg: number | null
  first: number | null
  last: number | null
  delta: number
  trend: 'rising' | 'stable' | 'falling'
}

export interface Dashboard {
  scores: Record<ScoreKey, ScoreTrend>
  direction_counts: Record<string, number>
  motivation_counts: Record<string, number>
  overall_direction: { key: string; label: string }
  dominant_motivation: { key: string; label: string }
  evidence: EvidenceItem[]
  strategy_hint: string
  reply_strategy: string | null
  reply_suggestions: string[]
  reply_error: string | null
}

export interface AnalyzeResponse {
  results: AnalysisResult[]
  dashboard: Dashboard | null
}

/** 前端展示用的指标中文名 */
export const SCORE_LABELS: Record<ScoreKey, string> = {
  initiative: '主动性',
  engagement: '投入度',
  warmth: '温度',
  intimacy: '亲密程度',
  flirtiness: '暧昧程度',
  vulnerability: '暴露程度',
  attention_toward_user: '对你的关注',
}

const http = axios.create({ baseURL: '/api' })

export async function parseChat(text: string): Promise<ParseResponse> {
  const { data } = await http.post<ParseResponse>('/parse', { text })
  return data
}

export async function analyzeMessages(
  messages: { sender: string; text: string }[],
  otherSender: string
): Promise<AnalyzeResponse> {
  const { data } = await http.post<AnalyzeResponse>('/analyze', {
    messages,
    other_sender: otherSender,
  })
  return data
}
