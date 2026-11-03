import type { TutorSourceReference, TutoringSession } from '../../services/tutoring'

export interface ReviewStep {
  title: string
  result: string
  justification: string
  badge: string
  emphasis: 'normal' | 'breakthrough' | 'verified'
}

export interface SessionReview {
  answer: string
  studentThought: string
  breakthroughTitle: string
  breakthroughDescription: string
  breakthroughReason: string
  methodName: string
  methodSummary: string
  steps: ReviewStep[]
  sources: TutorSourceReference[]
  verification: { passed: boolean; coverage: string; verifier: string; evidence: string }
}

function text(value: unknown) {
  return typeof value === 'string' ? value.trim() : ''
}

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function objects(value: unknown) {
  return Array.isArray(value) ? value.map(object).filter(item => Object.keys(item).length) : []
}

function strings(value: unknown) {
  return Array.isArray(value) ? value.map(text).filter(Boolean) : []
}

function bigrams(value: string) {
  const normalized = value.replace(/[\s，。；：、,.!?！？()（）|→=+−\-]/g, '')
  return new Set(Array.from({ length: Math.max(0, normalized.length - 1) }, (_, index) => normalized.slice(index, index + 2)))
}

function overlapScore(left: string, right: string) {
  const expected = bigrams(left)
  const actual = bigrams(right)
  return [...expected].filter(token => actual.has(token)).length
}

function latestPayload(session: TutoringSession, kind: string) {
  return [...(session.artifacts ?? [])].reverse().find(artifact => artifact.kind === kind)?.payload ?? {}
}

function savedStartingSteps(sessionId: string) {
  try {
    const raw = window.sessionStorage.getItem(`learning-start:${sessionId}`)
    return raw ? text((JSON.parse(raw) as { existingSteps?: string }).existingSteps) : ''
  } catch {
    return ''
  }
}

function collectSources(session: TutoringSession) {
  const sources = (session.artifacts ?? []).flatMap(artifact => {
    if (artifact.kind !== 'tutor_reply') return []
    return Array.isArray(artifact.payload.sources) ? artifact.payload.sources : []
  }).map(source => object(source) as unknown as TutorSourceReference)
  const unique = new Map<string, TutorSourceReference>()
  sources.forEach(source => {
    if (!source.document_id || !source.title) return
    unique.set(`${source.document_id}:${source.chunk_id ?? ''}:${source.locator ?? ''}`, source)
  })
  return [...unique.values()].slice(0, 6)
}

export function buildSessionReview(session: TutoringSession): SessionReview {
  const solution = latestPayload(session, 'solution_plan')
  const verificationPayload = latestPayload(session, 'verification_report')
  const methods = objects(solution.methods)
  const recommendedId = text(solution.recommended_method_id)
  const method = methods.find(item => text(item.id) === recommendedId) ?? methods[0] ?? {}
  const breakthroughs = objects(solution.key_breakthroughs)
  const breakthrough = breakthroughs[0] ?? {}
  const structuredSteps = objects(method.steps)
  const legacySteps = strings(solution.steps)
  const answer = text(method.answer) || text(solution.answer) || '答案已写入完整解法'
  const studentThought = session.record?.learner_answer
    || savedStartingSteps(session.id)
    || session.messages.filter((message, index) => index > 0 && message.role === 'student').map(message => message.content).join('\n')
    || '本轮没有记录到可复盘的独立步骤。'
  const breakthroughTitle = text(breakthrough.title) || '找到已知条件与目标之间的关键连接'
  const breakthroughDescription = text(breakthrough.description) || session.record?.correct_approach || '沿着已验证的解题路线，把当前条件逐步连接到求解目标。'
  const breakthroughReason = text(breakthrough.why_it_matters) || '这一步决定了后续计算应使用哪一个数学关系。'

  let steps: ReviewStep[] = structuredSteps.map((step, index) => ({
    title: text(step.statement) || `步骤 ${index + 1}`,
    result: text(step.result),
    justification: text(step.justification),
    badge: index === 0 ? '起点' : index === structuredSteps.length - 1 ? '已检验' : '继续推导',
    emphasis: index === structuredSteps.length - 1 ? 'verified' : 'normal',
  }))
  if (!steps.length) steps = legacySteps.map((step, index) => ({
    title: `步骤 ${index + 1}`,
    result: step,
    justification: '',
    badge: index === legacySteps.length - 1 ? '已检验' : '继续推导',
    emphasis: index === legacySteps.length - 1 ? 'verified' : 'normal',
  }))
  if (!steps.length && session.record?.correct_approach) steps = session.record.correct_approach.split('；').filter(Boolean).map((step, index, all) => ({
    title: `步骤 ${index + 1}`,
    result: step,
    justification: '',
    badge: index === all.length - 1 ? '学习记录' : '继续推导',
    emphasis: index === all.length - 1 ? 'verified' : 'normal',
  }))
  const breakthroughText = `${text(breakthrough.title)}${text(breakthrough.description)}`
  const breakthroughIndex = steps.reduce((best, step, index) => {
    const score = overlapScore(breakthroughText, `${step.title}${step.result}${step.justification}`)
    return score > best.score ? { index, score } : best
  }, { index: 0, score: -1 }).index
  if (steps.length) steps[breakthroughIndex].emphasis = 'breakthrough'

  const coverage = text(verificationPayload.coverage)
    || text(verificationPayload.verification_coverage)
    || (verificationPayload.passed === true ? '已通过本题配置的确定性验证' : '验证覆盖信息未返回')
  const evidence = strings(verificationPayload.evidence).join('；')
    || text(verificationPayload.evidence)
    || strings(verificationPayload.checks).join('；')
  return {
    answer,
    studentThought,
    breakthroughTitle,
    breakthroughDescription,
    breakthroughReason,
    methodName: text(method.name) || '推荐解法',
    methodSummary: text(method.strategy_summary) || session.record?.correct_approach || '',
    steps,
    sources: collectSources(session),
    verification: {
      passed: verificationPayload.passed === true,
      coverage,
      verifier: text(verificationPayload.verifier_type) || '数学验证链路',
      evidence,
    },
  }
}
