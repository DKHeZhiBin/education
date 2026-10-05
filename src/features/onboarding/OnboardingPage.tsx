import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, Chip } from '../../components/ui'

const grades = ['初一', '初二', '初三']
const focusAreas = ['一元一次方程', '整式运算', '函数基础']

export function OnboardingPage() {
  const [grade, setGrade] = useState('初二')
  const [focusAreasSelected, setFocusAreasSelected] = useState<string[]>(['一元一次方程'])
  const toggleFocusArea = (area: string) => setFocusAreasSelected(current =>
    current.includes(area) ? current.filter(item => item !== area) : [...current, area],
  )

  return <main className="onboarding-wrap">
    <section className="welcome-card">
      <Link to="/onboarding" className="welcome-brand">数知伙伴</Link>
      <h1>先找到卡点，<br />再一步步学会。</h1>
      <p>我不会直接替你作答，会先了解你卡在哪里。</p>
      <div className="welcome-orbit orbit-one" /><div className="welcome-orbit orbit-two" /><span className="welcome-star">✳</span>
    </section>
    <section className="onboarding-form" aria-labelledby="onboarding-title">
      <Chip tone="green">约 2 分钟完成</Chip>
      <h2 id="onboarding-title">让我们更懂你的学习节奏</h2>
      <Card><h3>当前年级</h3><div className="choice-grid three" role="group" aria-label="当前年级">
        {grades.map(item => <button key={item} type="button" aria-pressed={grade === item} onClick={() => setGrade(item)} className={`choice ${grade === item ? 'selected' : ''}`}>{item}</button>)}
      </div></Card>
      <Card><h3>最需要帮助的方向</h3><div className="chip-row" role="group" aria-label="需要帮助的方向">
        {focusAreas.map(item => <button key={item} type="button" aria-pressed={focusAreasSelected.includes(item)} className={`chip selectable ${focusAreasSelected.includes(item) ? 'selected-chip' : ''}`} onClick={() => toggleFocusArea(item)}>{item}</button>)}
      </div></Card>
      <Button to="/home">进入数知伙伴 <span>→</span></Button>
    </section>
  </main>
}
