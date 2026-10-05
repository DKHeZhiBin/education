import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button, Card, Chip, PageTitle } from '../../components/ui'
import { getTutoringSession, sendTutoringTurn, type TutorReply, type TutoringSession } from '../../services/tutoring'

const sourceKindLabel: Record<TutorReply['sources'][number]['supports'][number], string> = {
  concept: '概念依据',
  principle: '定理与公式',
  example_pattern: '例题结构',
  worked_example: '完整例题',
  error_pattern: '易错分析',
  hint: '提示依据',
  source_fact: '教材结论',
}

export function CoachPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const [session, setSession] = useState<TutoringSession | null>(null)
  const [answer, setAnswer] = useState('')
  const [lastReply, setLastReply] = useState<TutorReply | null>(null)
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)

  useEffect(() => {
    if (!sessionId) {
      navigate('/learn/new', { replace: true })
      return
    }
    getTutoringSession(sessionId).then(setSession).catch(cause => setError(cause instanceof Error ? cause.message : '无法读取学习会话'))
  }, [navigate, sessionId])

  const send = async (message: string, intent = 'answer') => {
    if (!sessionId || !message.trim()) return
    setSending(true)
    setError('')
    try {
      const result = await sendTutoringTurn(sessionId, message.trim(), intent)
      setSession(result.session)
      setLastReply(result.reply)
      setAnswer('')
      if (result.session.status === 'completed') navigate(`/learn/${sessionId}/feedback`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '消息发送失败')
    } finally {
      setSending(false)
    }
  }

  return <div className="page narrow">
    <PageTitle eyebrow="学习流程 · 02 / 04" title="我们一起理清这一步" description="每次只解决一个卡点，理解后再继续。" />
    <Card className="question-card"><span className="eyebrow">当前题目</span><div className="equation small-equation">{session?.question ?? '正在读取题目…'}</div></Card>
    <div className="conversation" aria-live="polite">
      {session?.messages.slice(1).map(message => <div key={message.id} className={`message-row ${message.role}`}>
        {message.role === 'assistant' && <span className="coach-mark">知</span>}
        <div className="message-bubble">{message.content}</div>
      </div>)}
    </div>
    {lastReply?.solution_steps.length ? <Card className="solution-card"><Chip tone="green">标准解法总结</Chip><ol>{lastReply.solution_steps.map(step => <li key={step}>{step}</li>)}</ol></Card> : null}
    {lastReply?.sources?.length ? <Card className="source-card">
      <div className="source-card-heading"><span className="eyebrow">本轮参考依据</span><span className="tiny-muted">来源与版本随回答保留</span></div>
      <ul className="source-list">{lastReply.sources.map(source => <li key={`${source.document_id}:${source.chunk_id ?? ''}`}>
        <div className="source-title-row">
          {source.source_url
            ? <a href={source.source_url} target="_blank" rel="noreferrer">{source.title}</a>
            : <strong>{source.title}</strong>}
          <span className="source-version">{source.version ? `版本 ${source.version}` : '版本未标注'}</span>
        </div>
        {source.locator ? <div className="source-locator">{source.locator}</div> : null}
        <div className="source-kinds">{source.supports.map(kind => <span key={kind}>{sourceKindLabel[kind]}</span>)}</div>
      </li>)}</ul>
    </Card> : null}
    <Card className="coach-composer">
      <label className="field-label" htmlFor="step-answer">写下你的想法</label>
      <textarea id="step-answer" rows={3} value={answer} onChange={event => setAnswer(event.target.value)} placeholder="例如：左边展开后是 3x − 6" />
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="coach-actions">
        <button className="text-button" type="button" disabled={sending} onClick={() => send('我还不确定，请给我一个提示', 'ask_hint')}>给我一个提示</button>
        <button className="text-button" type="button" disabled={sending} onClick={() => send('我想看完整答案和标准解法', 'ask_solution')}>查看完整讲解</button>
        <Button onClick={() => send(answer)}>{sending ? '正在思考…' : '发送 →'}</Button>
      </div>
      <div className="completion-row"><span className="tiny-muted">真正理解后再完成，这会写入学习记录。</span><button className="text-button" type="button" disabled={sending} onClick={() => send('我懂了，这道题我会了', 'complete')}>我已经学会</button></div>
    </Card>
  </div>
}
