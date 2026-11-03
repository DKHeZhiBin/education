import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { Button, Card, Chip, ServiceNotice } from '../../components/ui'
import { MathInline, MathMarkdown } from '../../components/MathMarkdown'
import { LearningWorkflow, WorkspaceHeading } from './LearningWorkspace'
import {
  createClientTurnId,
  getTutoringSession,
  streamTutoringTurn,
  type RuntimeDegradation,
  type TutorReply,
  type TutoringSession,
} from '../../services/tutoring'

type MapNodeStatus = 'completed' | 'current' | 'goal' | 'pending'

interface ThoughtMapNode {
  id: string
  title: string
  detail: string
  status: MapNodeStatus
  source: string
}

interface ThoughtMapModel {
  established: ThoughtMapNode[]
  goal: ThoughtMapNode
  current: ThoughtMapNode
  pending: ThoughtMapNode
}

const actionTitles: Record<TutorReply['action'], string> = {
  clarify: '补齐题目信息',
  diagnose: '定位当前卡点',
  hint: '建立关键关系',
  check_attempt: '检查这一步是否成立',
  explain: '连接局部步骤',
  summarize: '整理完整思路',
}

function extractGoal(question: string) {
  const match = question.match(/(求|计算|证明|解出|解)([^。；;？?]{1,64})/)
  if (!match) return '完成题目所求'
  return `${match[1]}${match[2]}`
}

function savedStepsFor(sessionId: string) {
  try {
    const raw = window.sessionStorage.getItem(`learning-start:${sessionId}`)
    const value = raw ? (JSON.parse(raw) as { existingSteps?: string }).existingSteps : ''
    return (value ?? '')
      .split(/\n+|(?<=[。；;])/)
      .map(step => step.trim())
      .filter(Boolean)
      .slice(0, 2)
  } catch {
    return []
  }
}

function buildThoughtMap(
  session: TutoringSession,
  reply: TutorReply | null,
  savedSteps: string[],
): ThoughtMapModel {
  const latestAssistantMessage = [...session.messages].reverse().find(message => message.role === 'assistant')
  const established: ThoughtMapNode[] = [{
    id: 'question-confirmed',
    title: '读懂题目与条件',
    detail: session.question,
    status: 'completed',
    source: '题目确认',
  }]

  savedSteps.forEach((step, index) => established.push({
    id: `saved-step-${index}`,
    title: index === 0 ? '接住已有步骤' : `已有步骤 ${index + 1}`,
    detail: step,
    status: 'completed',
    source: '学生开始页记录',
  }))

  const solutionGraph = [...session.artifacts].reverse().find(item => item.kind === 'solution_graph')?.payload
  const graphGoals = Array.isArray(solutionGraph?.goals)
    ? solutionGraph.goals.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
    : []
  const completedGoalCount = reply?.completed_goal_count ?? 0
  graphGoals.slice(0, completedGoalCount).forEach((goal, index) => established.push({
    id: typeof goal.id === 'string' ? goal.id : `completed-goal-${index}`,
    title: `已完成数学目标 ${index + 1}`,
    detail: typeof goal.title === 'string' ? goal.title : '该目标已有本轮证据支持。',
    status: 'completed',
    source: '引导状态机',
  }))

  const currentTitle = reply?.current_goal_title
    ? `当前目标 ${reply.current_goal_ordinal ?? ''}`.trim()
    : reply ? actionTitles[reply.action] : '寻找当前连接'
  const currentDetail = reply?.next_action
    || reply?.current_goal_title
    || reply?.understanding_check
    || latestAssistantMessage?.content
    || '把已知条件与求解目标连接起来，先写出下一条关系。'

  return {
    established,
    goal: {
      id: 'goal',
      title: `目标：${extractGoal(session.question)}`,
      detail: '从题目所求倒推需要哪些中间量或关系。',
      status: 'goal',
      source: '题目目标',
    },
    current: {
      id: 'current-connection',
      title: currentTitle,
      detail: currentDetail,
      status: 'current',
      source: reply ? '本轮 Agent 理解检查' : '当前会话',
    },
    pending: {
      id: 'next-exploration',
      title: '下一段探索',
      detail: '当前连接成立后再展开，暂不提前暴露完整解法。',
      status: 'pending',
      source: '分级提示策略',
    },
  }
}

function ThoughtNode({ node }: { node: ThoughtMapNode }) {
  const symbol = node.status === 'completed' ? '✓' : node.status === 'current' ? '●' : '○'
  return <article className={`thought-node ${node.status}`}>
    <div className="thought-node-title"><span aria-hidden="true">{symbol}</span><strong><MathInline source={node.title} /></strong></div>
    <MathMarkdown source={node.detail} />
    <small>{node.source}</small>
  </article>
}

export function ThoughtMapPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const navigationState = location.state as {
    reply?: TutorReply
    degradation?: RuntimeDegradation | null
  } | null
  const [session, setSession] = useState<TutoringSession | null>(null)
  const [reply, setReply] = useState<TutorReply | null>(navigationState?.reply ?? null)
  const [degradation, setDegradation] = useState<RuntimeDegradation | null>(navigationState?.degradation ?? null)
  const [input, setInput] = useState('')
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)
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
    void getTutoringSession(sessionId)
      .then(loadedSession => {
        setSession(loadedSession)
        const latestReply = [...loadedSession.artifacts].reverse().find(item => item.kind === 'tutor_reply')?.payload
        if (latestReply) setReply(latestReply as unknown as TutorReply)
      })
      .catch(cause => setError(cause instanceof Error ? cause.message : '无法读取学习会话'))
  }, [navigate, sessionId])

  const savedSteps = useMemo(() => sessionId ? savedStepsFor(sessionId) : [], [sessionId])
  const map = useMemo(
    () => session ? buildThoughtMap(session, reply, savedSteps) : null,
    [reply, savedSteps, session],
  )

  const submit = async (turn: { message: string; intent: string; clientTurnId: string }, returnToCoach = false) => {
    if (!sessionId) return
    setSending(true)
    setError('')
    setPendingTurn(turn)
    try {
      const result = await streamTutoringTurn(sessionId, turn.message, turn.intent, turn.clientTurnId)
      setSession(result.session)
      setReply(result.reply)
      setDegradation(result.degraded ? {
        code: result.degradation_code,
        reason: result.degradation_reason,
      } : null)
      setPendingTurn(null)
      setInput('')
      if (returnToCoach || result.session.status === 'completed') {
        navigate(result.session.status === 'completed'
          ? `/learn/${sessionId}/feedback`
          : `/learn/${sessionId}/coach`, {
          state: {
            reply: result.reply,
            degradation: result.degraded ? {
              code: result.degradation_code,
              reason: result.degradation_reason,
            } : null,
          },
        })
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '本轮提交失败，请使用同一请求重试')
    } finally {
      setSending(false)
    }
  }

  const sendInput = () => {
    const message = input.trim()
    if (!message || pendingTurn || sending) return
    void submit({ message, intent: 'answer', clientTurnId: createClientTurnId() })
  }

  if (!session || !map) return <div className="page learning-workspace-page">
    <WorkspaceHeading title="思路地图" description="正在整理本轮成立步骤、当前连接和待探索节点。" />
    {error ? <ServiceNotice title="思路地图暂时无法读取" message={error} tone="error" /> : <p className="tiny-muted">正在读取学习会话…</p>}
  </div>

  return <div className="page learning-workspace-page">
    <WorkspaceHeading
      title="思路地图"
      description="只看当前局部 · 从已知推进，也从目标倒推。后续结论暂不展开。"
      badge="由本轮对话整理"
    />
    <LearningWorkflow activeStep={4} completedThrough={3} />
    {degradation?.code && <ServiceNotice
      title="本轮使用降级结果"
      message={degradation.reason || '地图保留已有会话信息，知识检索依据可能不完整。'}
      tone="warning"
    />}
    <div className="thought-map-workspace">
      <Card className="thought-map-card">
        <div className="thought-map-card-header">
          <div><span className="eyebrow">当前题目</span><MathMarkdown source={session.question} /></div>
          <div className="thought-map-legend" aria-label="节点状态图例"><span className="completed">✓ 已完成</span><span className="current">● 当前连接</span><span>○ 待探索</span></div>
        </div>
        <p className="thought-map-disclaimer">✓ 表示本学习流程已确认或已保留；学生原步骤仍会在后续数学校验中复核。</p>
        <div className="thought-map-canvas">
          <div className="thought-branch established-branch">
            <h2>从已知推进 <span>↓</span></h2>
            <div className="thought-node-stack">{map.established.map(node => <ThoughtNode key={node.id} node={node} />)}</div>
          </div>
          <div className="thought-branch goal-branch">
            <h2>从目标倒推 <span>↓</span></h2>
            <ThoughtNode node={map.goal} />
          </div>
          <div className="thought-map-merge" aria-hidden="true"><span /><i /><span /></div>
          <div className="thought-current-node"><ThoughtNode node={map.current} /></div>
          <div className="thought-map-downlink" aria-hidden="true" />
          <div className="thought-pending-node"><ThoughtNode node={map.pending} /></div>
        </div>
      </Card>

      <aside className="thought-map-side">
        <Card className="current-node-editor">
          <Chip>● 当前节点</Chip>
          <h2><MathInline source={map.current.title} /></h2>
          <MathMarkdown source={map.current.detail} />
          <label className="field-label" htmlFor="thought-map-input">补写你的连接</label>
          <textarea id="thought-map-input" rows={5} value={input} disabled={sending || Boolean(pendingTurn)} onChange={event => setInput(event.target.value)} placeholder="例如：由哪两个条件可以推出这个关系？" />
          {error && <p className="form-error" role="alert">{error}</p>}
          {pendingTurn && !sending && <div className="map-retry-panel"><strong>这一步尚未确认送达</strong><MathMarkdown source={pendingTurn.message} /><Button onClick={() => void submit(pendingTurn)}>使用同一请求重试</Button></div>}
          <Button disabled={sending || Boolean(pendingTurn) || !input.trim()} onClick={sendInput}>{sending ? '正在检查…' : '补写这一步'}</Button>
        </Card>
        <Card className="map-knowledge-card">
          <span className="eyebrow">当前关联</span>
          <h2>{session.profile.subject} · {session.profile.grade}</h2>
          <p>地图只展示当前会话证据，不会混入其他学生的个人历史。</p>
        </Card>
        <button className="button button-secondary map-hint-button" type="button" disabled={sending || Boolean(pendingTurn)} onClick={() => navigate(`/learn/${sessionId}/hints`, { state: { reply, degradation } })}>需要一点提示</button>
        <button className="text-button map-back-button" type="button" onClick={() => navigate(`/learn/${sessionId}/coach`, { state: { reply, degradation } })}>← 返回一起思考</button>
      </aside>
    </div>
    <footer className="workspace-footer"><span>数知伙伴 · 当前只展开一条连接。</span><span>节点会随本轮作答更新</span></footer>
  </div>
}
