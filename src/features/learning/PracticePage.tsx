import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Chip, PageTitle, ProgressBar } from '../../components/ui'

const mathKeys = ['x', '−', '+', '=', '(', ')', '1', '2', '3', '⌫']

export function PracticePage() {
  const [answer, setAnswer] = useState('')
  const navigate = useNavigate()
  const appendKey = (key: string) => setAnswer(value => key === '⌫' ? value.slice(0, -1) : value + key)

  return <div className="page narrow">
    <PageTitle eyebrow="学习流程 · 03 / 04" title="换一道相似题试试" description="这次独立完成，写出每一步就好。" />
    <div className="step-progress"><Chip>相似题 1 / 2</Chip><ProgressBar value={66} label="相似题进度" /></div>
    <Card className="question-card"><Chip tone="green">巩固分配律</Chip><div className="equation">2(x + 4) = 3x − 1</div><p className="tiny-muted">先展开括号，再整理含 x 的项。</p></Card>
    <Card><label className="field-label" htmlFor="answer">你的答案</label><input id="answer" className="text-input answer-input" value={answer} onChange={event => setAnswer(event.target.value)} placeholder="在这里输入你的解题过程" />
      <div className="math-keypad" aria-label="数学输入键盘">{mathKeys.map(key => <button key={key} type="button" aria-label={key === '⌫' ? '删除' : key} onClick={() => appendKey(key)}>{key}</button>)}</div>
      <div className="form-foot"><span className="tiny-muted">已完成 0 / 3 步骤</span><Button onClick={() => navigate('/learn/feedback')}>提交这一步 →</Button></div>
    </Card>
  </div>
}
