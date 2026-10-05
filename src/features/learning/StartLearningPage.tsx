import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, PageTitle } from '../../components/ui'
import { createTutoringSession } from '../../services/tutoring'

export function StartLearningPage() {
  const [question, setQuestion] = useState('3(x − 2) = 2x + 5')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()

  const startSession = async () => {
    if (!question.trim()) {
      setError('请先输入一道完整题目。')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const result = await createTutoringSession(question.trim())
      navigate(`/learn/${result.session.id}/diagnosis`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '学习服务暂时不可用')
    } finally {
      setSubmitting(false)
    }
  }

  return <div className="page narrow">
    <PageTitle eyebrow="学习 · 新的一步" title="开始一次学习" description="拍题优先，也可以从相册导入或文字输入。" />
    <Card className="camera-card"><div className="camera-symbol" aria-hidden="true">◎</div><h2>图片识别即将接入</h2><p>当前版本先支持文字题目；OCR 将通过可替换服务接入，不要求腾讯云。</p><label className="button file-button">查看接入状态<input type="file" accept="image/*" aria-label="题目图片识别尚未接入" onChange={() => setError('图片识别尚未接入，请先把题目文字粘贴到下方。')} /></label></Card>
    <div className="input-divider"><span />或者输入题目<span /></div>
    <Card><label className="field-label" htmlFor="question">把题目写在这里</label><textarea id="question" rows={3} value={question} onChange={event => setQuestion(event.target.value)} />
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="form-foot"><span className="tiny-muted">先理解题目，不急着求答案</span><Button onClick={startSession}>{submitting ? '正在理解题目…' : '开始诊断 →'}</Button></div>
    </Card>
    <p className="privacy-note">🔒 题目仅用于本次学习</p>
  </div>
}
