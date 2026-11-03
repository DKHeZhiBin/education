import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { Button, Card, Chip, ServiceNotice } from '../../components/ui'
import { MathAnswerComposer } from '../../components/MathAnswerComposer'
import { MathInline, MathMarkdown } from '../../components/MathMarkdown'
import {
  createClientTurnId,
  getTutoringSession,
  streamTutoringTurn,
  type RuntimeDegradation,
  type TutorReply,
  type TutoringSession,
} from '../../services/tutoring'
import { LearningWorkflow, ProblemSnapshot, WorkspaceHeading } from './LearningWorkspace'
import { loadHintHistory, rememberHintReply, type HintHistory, type HintLevel } from './hintHistory'

const hintDefinitions: Array<{
  level: HintLevel
  title: string
  stage: NonNullable<TutorReply['hint_stage']>
  scope: string
}> = [
  { level: 1, title: '方向提示', stage: 'direction', scope: '指出可以从哪里开始，不给公式代入或答案。' },
  { level: 2, title: '关键关系', stage: 'key_relation', scope: '说明本轮要连接的条件与关系，保留计算任务。' },
  { level: 3, title: '局部步骤', stage: 'local_step', scope: '示范紧接着的一步，不提前展开后续解法。' },
  { level: 4, title: '完整讲解', stage: 'full_explanation', scope: '在规则允许后展示经过验证的完整步骤。' },
]

function savedStepsFor(sessionId: string) {
  try {
    const raw = window.sessionStorage.getItem(`learning-start:${sessionId}`)
    return raw ? (JSON.parse(raw) as { existingSteps?: string }).existingSteps?.trim() ?? '' : ''
  } catch {
    return ''
  }
}

function latestAssistantText(session: TutoringSession) {
  return [...session.messages].reverse().find(message => message.role === 'assistant')?.content ?? ''
}

/**
 * 从后端审计产物恢复分级提示历史。 / Restore level-specific hint history from backend audit artifacts.
 */
function restoreHintHistory(sessionId: string, session: TutoringSession): HintHistory {
  let restored = loadHintHistory(sessionId)
  for (const artifact of session.artifacts) {
    if (artifact.kind !== 'tutor_reply') continue
    const payload = artifact.payload as Partial<TutorReply>
    if (!payload.hint_level || payload.hint_level < 1 || payload.hint_level > 4) continue
    restored = rememberHintReply(sessionId, payload as TutorReply)
  }
  return restored
}

function HintCard({
  definition,
  currentLevel,
  reply,
  fallbackText,
  busy,
  canShowFullSolution,
  onExpand,
}: {
  definition: (typeof hintDefinitions)[number]
  currentLevel: number
  reply?: TutorReply
  fallbackText: string
  busy: boolean
  canShowFullSolution: boolean
  onExpand: (level: HintLevel) => void
}) {
  const expanded = definition.level <= currentLevel
  const verificationBlocked = definition.level === 4 && currentLevel === 3 && !canShowFullSolution
  const available = !verificationBlocked && definition.level === Math.min(currentLevel + 1, 4) && definition.level > currentLevel
  const content = reply?.text || (definition.level === currentLevel ? fallbackText : '')
  return <section className={`hint-level-card level-${definition.level} ${expanded ? 'expanded' : available ? 'available' : 'locked'}`}>
    <div className="hint-level-heading">
      <div><strong>{definition.level} · {definition.title}</strong><small>{definition.scope}</small></div>
      {expanded
        ? <span className="hint-level-state">已展开 ⌃</span>
        : available
          ? <button type="button" disabled={busy} onClick={() => onExpand(definition.level)}>{busy ? '正在生成…' : '展开 ＋'}</button>
          : <span className="hint-level-locked">{verificationBlocked ? '完整解法通过验证后可展开' : '完成上一层后可展开'}</span>}
    </div>
    {expanded && <div className="hint-level-content">
      <MathMarkdown source={content || '该级提示已在本会话中使用，可以在“一起思考”的对话记录中回看原文。'} />
      {reply?.solution_steps.length ? <ol>{reply.solution_steps.map(step => <li key={step}><MathMarkdown source={step} /></li>)}</ol> : null}
      {reply?.understanding_check ? <div className="hint-understanding-check"><span>回来自己写</span><MathMarkdown source={reply.understanding_check} /></div> : null}
    </div>}
  </section>
}

export function HintPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const navigationState = location.state as {
    reply?: TutorReply | null
    degradation?: RuntimeDegradation | null
  } | null
  const [session, setSession] = useState<TutoringSession | null>(null)
  const [history, setHistory] = useState<HintHistory>(() => sessionId ? loadHintHistory(sessionId) : {})
  const [degradation, setDegradation] = useState<RuntimeDegradation | null>(navigationState?.degradation ?? null)
  const [answer, setAnswer] = useState('')
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)
  const [pendingTurn, setPendingTurn] = useState<{
    message: string
    intent: string
    clientTurnId: string
    returnToCoach: boolean
  } | null>(null)

  useEffect(() => {
    if (!sessionId) {
      navigate('/learn/new', { replace: true })
      return
    }
    if (navigationState?.reply) setHistory(rememberHintReply(sessionId, navigationState.reply))
    void getTutoringSession(sessionId)
      .then(loadedSession => {
        setSession(loadedSession)
        setHistory(restoreHintHistory(sessionId, loadedSession))
      })
      .catch(cause => setError(cause instanceof Error ? cause.message : '无法读取学习会话'))
  }, [navigate, navigationState?.reply, sessionId])

  const savedSteps = useMemo(() => sessionId ? savedStepsFor(sessionId) : '', [sessionId])
  const currentLevel = Math.max(session?.hint_level ?? 0, navigationState?.reply?.hint_level ?? 0)
  const currentReply = currentLevel >= 1 && currentLevel <= 4 ? history[currentLevel as HintLevel] : navigationState?.reply ?? undefined
  const currentPrompt = currentReply?.understanding_check
    || (session ? latestAssistantText(session) : '')
    || '先选择你需要的提示层级，再带着这条连接继续写。'

  const submit = async (turn: NonNullable<typeof pendingTurn>) => {
    if (!sessionId) return
    setSending(true)
    setError('')
    setPendingTurn(turn)
    try {
      const result = await streamTutoringTurn(sessionId, turn.message, turn.intent, turn.clientTurnId)
      setSession(result.session)
      setHistory(rememberHintReply(sessionId, result.reply))
      const nextDegradation = result.degraded
        ? { code: result.degradation_code, reason: result.degradation_reason }
        : null
      setDegradation(nextDegradation)
      setPendingTurn(null)
      setAnswer('')
      if (turn.returnToCoach || result.session.status === 'completed') {
        navigate(result.session.status === 'completed'
          ? `/learn/${sessionId}/feedback`
          : `/learn/${sessionId}/coach`, {
          state: { reply: result.reply, degradation: result.degraded ? { code: result.degradation_code, reason: result.degradation_reason } : null },
        })
      } else {
        // 中文：同步替换浏览器历史状态，刷新后不再恢复上一轮已经结束的降级提示。
        // English: Replace history state so reloads do not restore a stale degradation notice.
        navigate(location.pathname, {
          replace: true,
          state: { reply: result.reply, degradation: nextDegradation },
        })
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '请求未完成，请使用同一请求重试')
    } finally {
      setSending(false)
    }
  }

  const expandLevel = (level: HintLevel) => {
    if (sending || pendingTurn || level !== Math.min(currentLevel + 1, 4)) return
    const fullExplanation = level === 4
    void submit({
      message: fullExplanation ? '我已经尝试过了，请展示经过验证的完整讲解' : `请给我第 ${level} 级提示，只展开${hintDefinitions[level - 1].title}`,
      intent: fullExplanation ? 'ask_solution' : 'ask_hint',
      clientTurnId: createClientTurnId(),
      returnToCoach: false,
    })
  }

  const continueWithAnswer = () => {
    const message = answer.trim()
    if (!message || sending || pendingTurn) return
    void submit({ message, intent: 'answer', clientTurnId: createClientTurnId(), returnToCoach: true })
  }

  if (!session) return <div className="page learning-workspace-page">
    <WorkspaceHeading title="给思路搭一座桥" description="正在读取本轮提示状态。" />
    {error ? <ServiceNotice title="分级提示暂时无法读取" message={error} tone="error" /> : <p className="tiny-muted">正在读取学习会话…</p>}
  </div>

  return <div className="page learning-workspace-page">
    <WorkspaceHeading title="给思路搭一座桥" description="提示按需展开 · 用提示不扣分，也不等于不会。找到连接，就回来自己写。" />
    <LearningWorkflow activeStep={5} completedThrough={4} />
    {degradation?.code && <ServiceNotice title="本轮提示使用降级结果" message={degradation.reason || '提示仍可使用，但知识库依据可能不完整。'} tone="warning" />}
    <div className="hint-workspace-grid">
      <aside className="workspace-column hint-context-column">
        <ProblemSnapshot question={session.question} />
        <Card className="saved-steps-card"><h2>我的步骤</h2><Chip tone="green">原记录已保存</Chip><MathMarkdown source={savedSteps || '还没有保存步骤，可以直接从提示后的下一步开始写。'} /><small>来自你的输入 · 草稿不会被提示覆盖</small></Card>
        <Card className="hint-current-node"><h2>● 当前节点</h2><strong>{currentReply?.understanding_check ? '补上当前连接' : '找到下一条关系'}</strong><MathMarkdown source={currentPrompt} /></Card>
      </aside>

      <Card className="hint-ladder-card">
        <h2>先展开需要的连接，不一次看全解</h2>
        <p className="hint-ladder-intro">当前已使用第 {currentLevel} 级提示。每次只开放紧接着的一层。</p>
        <div className="hint-level-list">
          {hintDefinitions.map(definition => <HintCard
            key={definition.level}
            definition={definition}
            currentLevel={currentLevel}
            reply={history[definition.level]}
            fallbackText={definition.level === currentLevel ? latestAssistantText(session) : ''}
            busy={sending || Boolean(pendingTurn)}
            canShowFullSolution={Boolean(currentReply?.can_show_full_solution || history[3]?.can_show_full_solution)}
            onExpand={expandLevel}
          />)}
        </div>
        <label className="field-label" htmlFor="hint-answer">试着补写：<MathInline source={currentReply?.understanding_check || '带着刚才的提示，写出紧接着的一步。'} /></label>
        <MathAnswerComposer id="hint-answer" rows={4} value={answer} disabled={sending || Boolean(pendingTurn)} onChange={setAnswer} />
        <div className="hint-answer-actions">
          <Button disabled={sending || Boolean(pendingTurn) || !answer.trim()} onClick={continueWithAnswer}>{sending ? '正在处理…' : '带着这条连接，继续写 →'}</Button>
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
        {pendingTurn && !sending && <div className="pending-turn" role="status"><div><strong>这次操作尚未确认送达</strong><span>{pendingTurn.message}</span></div><div className="pending-turn-actions"><Button onClick={() => void submit(pendingTurn)}>使用同一请求重试</Button></div></div>}
        <p className="hint-draft-note">你的草稿一直保留。只确认你提交的这一步，再继续后面的探索。</p>
      </Card>
    </div>
    <footer className="workspace-footer"><span>数知伙伴 · 不替你跳过思考，也不覆盖你的解法。</span><span>使用帮助 ↗</span></footer>
  </div>
}
