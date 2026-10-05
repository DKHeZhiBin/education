export type MistakeStatus = '待巩固' | '复习中' | '已掌握'

export type Mistake = {
  question: string
  topic: string
  status: MistakeStatus
  mastery: number
  lastPracticed: string
}

// Prototype-only examples. Replace with authorized learning-history API data.
export const demoMistakes: Mistake[] = [
  { question: '3(x − 2) = 2x + 5', topic: '分配律', status: '待巩固', mastery: 56, lastPracticed: '9 月 21 日' },
  { question: '−2(3x − 4) = 10', topic: '负号与括号', status: '复习中', mastery: 62, lastPracticed: '9 月 20 日' },
  { question: '5x + 7 = 2x − 8', topic: '移项与符号', status: '已掌握', mastery: 91, lastPracticed: '9 月 19 日' },
]

export const demoWeek = [
  { day: '一', minutes: 22 }, { day: '二', minutes: 52 }, { day: '三', minutes: 14 },
  { day: '四', minutes: 67 }, { day: '五', minutes: 43 }, { day: '六', minutes: 84 }, { day: '日', minutes: 33 },
]

export const demoKnowledge = [
  { name: '一元一次方程', mastery: 76 },
  { name: '整式运算', mastery: 64 },
  { name: '函数基础', mastery: 82 },
]
