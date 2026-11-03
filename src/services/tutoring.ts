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
  hint_stage: 'direction' | 'key_relation' | 'local_step' | 'full_explanation' | null
  understanding_check: string | null
  solution_steps: string[]
  can_show_full_solution: boolean
  sources: TutorSourceReference[]
  guidance_state: 'exploring' | 'uncertain' | 'blocked' | 'remediating' | 'guided' | 'verifying' | 'reflecting' | 'transfer_test' | 'completed' | null
  current_goal_id: string | null
  current_goal_title: string | null
  current_goal_ordinal: number | null
  completed_goal_count: number
  total_goal_count: number
  obstacle_type: 'none' | 'knowledge_gap' | 'strategy_selection' | 'expression_transformation' | 'execution_error' | 'alternative_valid_path' | 'uncertain' | null
  attempt_verification: 'valid' | 'invalid' | 'unverified' | null
  next_action: string | null
  confidence: number
}

export interface Message {
  id: string
  role: 'student' | 'assistant'
  content: string
  created_at: string
}

export interface AgentArtifact {
  run_id: string
  schema_version: string
  agent: string
  kind: string
  payload: Record<string, unknown>
  status: string
  duration_ms: number
  confidence: number
  created_at: string
}

export interface LearningRecord {
  id: string
  date: string
  subject: string
  grade: string
  question: string
  learner_answer: string
  error_category: string
  error_reason: string
  correct_approach: string
  knowledge_tags: string[]
  knowledge_points: Array<{
    code: string
    name: string
    relation_type: string
    mistake_detected: boolean
    error_category: string
    error_reason: string
    hint_level: number
    effective_attempt_count: number
    mastery: string
    evidence: string
  }>
  difficulty: number
  mastery: string
  hint_level: number
  attempt_count: number
  review_count: number
}

export interface TutoringSession {
  id: string
  version: number
  student_user_id: string
  knowledge_problem_id: string | null
  llm_model_id: string | null
  profile: { grade: string; subject: string }
  question: string
  status: TutoringStatus
  hint_level: number
  attempts: number
  messages: Message[]
  artifacts: AgentArtifact[]
  record: LearningRecord | null
  created_at: string
  updated_at: string
}

export interface TutoringSessionSummary {
  id: string
  question: string
  status: TutoringStatus
  llm_model_id: string | null
  updated_at: string
}

export type ContentIssueType =
  | 'incorrect_answer'
  | 'incorrect_question'
  | 'incorrect_hint'
  | 'ambiguous_content'
  | 'answer_conflict'
  | 'other'

export interface ContentIssueReport {
  id: string
  problem_id: string
  session_id: string | null
  issue_type: ContentIssueType
  description: string
  status: 'received' | 'revalidation_queued' | 'validating' | 'resolved' | 'dismissed'
  maintenance_job_id: string | null
  created_at: string
  updated_at: string
}

export interface ParentReport {
  sample_scope: {
    status: 'available' | 'no_samples'
    scope_type: 'all_completed_records'
    completed_record_count: number
    knowledge_evidence_count: number
    first_record_date: string | null
    last_record_date: string | null
    subjects: string[]
    grades: string[]
    generated_at: string
  }
  overview: { completed_questions: number; subjects: string[]; mistakes_to_review: number }
  knowledge_points: string[]
  knowledge_summary: Array<{
    code: string
    name: string
    evidence_count: number
    mistake_count: number
    effective_attempt_count: number
    highest_hint_level: number
    mastered_evidence_count: number
    latest_mastery: string
    latest_record_date: string
  }>
  weak_points: string[]
  recommendations: string[]
  records: LearningRecord[]
  note: string
}

export type DegradationCode = 'run_timeout' | 'llm_provider_unavailable' | 'knowledge_retrieval_degraded'

export interface RuntimeDegradation {
  code: DegradationCode | null
  reason: string | null
}

export interface SessionResponse {
  session: TutoringSession
  reply: TutorReply
  degraded: boolean
  degradation_code: DegradationCode | null
  degradation_reason: string | null
}

export type TutoringStreamEvent =
  | {
      type: 'turn.started'
      client_turn_id: string
      session_id: string
    }
  | {
      type: 'turn.progress'
      client_turn_id: string
      stage: string
      message: string
    }
  | {
      type: 'reply.started'
      client_turn_id: string
    }
  | {
      type: 'reply.delta'
      client_turn_id: string
      delta: string
    }
  | {
      type: 'session.completed'
      client_turn_id: string
      session_id: string
      status: 'completed'
      next_route: string
    }
  | {
      type: 'turn.completed'
      client_turn_id: string
      result: SessionResponse
    }
  | {
      type: 'turn.error'
      client_turn_id: string
      status: number
      code: string
      message: string
      retryable: boolean
      retry_after_seconds?: number
    }

export interface ReadinessCheck {
  status: 'ready' | 'not_ready' | 'disabled'
  required: boolean
  latency_ms: number
  detail: string
}

export interface LearningReadiness {
  status: 'ready' | 'not_ready'
  degraded: boolean
  checks: {
    mysql: ReadinessCheck
    redis: ReadinessCheck
    llm: ReadinessCheck
    rag: ReadinessCheck
    ocr: ReadinessCheck
    asr: ReadinessCheck
    tts: ReadinessCheck
  }
}

export class TutoringHttpError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string | null = null,
    readonly retryable = false,
    readonly retryAfterSeconds: number | null = null,
  ) {
    super(message)
    this.name = 'TutoringHttpError'
  }
}

export function hasConfirmedHttpResponse(error: unknown): error is TutoringHttpError {
  return error instanceof TutoringHttpError
}

export function isSessionConflictError(error: unknown): error is TutoringHttpError {
  return error instanceof TutoringHttpError && error.status === 409 && (
    error.code === 'session_busy' || error.code === 'session_version_conflict'
  )
}

export interface LLMModelOption {
  id: string
  provider: string
  model: string
  display_name: string
  available: boolean
  is_default: boolean
}

export interface LLMModelCatalog {
  models: LLMModelOption[]
  default_model_id: string | null
}

export type ProblemImageStatus = 'pending' | 'processing' | 'ready' | 'failed'
export type FormulaValidationStatus = 'not_checked' | 'valid' | 'needs_review' | 'invalid'

export interface FormulaStructureIssue {
  code: string
  severity: 'warning' | 'error'
  formula_index: number | null
  message: string
}

export interface ProblemImageUpload {
  id: string
  status: ProblemImageStatus
  original_filename: string
  mime_type: 'image/jpeg' | 'image/png' | 'image/webp'
  size_bytes: number
  extracted_text: string | null
  error_code: string | null
  ocr_provider: string | null
  ocr_model: string | null
  ocr_confidence: number | null
  recognized_formulas: string[]
  formula_validation_status: FormulaValidationStatus
  formula_validation_issues: FormulaStructureIssue[]
  student_confirmed_at: string | null
  created_at: string
  updated_at: string
  expires_at: string
  status_message: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authorizedFetch(path, init)
  if (!response.ok) {
    if (response.status === 401) clearAccessToken()
    const body = await response.json().catch(() => null) as {
      code?: string
      message?: string
      retryable?: boolean
      retry_after_seconds?: number
      detail?: string | { message?: string }
    } | null
    const legacyDetail = body?.detail
    const legacyMessage = typeof legacyDetail === 'string'
      ? legacyDetail
      : legacyDetail?.message
    throw new TutoringHttpError(
      body?.message ?? legacyMessage ?? '学习服务暂时不可用，请稍后重试',
      response.status,
      body?.code ?? null,
      body?.retryable ?? false,
      body?.retry_after_seconds ?? null,
    )
  }
  return response.json() as Promise<T>
}

export function createTutoringSession(
  question: string,
  llmModelId?: string,
) {
  return request<SessionResponse>('/tutoring/sessions', {
    method: 'POST',
    body: JSON.stringify({
      question,
      llm_model_id: llmModelId || null,
    }),
  })
}

/** 中文：从知识点中的已发布例题生成一题相似练习并创建会话。 English: Generates similar practice from a published knowledge example and creates a session. */
export function createKnowledgeExamplePractice(input: {
  knowledgePointCode: string
  contentKey: string
  difficulty?: 'easy' | 'medium' | 'hard' | 'easier' | 'same' | 'harder'
  structureLevel?: 'S1' | 'S2' | 'S3' | 'S4'
  reasoningLevel?: 'M1' | 'M2' | 'M3' | 'M4'
  teachingGoal?: 'T1' | 'T2' | 'T3' | 'T4'
  llmModelId?: string
  clientRequestId?: string
}) {
  return request<SessionResponse>('/tutoring/knowledge-example-practice', {
    method: 'POST',
    body: JSON.stringify({
      knowledge_point_code: input.knowledgePointCode,
      content_key: input.contentKey,
      difficulty: input.difficulty ?? 'medium',
      ...(input.structureLevel ? { structure_level: input.structureLevel } : {}),
      ...(input.reasoningLevel ? { reasoning_level: input.reasoningLevel } : {}),
      ...(input.teachingGoal ? { teaching_goal: input.teachingGoal } : {}),
      llm_model_id: input.llmModelId ?? null,
      client_request_id: input.clientRequestId ?? createClientTurnId(),
    }),
  })
}

export function getLLMModels() {
  return request<LLMModelCatalog>('/llm/models')
}

export function uploadProblemImage(file: File) {
  const body = new FormData()
  body.append('file', file)
  return request<ProblemImageUpload>('/tutoring/problem-images', {
    method: 'POST',
    body,
  })
}

export function getProblemImageUpload(assetId: string) {
  return request<ProblemImageUpload>(`/tutoring/problem-images/${assetId}`)
}

export function confirmProblemImageOCR(assetId: string, text: string, formulasLatex: string[]) {
  return request<ProblemImageUpload>(`/tutoring/problem-images/${assetId}/confirmation`, {
    method: 'PUT',
    body: JSON.stringify({ text, formulas_latex: formulasLatex }),
  })
}

export async function getLearningReadiness() {
  const response = await authorizedFetch('/health/ready')
  return response.json() as Promise<LearningReadiness>
}

export function getTutoringSession(sessionId: string) {
  return request<TutoringSession>(`/tutoring/sessions/${sessionId}`)
}

export function listTutoringSessions() {
  return request<TutoringSessionSummary[]>('/tutoring/sessions')
}

export function reportTutoringContentIssue(
  sessionId: string,
  input: {
    problem_id?: string | null
    issue_type: ContentIssueType
    description: string
    client_report_id: string
  },
) {
  return request<ContentIssueReport>(`/tutoring/sessions/${sessionId}/content-issues`, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function createClientTurnId(): string {
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

export async function streamTutoringTurn(
  sessionId: string,
  message: string,
  intent = 'answer',
  clientTurnId = createClientTurnId(),
  onEvent?: (event: TutoringStreamEvent) => void,
): Promise<SessionResponse> {
  const response = await authorizedFetch(`/tutoring/sessions/${sessionId}/turns/stream`, {
    method: 'POST',
    headers: { Accept: 'text/event-stream' },
    body: JSON.stringify({ message, intent, client_turn_id: clientTurnId }),
  })
  if (!response.ok) {
    if (response.status === 401) clearAccessToken()
    const body = await response.json().catch(() => null) as {
      code?: string
      message?: string
      retryable?: boolean
      retry_after_seconds?: number
      detail?: string | { message?: string }
    } | null
    const legacyDetail = body?.detail
    throw new TutoringHttpError(
      body?.message
        ?? (typeof legacyDetail === 'string' ? legacyDetail : legacyDetail?.message)
        ?? '学习服务暂时不可用，请稍后重试',
      response.status,
      body?.code ?? null,
      body?.retryable ?? false,
      body?.retry_after_seconds ?? null,
    )
  }
  if (!response.body) {
    throw new TutoringHttpError('浏览器未建立流式连接，请重试', 0, 'sse_stream_unavailable', true)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let completed: SessionResponse | null = null

  const processBlock = (block: string) => {
    const lines = block.split(/\r?\n/)
    const eventType = lines
      .find(line => line.startsWith('event:'))
      ?.slice(6)
      .trim()
    const data = lines
      .filter(line => line.startsWith('data:'))
      .map(line => line.slice(5).trimStart())
      .join('\n')
    if (!data) return
    const payload = JSON.parse(data) as Record<string, unknown>
    const type = typeof payload.type === 'string' ? payload.type : eventType
    if (!type) return
    const event = { ...payload, type } as TutoringStreamEvent
    onEvent?.(event)
    if (event.type === 'turn.completed') completed = event.result
    if (event.type === 'turn.error') {
      throw new TutoringHttpError(
        event.message,
        event.status,
        event.code,
        event.retryable,
        event.retry_after_seconds ?? null,
      )
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() ?? ''
    blocks.forEach(processBlock)
    if (done) break
  }
  if (buffer.trim()) processBlock(buffer)
  if (!completed) {
    throw new TutoringHttpError('流式回复中断，请使用同一请求重试', 0, 'sse_stream_interrupted', true)
  }
  return completed
}

export function listLearningRecords() {
  return request<LearningRecord[]>('/tutoring/learning-records')
}

export function getParentReport() {
  return request<ParentReport>('/tutoring/parent-report')
}
