import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, Chip, PageTitle, ProgressBar } from '../../components/ui'
import { MathMarkdown } from '../../components/MathMarkdown'
import {
  listTutoringSessions,
  type TutoringSessionSummary,
} from '../../services/tutoring'

const statusLabel: Record<TutoringSessionSummary['status'], string> = {
  collecting: '等待补充',
  clarifying: '正在澄清',
  diagnosing: '诊断思路',
  hinting: '分级提示',
  checking_attempt: '检查作答',
  explaining: '完整讲解',
  completed: '已经完成',
}

export function DashboardPage() {
  return <div className="page">
    <PageTitle eyebrow="星期三 · 9 月 23 日" title="晚上好，林晓" description="今天用 25 分钟，完成一个理解—练习闭环。" />
    <div className="home-grid">
      <div className="home-main">
        <DailyPlanCard />
        <ContinueLearningCard />
        <WeeklyMetricCards />
      </div>
      <aside className="home-side">
        <WeeklySummaryCard />
        <LearningHabitsCard />
      </aside>
    </div>
  </div>
}

function DailyPlanCard() {
  return <Card className="plan-card">
    <div className="card-topline"><Chip>今日学习计划</Chip><span className="subtle">约 25 分钟</span></div>
    <h2>一元一次方程 <span className="muted-dot">·</span> 移项</h2>
    <p>先复习易错步骤，再独立完成 2 道相似题。</p>
    <ProgressBar value={38} label="今日学习进度" />
    <div className="plan-foot"><span className="tiny-muted">学习进度 <b>2 / 5 步</b></span><Button to="/learn/new">开始今日学习 <span>→</span></Button></div>
  </Card>
}

function ContinueLearningCard() {
  const [sessions, setSessions] = useState<TutoringSessionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadSessions = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await listTutoringSessions()
      setSessions(result.filter(item => item.status !== 'completed').slice(0, 4))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '暂时无法读取学习记录')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadSessions()
  }, [loadSessions])

  return <Card className="session-history-card">
    <div className="section-heading">
      <div><span className="eyebrow">PICK UP WHERE YOU LEFT OFF</span><h3>继续未完成的学习</h3></div>
      <Link to="/learn/new" className="text-link">开始新题 →</Link>
    </div>
    {loading && <div className="session-history-state" role="status">正在读取最近会话…</div>}
    {!loading && error && <div className="session-history-state error" role="alert">
      <span>{error}</span>
      <button type="button" className="text-button" onClick={() => void loadSessions()}>重新加载</button>
    </div>}
    {!loading && !error && sessions.length === 0 && <div className="session-history-empty">
      <div className="subject-icon">x²</div>
      <div><strong>目前没有未完成的学习</strong><p>提交一道新题后，可以随时从这里回来继续。</p></div>
    </div>}
    {!loading && !error && sessions.length > 0 && <div className="session-history-list">
      {sessions.map(session => <Link className="continue-row session-history-row" key={session.id} to={resumePath(session)}>
        <div className="subject-icon">x²</div>
        <div className="continue-copy">
          <MathMarkdown className="session-question" source={session.question} />
          <p>{formatUpdatedAt(session.updated_at)} · {formatModel(session.llm_model_id)}</p>
        </div>
        <Chip tone="amber">{statusLabel[session.status]}</Chip>
        <span className="continue-arrow" aria-hidden="true">→</span>
      </Link>)}
    </div>}
  </Card>
}

function resumePath(session: TutoringSessionSummary) {
  const diagnosisStatuses: TutoringSessionSummary['status'][] = [
    'collecting',
    'clarifying',
    'diagnosing',
  ]
  const step = diagnosisStatuses.includes(session.status) ? 'diagnosis' : 'coach'
  return `/learn/${session.id}/${step}`
}

function formatUpdatedAt(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '最近更新'
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function formatModel(modelId: string | null) {
  if (!modelId) return '默认辅导模型'
  return modelId.replace(':', ' · ')
}

function WeeklyMetricCards() {
  return <div className="two-cards">
    <Card className="mini-card"><span className="mini-icon teal-icon">↗</span><span className="eyebrow">本周学习</span><strong className="metric">3.5 <small>小时</small></strong><span className="tiny-muted">比上周多 40 分钟</span></Card>
    <Card className="mini-card"><span className="mini-icon blue-icon">✓</span><span className="eyebrow">独立解题率</span><strong className="metric">68<small>%</small></strong><span className="tiny-muted">持续向上，做得不错</span></Card>
  </div>
}

function WeeklySummaryCard() {
  return <Card className="weekly-card">
    <Chip tone="green">本周小结</Chip><h3>每一步都在<br />变成真正的进步。</h3>
    <p>你已经完成 <b>6 次</b>有效学习闭环，这周独立解题率提升至 68%。</p>
    <Link to="/progress" className="dark-link">查看学习周报 <span>→</span></Link><div className="weekly-decoration" aria-hidden="true">✳</div>
  </Card>
}

function LearningHabitsCard() {
  return <Card className="focus-card"><span className="eyebrow">正在建立的习惯</span>
    <HabitRow title="先说思路，再动笔" detail="已经连续坚持 4 天" />
    <HabitRow title="错题当天回看" detail="还有 3 道题等你巩固" />
    <Button to="/mistakes" secondary>打开错题本</Button>
  </Card>
}

function HabitRow({ title, detail }: { title: string; detail: string }) {
  return <div className="habit"><span className="habit-check">✓</span><div><strong>{title}</strong><p>{detail}</p></div></div>
}
