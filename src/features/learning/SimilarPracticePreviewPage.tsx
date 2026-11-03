import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { Button, Card, Chip, ServiceNotice } from '../../components/ui'
import { MathInline, MathMarkdown } from '../../components/MathMarkdown'
import { getTutoringSession, type RuntimeDegradation, type TutoringSession } from '../../services/tutoring'
import { LearningWorkflow, WorkspaceHeading } from './LearningWorkspace'

type SimilarPracticeContext = {
  knowledgePointCode?: string
  knowledgePointName?: string
  sourceContentKey?: string
  sourceContentTitle?: string
  practiceDifficulty?: 'easy' | 'medium' | 'hard'
}

const DIFFICULTY_LABELS = { easy: '简单', medium: '中等', hard: '困难' } as const

/** 中文：展示刚生成的相似题，并让学生确认后再进入辅导流程。 English: Displays a newly generated similar problem before the learner enters tutoring. */
export function SimilarPracticePreviewPage() {
  const { sessionId = '' } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const [session, setSession] = useState<TutoringSession | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const degradation = (location.state as { degradation?: RuntimeDegradation | null } | null)?.degradation ?? null

  const context = useMemo(() => {
    if (!sessionId) return null
    try {
      const raw = window.sessionStorage.getItem(`learning-start:${sessionId}`)
      return raw ? JSON.parse(raw) as SimilarPracticeContext : null
    } catch {
      return null
    }
  }, [sessionId])

  /** 中文：从 API 恢复题目，使页面刷新后仍可继续。 English: Restores the problem from the API so refreshes remain recoverable. */
  const loadSession = async () => {
    if (!sessionId) return
    setLoading(true)
    setError('')
    try {
      setSession(await getTutoringSession(sessionId))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '暂时无法读取生成的题目。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadSession() }, [sessionId])

  /** 中文：确认题目后进入现有诊断与引导流程。 English: Enters the existing diagnosis and guided tutoring flow after confirmation. */
  const beginThinking = () => {
    if (!sessionId) return
    navigate(`/learn/${sessionId}/diagnosis`, { state: { degradation } })
  }

  if (loading) return <div className="page learning-workspace-page"><Card className="similar-practice-loading">正在读取刚刚生成的题目…</Card></div>

  if (!session || error) return <div className="page learning-workspace-page">
    <WorkspaceHeading title="相似题暂时无法打开" description="生成记录仍会保留，可以重新读取。" badge="等待恢复" />
    <ServiceNotice title="没有读取到题目" message={error || '学习会话不存在或已经过期。'} tone="error" />
    <div className="similar-practice-error-actions"><Button onClick={() => void loadSession()}>重新读取</Button><Button secondary onClick={() => navigate(-1)}>返回知识点</Button></div>
  </div>

  return <div className="page learning-workspace-page similar-practice-preview-page">
    <WorkspaceHeading title="为你生成了一道相似题" description="先完整读一遍题目，确认后再开始建立解题思路。" badge="题目已生成" />
    <LearningWorkflow activeStep={1} />
    {degradation?.reason && <ServiceNotice title="本轮部分能力处于降级状态" message={degradation.reason} tone="warning" />}

    <div className="similar-practice-preview-grid">
      <Card className="similar-practice-question-card">
        <div className="similar-practice-question-heading">
          <div><span className="eyebrow">SIMILAR PRACTICE</span><h2>相似练习</h2></div>
          <div className="problem-meta"><Chip>{session.profile.grade}</Chip><Chip tone="amber">{context?.practiceDifficulty ? DIFFICULTY_LABELS[context.practiceDifficulty] : '中等'}</Chip><Chip tone="green">{context?.knowledgePointName || '同知识点'}</Chip></div>
        </div>
        <MathMarkdown className="similar-practice-question" source={session.question} />
        <div className="similar-practice-generation-note">
          <strong>这道题怎样生成？</strong>
          <p>系统保留原题型的知识点和解题框架，改变具体条件，再通过教学 Agent 重新分析题意与解题路线。</p>
        </div>
      </Card>

      <Card className="similar-practice-source-card">
        <span className="eyebrow">SOURCE</span>
        <h2>生成依据</h2>
        <dl>
          <div><dt>知识点</dt><dd><MathInline source={context?.knowledgePointName || '当前知识点'} /></dd></div>
          <div><dt>原题型</dt><dd><MathInline source={context?.sourceContentTitle || '已发布例题'} /></dd></div>
          <div><dt>学习阶段</dt><dd>{session.profile.grade}</dd></div>
          <div><dt>题目难度</dt><dd>{context?.practiceDifficulty ? DIFFICULTY_LABELS[context.practiceDifficulty] : '中等'}</dd></div>
        </dl>
        <p>这里不展示答案。进入辅导后，系统会根据你的实际尝试逐级提供提示。</p>
        <Button onClick={beginThinking}>开始思考这道题 →</Button>
        <Button secondary onClick={() => navigate(-1)}>返回知识点</Button>
      </Card>
    </div>

    <footer className="workspace-footer"><span>相似题仅用于本次学习会话，不会自动进入正式题库。</span><span>先读题，再决定从哪里出发。</span></footer>
  </div>
}
