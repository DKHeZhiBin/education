import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { Button, Card, Chip } from '../../components/ui'
import { MathMarkdown } from '../../components/MathMarkdown'
import { ContentIssueReporter } from './ContentIssueReporter'
import { LearningWorkflow, ProblemSnapshot, WorkspaceHeading } from './LearningWorkspace'
import {
  createClientTurnId,
  getTutoringSession,
  hasConfirmedHttpResponse,
  isSessionConflictError,
  sendTutoringTurn,
  type RuntimeDegradation,
  type TutoringHttpError,
  type TutoringSession,
} from '../../services/tutoring'

const bottlenecks = [
  { id: 'relation', title: '还没找到关键关系', description: '知道部分条件，但不知道它们怎样连接目标' },
  { id: 'next', title: '不知道下一步用什么', description: '条件很多，还没找到可以推进的量' },
  { id: 'check', title: '帮我检查已有步骤', description: '先确认推导与条件是否一致' },
] as const

type BottleneckId = (typeof bottlenecks)[number]['id']

type ThinkingMethodCandidate = {
  category_id: string
  category_name: string
  method_id: string
  method_name: string
  role: 'primary' | 'related'
  evidence: string
  confidence: number
}

export function DiagnosisPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const incomingDegradation = (location.state as { degradation?: RuntimeDegradation | null } | null)?.degradation ?? null
  const [session, setSession] = useState<TutoringSession | null>(null)
  const [selection, setSelection] = useState<BottleneckId>('relation')
  const [customBottleneck, setCustomBottleneck] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [pendingTurn, setPendingTurn] = useState<{ message: string; clientTurnId: string } | null>(null)

  const startContext = useMemo(() => {
    if (!sessionId) return null
    try {
      const raw = window.sessionStorage.getItem(`learning-start:${sessionId}`)
      return raw ? JSON.parse(raw) as { mode?: string; startingPoint?: string; existingSteps?: string } : null
    } catch {
      return null
    }
  }, [sessionId])

  useEffect(() => {
    if (!sessionId) {
      navigate('/learn/new', { replace: true })
      return
    }
    getTutoringSession(sessionId).then(setSession).catch(cause => setError(cause instanceof Error ? cause.message : '无法读取学习会话'))
  }, [navigate, sessionId])

  const refreshSession = async (conflict?: TutoringHttpError) => {
    if (!sessionId) return
    setSyncing(true)
    if (conflict) setError(conflict.message)
    const waitSeconds = conflict?.retryAfterSeconds ?? 0
    if (waitSeconds > 0) await new Promise(resolve => window.setTimeout(resolve, waitSeconds * 1000))
    try {
      const latest = await getTutoringSession(sessionId)
      setSession(latest)
      setError(conflict?.code === 'session_busy'
        ? '最新会话已同步。请确认后使用同一请求重试。'
        : '已加载最新学习进度，可以继续。')
    } catch (cause) {
      setError(cause instanceof Error ? `重新获取会话失败：${cause.message}` : '重新获取会话失败，请再试一次')
    } finally {
      setSyncing(false)
    }
  }

  const submitTurn = async (turn: { message: string; clientTurnId: string }) => {
    if (!sessionId) return
    setSubmitting(true)
    setError('')
    setPendingTurn(turn)
    try {
      const result = await sendTutoringTurn(sessionId, turn.message, 'answer', turn.clientTurnId)
      setPendingTurn(null)
      navigate(`/learn/${sessionId}/coach`, {
        state: {
          reply: result.reply,
          degradation: result.degraded ? { code: result.degradation_code, reason: result.degradation_reason } : incomingDegradation,
        },
      })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '提交失败，请稍后重试')
      if (isSessionConflictError(cause)) await refreshSession(cause)
      else if (hasConfirmedHttpResponse(cause) && !cause.retryable) setPendingTurn(null)
    } finally {
      setSubmitting(false)
    }
  }

  const continueLearning = () => {
    if (pendingTurn) return
    const selected = bottlenecks.find(item => item.id === selection)
    const message = customBottleneck.trim() || selected?.title || '我还不确定卡点在哪里'
    void submitTurn({ message, clientTurnId: createClientTurnId() })
  }

  const existingSteps = startContext?.existingSteps?.trim()
    || ''
  const clarificationReply = (() => {
    if (session?.status !== 'clarifying') return ''
    const artifact = [...session.artifacts].reverse().find(item => item.kind === 'tutor_reply')
    return typeof artifact?.payload.text === 'string' ? artifact.payload.text : ''
  })()
  const isClarifying = Boolean(clarificationReply)
  const methodCandidates = (() => {
    const problemSpec = [...(session?.artifacts ?? [])].reverse().find(artifact => artifact.kind === 'problem_spec')?.payload
    return Array.isArray(problemSpec?.thinking_methods) ? problemSpec.thinking_methods as ThinkingMethodCandidate[] : []
  })()
  const isMethodRecognition = startContext?.mode === 'method-recognition'

  return <div className="page learning-workspace-page">
    <WorkspaceHeading
      title={isMethodRecognition ? '题目结构与方法归类' : isClarifying ? '先补充一个题目条件' : '接住你的思路'}
      description={isMethodRecognition ? '先看主方法为什么成立，再比较可以关联的其他方法。' : isClarifying ? '这个条件会改变解集，确认后再进入解题分析。' : existingSteps ? '已接续草稿。从你完成的步骤开始，而不是重新给你一条标准路线。' : '题目已经确认，接下来定位真正需要连接的地方。'}
      badge={isMethodRecognition ? '方法识别已记录' : isClarifying ? '等待补充条件' : existingSteps ? '草稿已保留' : '题目已确认'}
    />
    <LearningWorkflow activeStep={2} completedThrough={1} />

    <div className="diagnosis-workspace-grid">
      <div className="workspace-column">
        <ProblemSnapshot question={session?.question ?? ''}>
          {sessionId && <ContentIssueReporter sessionId={sessionId} problemId={session?.knowledge_problem_id} />}
        </ProblemSnapshot>
        {isMethodRecognition && <Card className="method-classification-card">
          <div className="method-classification-heading"><h2>思想与方法识别</h2><Chip tone="green">{methodCandidates.length ? '已完成初步归类' : '等待可靠归类'}</Chip></div>
          {methodCandidates.length ? <div className="method-classification-list">{methodCandidates.map(item => <article key={`${item.category_id}-${item.method_id}`}>
            <span>{item.role === 'primary' ? '主方法' : '关联方法'}</span><div><strong>{item.category_name} · {item.method_name}</strong><MathMarkdown source={item.evidence} /></div><small>{Math.round(item.confidence * 100)}%</small>
          </article>)}</div> : <p className="tiny-muted">当前分析没有形成可信的方法标签，本轮不会把猜测当作正式归类。</p>}
        </Card>}
        <Card className="saved-steps-card">
          <h2>我的步骤</h2>
          <Chip tone={existingSteps ? 'green' : 'blue'}>{existingSteps ? '原记录已保存' : '尚未作答'}</Chip>
          <MathMarkdown source={existingSteps || '还没有保存步骤，可以直接描述你准备从哪里开始。'} />
          <small>{existingSteps ? '来自你的输入 · 可以继续补充' : '题目文本不会被当作学生步骤'}</small>
        </Card>
        {existingSteps && <aside className="validated-work-callout"><strong>✓ 已保存这些步骤</strong><p>Agent 会先检查是否成立，再决定从哪里继续。</p></aside>}
      </div>

      <Card className="bottleneck-card">
        <h2>{isClarifying ? '请确认题目条件' : '接下来，哪里还连不上？'}</h2>
        <MathMarkdown source={isClarifying ? clarificationReply : '先定位需要搭桥的地方。卡住不代表前面的努力无效。'} />
        {!isClarifying && <div className="starting-point-list bottleneck-list" role="radiogroup" aria-label="选择当前卡点">
          {bottlenecks.map(option => <button key={option.id} type="button" role="radio" aria-checked={selection === option.id} className={`starting-point-option ${selection === option.id ? 'selected' : ''}`} onClick={() => setSelection(option.id)}>
            <span><strong>{option.title}</strong><small>{option.description}</small></span><i aria-hidden="true" />
          </button>)}
        </div>}
        <label className="field-label" htmlFor="custom-bottleneck">{isClarifying ? '你的回答' : '也可以直接说出你的卡点'}</label>
        <textarea id="custom-bottleneck" rows={4} value={customBottleneck} onChange={event => setCustomBottleneck(event.target.value)} placeholder={isClarifying ? '例如：在实数范围内求解。' : '例如：我看到了重复结构，但不确定该怎样转化。'} />
        <p className="tiny-muted">{isClarifying ? '确认范围后，系统会重新检查题意并进入解题分析。' : '不同但成立的思路，我们都会接着看。你也可以补充自己的方法。'}</p>
        {error && <p className="form-error" role="alert">{error}</p>}
        {pendingTurn && !submitting && <div className="pending-turn" role="status">
          <div><strong>这次回答尚未确认送达</strong><span>{pendingTurn.message}</span></div>
          <div className="pending-turn-actions">
            <button className="text-button" type="button" disabled={syncing} onClick={() => void refreshSession()}>{syncing ? '正在同步…' : '重新同步会话'}</button>
            <Button disabled={syncing} onClick={() => void submitTurn(pendingTurn)}>使用同一请求重试</Button>
          </div>
        </div>}
        <Button disabled={submitting || Boolean(pendingTurn) || (isClarifying && !customBottleneck.trim())} onClick={continueLearning}>{submitting ? (isClarifying ? '正在确认条件…' : '正在理解卡点…') : pendingTurn ? '等待重试' : isClarifying ? '确认并继续 →' : '从这里一起思考 →'}</Button>
      </Card>
    </div>
    <footer className="workspace-footer"><span>数知伙伴 · 不替你跳过思考，也不覆盖你的解法。</span><span>使用帮助 ↗</span></footer>
  </div>
}
