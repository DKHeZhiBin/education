import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, Chip } from '../../components/ui'

const focusAreas = ['函数、极限与连续', '一元函数微分学', '一元函数积分学', '多元函数微积分']

export function OnboardingPage() {
  const [focusAreasSelected, setFocusAreasSelected] = useState<string[]>(['函数、极限与连续'])
  const toggleFocusArea = (area: string) => setFocusAreasSelected(current =>
    current.includes(area) ? current.filter(item => item !== area) : [...current, area],
  )

  return <main className="onboarding-wrap">
    <section className="welcome-card">
      <Link to="/onboarding" className="welcome-brand">数知伙伴</Link>
      <h1>学高数，先连起思路，<br />再完成推导。</h1>
      <p>我会从你的已有步骤出发，陪你理解大学高数中的关键关系。</p>
      <div className="welcome-orbit orbit-one" /><div className="welcome-orbit orbit-two" /><span className="welcome-star">✳</span>
    </section>
    <section className="onboarding-form" aria-labelledby="onboarding-title">
      <Chip tone="green">约 2 分钟完成</Chip>
      <h2 id="onboarding-title">让我们更懂你的学习节奏</h2>
      <Card><h3>最需要帮助的方向</h3><div className="chip-row" role="group" aria-label="需要帮助的方向">
        {focusAreas.map(item => <button key={item} type="button" aria-pressed={focusAreasSelected.includes(item)} className={`chip selectable ${focusAreasSelected.includes(item) ? 'selected-chip' : ''}`} onClick={() => toggleFocusArea(item)}>{item}</button>)}
      </div></Card>
      <Button to="/home">进入数知伙伴 <span>→</span></Button>
    </section>
  </main>
}
