import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button, Card, Chip, ServiceNotice } from '../../components/ui'
import { MathInline, MathMarkdown } from '../../components/MathMarkdown'
import { createClientTurnId, getTutoringSession, sendTutoringTurn, type TutoringSession } from '../../services/tutoring'
import { LearningWorkflow, WorkspaceHeading } from './LearningWorkspace'
import { buildSessionReview } from './sessionReview'

const hintCompletionLabels = ['独立完成', '在方向提示下完成', '在关键关系提示下完成', '在局部步骤提示下完成', '在完整讲解后完成']

function reflectionKey(sessionId: string) {
  return `learning-reflection:${sessionId}`
}

export function FeedbackPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const [session, setSession] = useState<TutoringSession | null>(null)
  const [reflection, setReflection] = useState('')
  const [reflectionSaved, setReflectionSaved] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!sessionId) {
      navigate('/learn/new', { replace: true })
      return
    }
    const saved = window.sessionStorage.getItem(reflectionKey(sessionId)) ?? ''
    setReflection(saved)
    setReflectionSaved(Boolean(saved))
    void getTutoringSession(sessionId)
      .then(setSession)
      .catch(cause => setError(cause instanceof Error ? cause.message : '无法读取本次学习复盘'))
  }, [navigate, sessionId])

  const review = useMemo(() => session ? buildSessionReview(session) : null, [session])

  const saveReflection = () => {
    if (!sessionId || !reflection.trim()) return
    window.sessionStorage.setItem(reflectionKey(sessionId), reflection.trim())
    setReflectionSaved(true)
  }

  const startSimilarPractice = async () => {
    if (!sessionId || generating) return
    setGenerating(true)
    setError('')
    try {
      const result = await sendTutoringTurn(sessionId, '生成一道同难度相似题', 'practice', createClientTurnId())
      navigate(`/learn/${result.session.id}/coach`, {
        state: { reply: result.reply, degradation: result.degraded ? { code: result.degradation_code, reason: result.degradation_reason } : null },
      })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '暂时无法生成相似题')
    } finally {
      setGenerating(false)
    }
  }

  if (!session || !review) return <div className="page learning-workspace-page">
    <WorkspaceHeading title="这题，连起来了" description="正在整理学生原思路、关键突破口和完整解法。" badge="复盘已保存" />
    {error ? <ServiceNotice title="学习复盘暂时无法读取" message={error} tone="error" /> : <p className="tiny-muted">正在读取学习记录…</p>}
  </div>

  const record = session.record
  const hintLevel = record?.hint_level ?? session.hint_level
  const completed = session.status === 'completed' && Boolean(record)
  return <div className="page learning-workspace-page">
    <WorkspaceHeading title="这题，连起来了" description="完成后复盘 · 看懂转折比记住答案重要。" badge={completed ? '复盘已保存' : '复盘预览'} />
    <LearningWorkflow activeStep={6} completedThrough={5} />

    <div className="review-hero-grid">
      <Card className="review-answer-card">
        <Chip tone="green">{completed ? hintCompletionLabels[Math.min(hintLevel, 4)] : `当前已使用 ${hintLevel} 级提示`}</Chip>
        <MathMarkdown className="review-answer" source={review.answer} />
        <p>保留你的原始步骤，再与经过验证的完整解法对照。</p>
      </Card>
      <Card className="review-breakthrough-card">
        <h2>这道题真正的转折</h2>
        <strong><MathInline source={review.breakthroughTitle} /></strong>
        <MathMarkdown source={review.breakthroughDescription} />
        <small><MathInline source={review.breakthroughReason} /></small>
      </Card>
    </div>

    <div className="review-content-grid">
      <Card className="review-reasoning-card">
        <h2>回看学生原思路与完整关键推理</h2>
        <section className="original-thought-block">
          <div><strong>学生原思路</strong><Chip tone="green">原记录</Chip></div>
          <MathMarkdown source={review.studentThought} />
          <small>来自本次真实作答与开始页草稿，不会被标准解法覆盖。</small>
        </section>
        <div className="review-method-heading"><div><strong><MathInline source={review.methodName} /></strong><MathMarkdown source={review.methodSummary} /></div><span>{review.verification.passed ? '✓ 已通过验证' : '验证覆盖有限'}</span></div>
        <div className="review-step-list">{review.steps.map((step, index) => <article key={`${step.title}-${index}`} className={`review-step ${step.emphasis}`}>
          <div><strong>{step.title}</strong><span>{step.emphasis === 'breakthrough' ? '关键突破' : step.badge}</span></div>
          {step.result && <MathMarkdown source={step.result} />}
          {step.justification && <small><MathInline source={step.justification} /></small>}
        </article>)}</div>
      </Card>

      <aside className="review-side-column">
        <Card className="review-retell-card">
          <h2>换成你的话，说说为什么</h2>
          <MathMarkdown source={review.breakthroughReason} />
          <textarea rows={4} value={reflection} onChange={event => { setReflection(event.target.value); setReflectionSaved(false) }} placeholder="用自己的话复述关键连接…" />
          <button className="button button-secondary" type="button" disabled={!reflection.trim()} onClick={saveReflection}>{reflectionSaved ? '✓ 我的复述已保存' : '保存我的复述'}</button>
        </Card>
        <Card className="review-observation-card">
          <h2>本次学习观察</h2>
          <p className="positive">✓ 有效尝试 · {record?.attempt_count ?? session.attempts} 次</p>
          <p className={hintLevel > 0 ? 'assisted' : 'positive'}>{hintLevel > 0 ? '◐' : '✓'} 最高提示等级 · {hintLevel} 级</p>
          <p>当前掌握状态：{record?.mastery || '待继续验证'}</p>
          <small>这是一题中的表现，还需要结构相似题验证，不等于已经稳定掌握。</small>
        </Card>
        <Card className="review-evidence-card">
          <h2>解法验证与来源依据</h2>
          <div className="verification-summary"><strong>{review.verification.passed ? '✓ 解法复核通过' : '◐ 部分验证覆盖'}</strong><span>{review.verification.verifier}</span><MathMarkdown source={review.verification.coverage} />{review.verification.evidence && <small><MathInline source={review.verification.evidence} /></small>}</div>
          {review.sources.length ? <ul>{review.sources.map(source => <li key={`${source.document_id}:${source.chunk_id ?? ''}`}><div>{source.source_url ? <a href={source.source_url} target="_blank" rel="noreferrer">{source.title}</a> : <strong>{source.title}</strong>}<span>{source.version ? `版本 ${source.version}` : '版本未标注'}</span></div>{source.locator && <small>{source.locator}</small>}</li>)}</ul> : <p className="no-review-sources">本轮没有使用外部教材片段；依据来自题目条件、独立解题与数学验证工具。</p>}
        </Card>
        {error && <p className="form-error" role="alert">{error}</p>}
        <Button disabled={generating} onClick={() => void startSimilarPractice()}>{generating ? '正在生成…' : '再练一道验证迁移 →'}</Button>
        <button className="text-button" type="button" onClick={() => navigate(`/learn/${sessionId}/coach`)}>探索另一种成立的解法 →</button>
      </aside>
    </div>
    <footer className="workspace-footer"><span>数知伙伴 · 不替你跳过思考，也不覆盖你的解法。</span><span>使用帮助 ↗</span></footer>
  </div>
}
