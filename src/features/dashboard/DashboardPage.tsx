import { Link } from 'react-router-dom'
import { Button, Card, Chip, PageTitle, ProgressBar } from '../../components/ui'

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
  return <Card>
    <div className="section-heading"><div><span className="eyebrow">PICK UP WHERE YOU LEFT OFF</span><h3>继续学习</h3></div><Link to="/learn/diagnosis" className="text-link">查看计划 →</Link></div>
    <div className="continue-row"><div className="subject-icon">x²</div><div className="continue-copy"><strong>整式运算 · 去括号</strong><p>上次学到：判断负号影响范围</p></div><Chip tone="amber">待巩固</Chip></div>
  </Card>
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
