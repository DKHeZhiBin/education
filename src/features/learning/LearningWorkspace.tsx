import type { ReactNode } from 'react'
import { MathMarkdown } from '../../components/MathMarkdown'
import { Card, Chip } from '../../components/ui'

const WORKFLOW_STEPS = [
  '确认题目',
  '接续步骤',
  '一起思考',
  '思路地图',
  '按需提示',
  '完成复盘',
  '迁移练习',
]

export function WorkspaceHeading({ title, description, badge = '草稿已保留' }: {
  title: string
  description: string
  badge?: string
}) {
  return <header className="workspace-heading">
    <div><h1>{title}</h1><p>{description}</p></div>
    <Chip tone="green">{badge}</Chip>
  </header>
}

export function LearningWorkflow({ activeStep, completedThrough = 0 }: {
  activeStep: number
  completedThrough?: number
}) {
  return <ol className="learning-workflow" aria-label="学习流程">
    {WORKFLOW_STEPS.map((step, index) => {
      const number = index + 1
      const completed = number <= completedThrough
      return <li key={step} className={number === activeStep ? 'active' : completed ? 'completed' : ''}>
        <span>{completed ? '✓' : String(number).padStart(2, '0')}</span>{step}
      </li>
    })}
  </ol>
}

export function ProblemSnapshot({ question, children }: {
  question: string
  children?: ReactNode
}) {
  return <Card className="problem-snapshot">
    <h2>当前题目</h2>
    <div className="problem-meta"><Chip>综合题</Chip><Chip tone="green">已确认</Chip></div>
    <MathMarkdown className="problem-statement" source={question || '正在读取题目…'} />
    <small>关注范围与目标条件，不急着求答案。</small>
    {children}
  </Card>
}
