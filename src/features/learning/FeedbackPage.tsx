import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button, Card, Chip, PageTitle, ProgressBar } from '../../components/ui'
import { getTutoringSession, type TutoringSession } from '../../services/tutoring'

export function FeedbackPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const [session, setSession] = useState<TutoringSession | null>(null)

  useEffect(() => {
    if (!sessionId) {
      navigate('/learn/new', { replace: true })
      return
    }
    getTutoringSession(sessionId).then(setSession).catch(() => navigate('/learn/new', { replace: true }))
  }, [navigate, sessionId])

  const record = session?.record
  return <div className="page narrow">
    <PageTitle eyebrow="学习流程 · 完成" title="这题完成了" description="重点看清哪些能力已掌握、哪里还要巩固。" />
    <div className="chip-row"><Chip tone="amber">{session?.hint_level ?? 0} 级提示后完成</Chip><Chip tone="green">完成 {session?.attempts ?? 0} 次思考</Chip></div>
    <Card className="amber-card"><span className="eyebrow">本次卡点</span><h2>{record?.error_reason || '继续观察你的解题习惯'}</h2><p>记录来自本次真实对话，之后可以在错题本里再次练习。</p></Card>
    <Card className="teal-card"><span className="eyebrow">学习状态</span><strong className="metric">已完成</strong><ProgressBar value={72} label="当前学习闭环进度" /></Card>
    <Card><h3>这道题用到的知识点</h3><div className="chip-row">{record?.knowledge_tags.map(tag => <Chip key={tag}>{tag}</Chip>) ?? <span className="tiny-muted">正在整理知识点</span>}</div>
      {record?.correct_approach && <div className="feedback-summary"><strong>复盘思路</strong><p>{record.correct_approach}</p></div>}
    </Card>
    <div className="form-foot"><Button to="/mistakes" secondary>回错题本</Button><Button to="/learn/new">再学一道 →</Button></div>
  </div>
}
