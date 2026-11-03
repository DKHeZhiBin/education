import { useEffect, useState } from 'react'
import { Card, Chip, PageTitle } from '../../components/ui'
import { getParentReport, type ParentReport } from '../../services/tutoring'

export function ProgressPage() {
  const [report, setReport] = useState<ParentReport | null>(null)
  useEffect(() => { getParentReport().then(setReport).catch(() => undefined) }, [])
  const scope = report?.sample_scope
  const rangeLabel = scope?.first_record_date && scope.last_record_date
    ? `${scope.first_record_date}—${scope.last_record_date}`
    : '暂无已完成记录'
  return <div className="page">
    <PageTitle eyebrow={rangeLabel} title="学习进度" description="报告只统计真实完成并写入学习记录的会话。" />
    <WeeklyReportBanner report={report} />
    <SampleScope report={report} />
    <div className="progress-grid"><div className="progress-main"><ProgressMetrics report={report} /><Recommendations report={report} /></div><KnowledgeSummary report={report} /></div>
  </div>
}

function WeeklyReportBanner({ report }: { report: ParentReport | null }) {
  const count = report?.overview.completed_questions ?? 0
  return <Card className="report-banner"><div><Chip tone="green">学习报告</Chip><h2>{count ? '真实学习记录已汇总' : '完成一次学习后生成报告'}</h2><p>{count ? `报告基于 ${count} 道已完成题目的持久化学习记录。` : '系统不会使用演示数字推断学习情况。'}</p></div><span className="report-arrow" aria-hidden="true">↗</span></Card>
}

function SampleScope({ report }: { report: ParentReport | null }) {
  const scope = report?.sample_scope
  return <Card><div className="section-heading"><div><span className="eyebrow">样本范围</span><h3>本报告用了哪些数据</h3></div><Chip>{scope?.status === 'available' ? '真实记录' : '暂无样本'}</Chip></div>
    {scope?.status === 'available' ? <div className="feedback-list">
      <p><span>✓</span>时间：{scope.first_record_date} 至 {scope.last_record_date}</p>
      <p><span>✓</span>样本：{scope.completed_record_count} 条已完成学习记录，{scope.knowledge_evidence_count} 条知识点证据</p>
      <p><span>✓</span>范围：{scope.grades.join('、') || '年级未标注'} · {scope.subjects.join('、') || '学科未标注'}</p>
    </div> : <p>还没有已完成并写入数据库的学习记录。</p>}
    {report?.note && <p className="tiny-muted">{report.note}</p>}
  </Card>
}

function ProgressMetrics({ report }: { report: ParentReport | null }) {
  const metrics = [
    { label: '有效闭环', value: String(report?.overview.completed_questions ?? 0), unit: '次', note: '来自已完成会话' },
    { label: '待巩固', value: String(report?.overview.mistakes_to_review ?? 0), unit: '道', note: '来自真实掌握状态' },
    { label: '知识证据', value: String(report?.sample_scope.knowledge_evidence_count ?? 0), unit: '条', note: '来自知识点关联记录' },
  ]
  return <div className="stats-grid">{metrics.map(metric => <Card key={metric.label}><span className="eyebrow">{metric.label}</span><strong className="metric">{metric.value}<small>{metric.unit}</small></strong><span className="metric-note">{metric.note}</span></Card>)}</div>
}

function Recommendations({ report }: { report: ParentReport | null }) {
  return <Card className="chart-card"><div className="section-heading"><div><span className="eyebrow">NEXT ACTIONS</span><h3>下一阶段建议</h3></div><Chip>有据可查</Chip></div>
    {report?.recommendations.length ? <div className="feedback-list">{report.recommendations.map(item => <p key={item}><span>✓</span>{item}</p>)}</div> : <p>当前记录没有支持具体建议的待巩固知识点，系统不会补造建议。</p>}
  </Card>
}

function KnowledgeSummary({ report }: { report: ParentReport | null }) {
  return <Card className="knowledge-card"><span className="eyebrow">EVIDENCE</span><h3>知识点证据</h3>
    {report?.knowledge_summary.map(item => <div className="skill" key={item.code}><div><span>{item.name}</span><strong>{item.latest_mastery}</strong></div><p className="tiny-muted">{item.evidence_count} 条证据 · {item.mistake_count} 次错误 · {item.effective_attempt_count} 次有效尝试 · 最高 {item.highest_hint_level} 级提示</p></div>)}
    {!report?.knowledge_summary.length && <p>还没有知识点学习证据。</p>}
    <div className="skill-note">这里只展示数据库中的真实学习证据 <span>✦</span></div>
  </Card>
}
