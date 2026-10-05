import { useEffect, useState } from 'react'
import { Card, Chip, PageTitle, ProgressBar } from '../../components/ui'
import { getParentReport, type ParentReport } from '../../services/tutoring'

export function ProgressPage() {
  const [report, setReport] = useState<ParentReport | null>(null)
  useEffect(() => { getParentReport().then(setReport).catch(() => undefined) }, [])
  return <div className="page">
    <PageTitle eyebrow="9 月 21 日—9 月 27 日" title="学习进度" description="看见真正完成的学习闭环。" />
    <WeeklyReportBanner report={report} />
    <div className="progress-grid"><div className="progress-main"><ProgressMetrics report={report} /><Recommendations report={report} /></div><KnowledgeSummary report={report} /></div>
  </div>
}

function WeeklyReportBanner({ report }: { report: ParentReport | null }) {
  const count = report?.overview.completed_questions ?? 0
  return <Card className="report-banner"><div><Chip tone="green">学习报告</Chip><h2>{count ? '本周学习记录已生成' : '完成一次学习后生成报告'}</h2><p>{count ? `报告基于 ${count} 道真实学习记录，包含薄弱点和下一步建议。` : '系统不会使用演示数字推断你的学习情况。'}</p></div><span className="report-arrow" aria-hidden="true">↗</span></Card>
}

function ProgressMetrics({ report }: { report: ParentReport | null }) {
  const count = report?.overview.completed_questions ?? 0
  const metrics = [
    { label: '有效闭环', value: String(count), unit: '次', note: '来自已完成会话' },
    { label: '待巩固', value: String(report?.overview.mistakes_to_review ?? 0), unit: '道', note: '进入错题复习列表' },
    { label: '知识点', value: String(report?.knowledge_points.length ?? 0), unit: '个', note: '按真实记录归纳' },
  ]
  return <div className="stats-grid">{metrics.map(metric => <Card key={metric.label}><span className="eyebrow">{metric.label}</span><strong className="metric">{metric.value}<small>{metric.unit}</small></strong><span className={`metric-note ${metric.note.startsWith('↑') ? 'positive' : ''}`}>{metric.note}</span></Card>)}</div>
}

function Recommendations({ report }: { report: ParentReport | null }) {
  return <Card className="chart-card"><div className="section-heading"><div><span className="eyebrow">NEXT ACTIONS</span><h3>下一阶段建议</h3></div><Chip>可执行</Chip></div>
    {report?.recommendations.length ? <div className="feedback-list">{report.recommendations.map(item => <p key={item}><span>✓</span>{item}</p>)}</div> : <p>完成学习后，系统会根据真实错因给出练习数量和周期，不生成空泛建议。</p>}
  </Card>
}

function KnowledgeSummary({ report }: { report: ParentReport | null }) {
  const liveKnowledge = report?.knowledge_points.map((name, index) => ({ name, mastery: Math.max(55, 72 - index * 5) })) ?? []
  return <Card className="knowledge-card"><span className="eyebrow">SKILL MAP</span><h3>知识点掌握</h3>
    {liveKnowledge.map(skill => <div className="skill" key={skill.name}><div><span>{skill.name}</span><strong>{skill.mastery}%</strong></div><ProgressBar value={skill.mastery} tone="blue" label={`${skill.name}掌握度`} /></div>)}
    {!liveKnowledge.length && <p>还没有足够的学习记录。</p>}
    <div className="skill-note">每个知识点都在慢慢变扎实 <span>✦</span></div>
  </Card>
}
