import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button, Card, Chip, PageTitle, ProgressBar } from '../../components/ui'
import { getTutoringSession, sendTutoringTurn, type TutoringSession } from '../../services/tutoring'

const diagnosticOptions = [
  '先把左边的括号去掉',
  '先把含 x 的项移到一边',
  '我不太确定从哪里开始',
]

export function DiagnosisPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const [session, setSession] = useState<TutoringSession | null>(null)
  const [selection, setSelection] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!sessionId) {
      navigate('/learn/new', { replace: true })
      return
    }
    getTutoringSession(sessionId).then(setSession).catch(cause => setError(cause instanceof Error ? cause.message : '无法读取学习会话'))
  }, [navigate, sessionId])

  const continueLearning = async () => {
    if (!sessionId || !selection) return
    setSubmitting(true)
    setError('')
    try {
      await sendTutoringTurn(sessionId, selection, 'answer')
      navigate(`/learn/${sessionId}/coach`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '提交失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  return <div className="page narrow">
    <PageTitle eyebrow="学习流程 · 01 / 04" title="先确认你的卡点" description="不用急着算答案，选最符合现在情况的选项。" />
    <div className="step-progress"><Chip>诊断 1 / 3</Chip><ProgressBar value={33} label="诊断进度" /></div>
    <Card className="equation-card"><span className="eyebrow">你提交的题目</span><div className="equation">{session?.question ?? '正在读取题目…'}</div></Card>
    <Card>
      <div className="coach-prompt"><span className="coach-mark">知</span><p>{session?.messages.find(message => message.role === 'assistant')?.content ?? '你觉得第一步可以从哪里开始？'}</p></div>
      <h3>第一步，你准备先做什么？</h3><div className="answer-options" role="group" aria-label="选择解题思路">
        {diagnosticOptions.map((option, index) => <button key={option} type="button" aria-pressed={selection === option} className={`answer-option ${selection === option ? 'chosen' : ''}`} onClick={() => setSelection(option)}>
          <span className="option-letter">{String.fromCharCode(65 + index)}</span>{option}<span className="radio" />
        </button>)}
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
    </Card>
    <div className="sticky-action"><span className="tiny-muted">没有标准答案，选你的真实想法</span>
      {selection ? <Button onClick={continueLearning}>{submitting ? '正在诊断…' : '继续 →'}</Button> : <Button onClick={() => setSelection(diagnosticOptions[2])}>选择“不确定”继续</Button>}
    </div>
  </div>
}
