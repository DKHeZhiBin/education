import { useEffect, useState } from 'react'
import { Card, Chip, PageTitle, ProgressBar } from '../../components/ui'
import type { Mistake, MistakeStatus } from './data'
import { listLearningRecords, type LearningRecord } from '../../services/tutoring'

type MistakeFilter = '全部' | '待巩固' | '已掌握'
const filters: MistakeFilter[] = ['全部', '待巩固', '已掌握']

export function MistakesPage() {
  const [filter, setFilter] = useState<MistakeFilter>('全部')
  const [records, setRecords] = useState<LearningRecord[]>([])
  useEffect(() => { listLearningRecords().then(setRecords).catch(() => undefined) }, [])
  const liveMistakes = records.map(record => ({
    question: record.question,
    topic: record.knowledge_tags.join(' · ') || '待归类',
    status: record.mastery as MistakeStatus,
    mastery: record.mastery === '已掌握' ? 90 : 56,
    lastPracticed: record.date,
  }))
  const mistakes = liveMistakes
  const filteredMistakes = filter === '全部' ? mistakes : mistakes.filter(item => item.status === filter)
  return <div className="page">
    <PageTitle eyebrow="复习空间" title="错题本" description="记录错误原因与复习结果，不只收藏题目。" />
    <MistakeSummary mistakes={mistakes} />
    <div className="section-heading list-heading"><div><span className="eyebrow">YOUR REVIEW LIST</span><h2>最近需要回看的题目</h2></div>
      <div className="filters" role="group" aria-label="错题筛选">{filters.map(item => <button key={item} type="button" aria-pressed={filter === item} className={`filter ${filter === item ? 'active' : ''}`} onClick={() => setFilter(item)}>{item}</button>)}</div>
    </div>
    <div className="mistake-list" aria-live="polite">{filteredMistakes.map((item, index) => <MistakeCard key={item.question} item={item} index={index} />)}</div>
    {filteredMistakes.length === 0 && <Card><p>这个筛选条件下暂时没有题目。</p></Card>}
  </div>
}

function MistakeSummary({ mistakes }: { mistakes: Mistake[] }) {
  const pending = mistakes.filter(item => item.status !== '已掌握').length
  const mastered = mistakes.filter(item => item.status === '已掌握').length
  return <div className="mistake-overview">
    <Card className="amber-card"><span className="eyebrow">待复习</span><strong className="metric">{pending} <small>道</small></strong></Card>
    <Card className="teal-card"><span className="eyebrow">已掌握</span><strong className="metric">{mastered} <small>道</small></strong></Card>
    <Card className="blue-card"><span className="eyebrow">本周记录</span><strong className="metric">{mistakes.length} <small>道</small></strong></Card>
  </div>
}

function MistakeCard({ item, index }: { item: Mistake; index: number }) {
  const statusTone: Record<MistakeStatus, 'amber' | 'green' | 'blue'> = {
    '待巩固': 'amber', '复习中': 'blue', '已掌握': 'green',
  }
  return <Card className="mistake-item">
    <div className="mistake-title"><div><span className="item-number">{String(index + 1).padStart(2, '0')}</span><strong>{item.question}</strong></div><Chip tone={statusTone[item.status]}>{item.status}</Chip></div>
    <div className="mistake-meta"><span>{item.topic}</span><span>上次练习 · {item.lastPracticed}</span></div>
    <div className="mastery-row"><span>掌握度</span><strong>{item.mastery}%</strong></div>
    <ProgressBar value={item.mastery} tone={item.mastery > 80 ? 'teal' : 'blue'} label={`${item.topic}掌握度`} />
  </Card>
}
