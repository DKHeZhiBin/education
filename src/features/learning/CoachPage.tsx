import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { Button, Card, Chip, ServiceNotice } from '../../components/ui'
import { MathAnswerComposer } from '../../components/MathAnswerComposer'
import { MathMarkdown } from '../../components/MathMarkdown'
import { ContentIssueReporter } from './ContentIssueReporter'
import { LearningWorkflow, ProblemSnapshot, WorkspaceHeading } from './LearningWorkspace'
import { rememberHintReply } from './hintHistory'
import {
  createClientTurnId,
  getTutoringSession,
  hasConfirmedHttpResponse,
  isSessionConflictError,
  streamTutoringTurn,
  TutoringHttpError,
  type RuntimeDegradation,
  type TutorReply,
  type TutoringSession,
} from '../../services/tutoring'

const sourceKindLabel: Record<TutorReply['sources'][number]['supports'][number], string> = {
  concept: '概念依据',
  principle: '定理与公式',
  example_pattern: '例题结构',
  worked_example: '完整例题',
  error_pattern: '易错分析',
  hint: '提示依据',
  source_fact: '教材结论',
}

const hintLevelLabel = ['尚未使用提示', '方向提示', '关键关系', '局部步骤', '完整讲解']

const guidanceStateLabel: Record<NonNullable<TutorReply['guidance_state']>, string> = {
  exploring: '独立探索',
  uncertain: '确认卡点',
  blocked: '修正局部错误',
  remediating: '补充前置知识',
  guided: '按提示推进',
  verifying: '校验当前步骤',
  reflecting: '提炼解题方法',
  transfer_test: '独立迁移检验',
  completed: '本轮已完成',
}

const obstacleLabel: Record<NonNullable<TutorReply['obstacle_type']>, string> = {
  none: '当前没有已确认障碍',
  knowledge_gap: '前置知识缺口',
  strategy_selection: '方法选择困难',
  expression_transformation: '表达与变形困难',
  execution_error: '局部执行错误',
  alternative_valid_path: '正在采用另一条成立路径',
  uncertain: '需要更多本轮证据',
}

const actionLabel: Record<TutorReply['action'], string> = {
  clarify: '补充题目信息',
  diagnose: '诊断当前卡点',
  hint: '提供分级提示',
  check_attempt: '检查本轮尝试',
  explain: '讲解解题过程',
  summarize: '总结本次学习',
}

const statusAction: Record<TutoringSession['status'], TutorReply['action']> = {
  collecting: 'clarify',
  clarifying: 'clarify',
  diagnosing: 'diagnose',
  hinting: 'hint',
  checking_attempt: 'check_attempt',
  explaining: 'explain',
  completed: 'summarize',
}

const nextStepByAction: Record<TutorReply['action'], string> = {
  clarify: '补充题目中缺少的条件、图形信息或符号含义。',
  diagnose: '写下你准备进行的第一步，或说明最不确定的位置。',
  hint: '根据当前提示完成紧接着的一步，再把结果发给教学 Agent。',
  check_attempt: '检查刚才的步骤，并说明所依据的公式或关系。',
  explain: '复述完整讲解中的关键关系，确认自己能够独立使用。',
  summarize: '回顾本题知识点，或者开始下一道题。',
}

function degradationCopy(degradation: RuntimeDegradation | null) {
  if (!degradation?.code) return null
  if (degradation.code === 'knowledge_retrieval_degraded') return {
    title: '知识检索已降级',
    message: degradation.reason || '本轮已回退到基础教学链路，不展示题库引用。',
    tone: 'warning' as const,
  }
  if (degradation.code === 'llm_provider_unavailable') return {
    title: '辅导模型当前不可用',
    message: degradation.reason || '本轮使用了安全降级回复，你的作答仍然保留。',
    tone: 'warning' as const,
  }
  return {
    title: '本轮处理时间较长',
    message: degradation.reason || '本轮超过时间预算，可以保留作答后重试。',
    tone: 'error' as const,
  }
}

export function CoachPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const navigationState = location.state as {
    reply?: TutorReply
    degradation?: RuntimeDegradation | null
  } | null
  const navigationReply = navigationState?.reply ?? null
  const [session, setSession] = useState<TutoringSession | null>(null)
  const [answer, setAnswer] = useState('')
  const [lastReply, setLastReply] = useState<TutorReply | null>(navigationReply)
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const [streamingStatus, setStreamingStatus] = useState('')
  const [syncing, setSyncing] = useState(false)
  const [degradation, setDegradation] = useState<RuntimeDegradation | null>(
    navigationState?.degradation ?? null,
  )
  const [serviceFailure, setServiceFailure] = useState<{
    title: string
    message: string
    tone: 'warning' | 'error'
  } | null>(null)
  const [pendingTurn, setPendingTurn] = useState<{
    message: string
    intent: string
    clientTurnId: string
  } | null>(null)

  useEffect(() => {
    if (!sessionId) {
      navigate('/learn/new', { replace: true })
      return
    }
    getTutoringSession(sessionId).then(loadedSession => {
      setSession(loadedSession)
      const latestReply = [...loadedSession.artifacts].reverse().find(item => item.kind === 'tutor_reply')?.payload
      if (latestReply) setLastReply(latestReply as unknown as TutorReply)
    }).catch(cause => setError(cause instanceof Error ? cause.message : '无法读取学习会话'))
  }, [navigate, sessionId])

  useEffect(() => {
    if (sessionId && lastReply) rememberHintReply(sessionId, lastReply)
  }, [lastReply, sessionId])

  const refreshSession = async (
    conflict?: TutoringHttpError,
  ) => {
    if (!sessionId) return
    setSyncing(true)
    if (conflict) setError(conflict.message)
    const waitSeconds = conflict?.retryAfterSeconds ?? 0
    if (waitSeconds > 0) {
      await new Promise(resolve => window.setTimeout(resolve, waitSeconds * 1000))
    }
    try {
      const latest = await getTutoringSession(sessionId)
      setSession(latest)
      setLastReply(null)
      if (conflict) {
        setError(conflict.code === 'session_busy'
          ? '最新会话已同步。请确认后使用同一请求重试。'
          : '已加载其他请求更新后的进度。请使用同一请求继续重试。')
      } else {
        setError('最新会话已同步，可以继续重试。')
      }
    } catch (cause) {
      setError(cause instanceof Error ? `重新获取会话失败：${cause.message}` : '重新获取会话失败，请再试一次')
    } finally {
      setSyncing(false)
    }
  }

  const submitTurn = async (turn: {
    message: string
    intent: string
    clientTurnId: string
  }) => {
    if (!sessionId) return
    setSending(true)
    setError('')
    setStreamingText('')
    setStreamingStatus('正在连接教学 Agent…')
    setPendingTurn(turn)
    try {
      const result = await streamTutoringTurn(
        sessionId,
        turn.message,
        turn.intent,
        turn.clientTurnId,
        event => {
          if (event.type === 'turn.started') setStreamingStatus('已收到作答，正在分析…')
          if (event.type === 'turn.progress') setStreamingStatus(event.message)
          if (event.type === 'reply.started') setStreamingStatus('正在组织回复…')
          if (event.type === 'reply.delta') {
            setStreamingStatus('')
            setStreamingText(current => current + event.delta)
          }
          if (event.type === 'session.completed') {
            setStreamingStatus('本题已完成，正在进入思路复盘…')
          }
        },
      )
      setSession(result.session)
      setLastReply(result.reply)
      setServiceFailure(null)
      if (result.degraded) {
        setDegradation({
          code: result.degradation_code,
          reason: result.degradation_reason,
        })
      }
      setPendingTurn(null)
      setAnswer('')
      setStreamingText('')
      setStreamingStatus('')
      if (result.session.id !== sessionId) {
        navigate(`/learn/${result.session.id}/coach`, {
          replace: true,
          state: {
            reply: result.reply,
            degradation: result.degraded ? {
              code: result.degradation_code,
              reason: result.degradation_reason,
            } : null,
          },
        })
      } else if (result.session.status === 'completed') {
        navigate(`/learn/${sessionId}/feedback`)
      }
    } catch (cause) {
      setStreamingStatus('')
      setError(cause instanceof Error ? cause.message : '消息发送失败')
      if (cause instanceof TutoringHttpError && cause.code === 'llm_model_unavailable') {
        setServiceFailure({
          title: '所选辅导模型当前不可用',
          message: `${cause.message}。作答内容已保留，请稍后重试。`,
          tone: 'warning',
        })
      } else if (!isSessionConflictError(cause)) {
        setServiceFailure({
          title: '学习服务暂时不可用',
          message: `${cause instanceof Error ? cause.message : '请求未能完成'}。作答内容已保留，可以稍后重试。`,
          tone: 'error',
        })
      }
      if (isSessionConflictError(cause)) {
        await refreshSession(cause)
      } else if (hasConfirmedHttpResponse(cause) && !cause.retryable) {
        setPendingTurn(null)
      }
    } finally {
      setSending(false)
    }
  }

  const send = (message: string, intent = 'answer') => {
    const normalized = message.trim()
    if (!normalized || pendingTurn || sending) return
    void submitTurn({
      message: normalized,
      intent,
      clientTurnId: createClientTurnId(),
    })
  }

  const currentAction = lastReply?.action ?? (session ? statusAction[session.status] : 'diagnose')
  const currentHintLevel = lastReply?.hint_level ?? session?.hint_level ?? 0
  const nextStep = lastReply?.next_action || lastReply?.understanding_check || nextStepByAction[currentAction]
  const problemSpec = useMemo(() => [...(session?.artifacts ?? [])].reverse().find(item => item.kind === 'problem_spec')?.payload, [session])
  const target = problemSpec?.target && typeof problemSpec.target === 'object'
    ? problemSpec.target as Record<string, unknown>
    : null
  const targetObject = typeof target?.object === 'string' ? target.object : '当前题目目标'
  const currentGoal = lastReply?.current_goal_title || targetObject
  const currentGuidanceState = lastReply?.guidance_state
  const currentObstacle = lastReply?.obstacle_type
  const degradationNotice = degradationCopy(degradation)
  const savedSteps = useMemo(() => {
    if (!sessionId) return ''
    try {
      const raw = window.sessionStorage.getItem(`learning-start:${sessionId}`)
      return raw ? (JSON.parse(raw) as { existingSteps?: string }).existingSteps ?? '' : ''
    } catch {
      return ''
    }
  }, [sessionId])

  return <div className="page learning-workspace-page">
    <WorkspaceHeading title="一起思考" description={`当前数学目标：${currentGoal}。系统会保留已经成立的步骤，不把你带回开头。`} />
    <LearningWorkflow activeStep={3} completedThrough={2} />
    {serviceFailure && <ServiceNotice {...serviceFailure} />}
    {degradationNotice && <ServiceNotice {...degradationNotice} />}
    <div className="coach-workspace-grid">
      <aside className="workspace-column coach-problem-column">
        <ProblemSnapshot question={session?.question ?? ''} />
        <Card className="saved-steps-card"><h2>我的步骤</h2><Chip tone="green">原记录已保存</Chip><MathMarkdown source={savedSteps || '你的有效步骤会显示在这里。'} /><small>可以随时回看，不会被标准解法覆盖。</small></Card>
        {sessionId && <ContentIssueReporter sessionId={sessionId} problemId={session?.knowledge_problem_id} />}
      </aside>

      <Card className="coach-dialogue-card">
        <div className="dialogue-heading"><Chip>● 一起思考</Chip><span>思路地图 →</span></div>
        <div className="conversation" aria-live="polite">
          {session?.messages.slice(1).map(message => <div key={message.id} className={`message-row ${message.role}`}>
            {message.role === 'assistant' && <span className="message-author">数知伙伴</span>}
            <div className="message-bubble"><MathMarkdown source={message.content} /></div>
          </div>)}
          {sending && <div className="message-row assistant streaming-reply" role="status"><span className="message-author">数知伙伴</span><div className="message-bubble"><MathMarkdown source={streamingText || streamingStatus} /><span className="streaming-cursor" aria-hidden="true" /></div></div>}
        </div>
        {lastReply?.solution_steps.length ? <Card className="solution-card"><Chip tone="green">标准解法总结</Chip><ol>{lastReply.solution_steps.map(step => <li key={step}><MathMarkdown source={step} /></li>)}</ol></Card> : null}
        {lastReply?.sources?.length ? <Card className="source-card"><div className="source-card-heading"><span className="eyebrow">本轮参考依据</span><span className="tiny-muted">来源与版本随回答保留</span></div><ul className="source-list">{lastReply.sources.map(source => <li key={`${source.document_id}:${source.chunk_id ?? ''}`}><div className="source-title-row">{source.source_url ? <a href={source.source_url} target="_blank" rel="noreferrer">{source.title}</a> : <strong>{source.title}</strong>}<span className="source-version">{source.version ? `版本 ${source.version}` : '版本未标注'}</span></div>{source.locator ? <div className="source-locator">{source.locator}</div> : null}<div className="source-kinds">{source.supports.map(kind => <span key={kind}>{sourceKindLabel[kind]}</span>)}</div></li>)}</ul></Card> : null}
        <div className="coach-composer">
          <MathAnswerComposer id="step-answer" rows={3} value={answer} disabled={Boolean(pendingTurn) || sending} onChange={setAnswer} placeholder="写下你的下一步，也可以先解释为什么…" />
          {error && <p className="form-error" role="alert">{error}</p>}
          {pendingTurn && !sending && <div className="pending-turn" role="status"><div><strong>这条消息尚未确认送达</strong><span>{pendingTurn.message}</span></div><div className="pending-turn-actions"><button className="text-button" type="button" disabled={syncing} onClick={() => void refreshSession()}>{syncing ? '正在同步…' : '重新同步会话'}</button><Button disabled={syncing} onClick={() => void submitTurn(pendingTurn)}>使用同一请求重试</Button></div></div>}
          <div className="coach-actions"><button className="button button-secondary" type="button" disabled={sending || Boolean(pendingTurn)} onClick={() => navigate(`/learn/${sessionId}/hints`, { state: { reply: lastReply, degradation } })}>我需要提示</button><button className="button button-secondary" type="button" disabled={sending || Boolean(pendingTurn)} onClick={() => navigate(`/learn/${sessionId}/map`, { state: { reply: lastReply, degradation } })}>查看思路地图</button><Button disabled={sending || Boolean(pendingTurn) || !answer.trim()} onClick={() => send(answer)}>{sending ? '正在思考…' : pendingTurn ? '等待重试' : '发送我的想法 ↑'}</Button></div>
        </div>
      </Card>

      <aside className="workspace-column coach-progress-column">
        <Card><h2>本题学习进度</h2><div className="progress-step done">✓ 题目与条件已记录</div><div className="progress-step active">● {currentGuidanceState ? guidanceStateLabel[currentGuidanceState] : (hintLevelLabel[currentHintLevel] || actionLabel[currentAction])}</div><div className="progress-step">○ 后续步骤待探索</div>{lastReply?.total_goal_count ? <p>已完成 {lastReply.completed_goal_count} / {lastReply.total_goal_count} 个数学目标；当前是第 {lastReply.current_goal_ordinal} 个。</p> : <p>只展开当前连接；完成本题不会自动等于稳定掌握。</p>}</Card>
        <Card className="local-thinking-card"><h2>当前数学目标</h2><MathMarkdown source={currentGoal} /><p>引导状态：{currentGuidanceState ? guidanceStateLabel[currentGuidanceState] : actionLabel[currentAction]}</p>{currentObstacle ? <p>本轮障碍：{obstacleLabel[currentObstacle]}</p> : null}<div className="guidance-next-action"><strong>下一步</strong><MathMarkdown source={nextStep} /></div></Card>
        <Card><h2>草稿一直在</h2><p>已有步骤已同步。想补充或换一种成立的方法，直接在对话里说明。</p></Card>
        <button className="text-button" type="button" disabled={sending || Boolean(pendingTurn)} onClick={() => send('我懂了，这道题我会了', 'complete')}>完成本题并复盘 →</button>
      </aside>
    </div>
    <footer className="workspace-footer"><span>数知伙伴 · 不替你跳过思考，也不覆盖你的解法。</span><span>使用帮助 ↗</span></footer>
  </div>
}
