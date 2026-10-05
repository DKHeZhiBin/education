import { authorizedFetch, clearAccessToken } from './auth'

export type TutoringStatus = 'collecting' | 'clarifying' | 'diagnosing' | 'hinting' | 'checking_attempt' | 'explaining' | 'completed'

export interface TutorSourceReference {
  source_reference_id: string | null
  document_id: string
  chunk_id: string | null
  title: string
  version: string | null
  source_url: string | null
  locator: string | null
  supports: Array<'concept' | 'principle' | 'example_pattern' | 'worked_example' | 'error_pattern' | 'hint' | 'source_fact'>
}

export interface TutorReply {
  action: 'clarify' | 'diagnose' | 'hint' | 'check_attempt' | 'explain' | 'summarize'
  text: string
  hint_level: number | null
  understanding_check: string | null
  solution_steps: string[]
  sources: TutorSourceReference[]
  confidence: number
}

export interface Message {
  id: string
  role: 'student' | 'assistant'
  content: string
  created_at: string
}

export interface LearningRecord {
  id: string
  date: string
  subject: string
  grade: string
  question: string
  learner_answer: string
  error_reason: string
  correct_approach: string
  knowledge_tags: string[]
  difficulty: number
  mastery: string
  review_count: number
}

export interface TutoringSession {
  id: string
  version: number
  student_user_id: string
  profile: { grade: string; subject: string }
  question: string
  status: TutoringStatus
  hint_level: number
  attempts: number
  messages: Message[]
  record: LearningRecord | null
  created_at: string
  updated_at: string
}

export interface ParentReport {
  overview: { completed_questions: number; subjects: string[]; mistakes_to_review: number }
  knowledge_points: string[]
  weak_points: string[]
  recommendations: string[]
  records: LearningRecord[]
  note: string
}

interface SessionResponse {
  session: TutoringSession
  reply: TutorReply
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authorizedFetch(path, init)
  if (!response.ok) {
    if (response.status === 401) clearAccessToken()
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? '学习服务暂时不可用，请稍后重试')
  }
  return response.json() as Promise<T>
}

export function createTutoringSession(question: string, grade = '初中') {
  return request<SessionResponse>('/tutoring/sessions', {
    method: 'POST',
    body: JSON.stringify({ question, grade, subject: '数学' }),
  })
}

export function getTutoringSession(sessionId: string) {
  return request<TutoringSession>(`/tutoring/sessions/${sessionId}`)
}

export function createClientTurnId() {
  return globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export function sendTutoringTurn(
  sessionId: string,
  message: string,
  intent = 'answer',
  clientTurnId = createClientTurnId(),
) {
  return request<SessionResponse>(`/tutoring/sessions/${sessionId}/turns`, {
    method: 'POST',
    body: JSON.stringify({ message, intent, client_turn_id: clientTurnId }),
  })
}

export function listLearningRecords() {
  return request<LearningRecord[]>('/tutoring/learning-records')
}

export function getParentReport() {
  return request<ParentReport>('/tutoring/parent-report')
}
