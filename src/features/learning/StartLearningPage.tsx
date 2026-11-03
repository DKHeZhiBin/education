import { useEffect, useState, type ChangeEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Button, Card, ServiceNotice } from '../../components/ui'
import { MathInline, MathMarkdown } from '../../components/MathMarkdown'
import { LearningWorkflow, WorkspaceHeading } from './LearningWorkspace'
import { PRODUCT_SCOPE_LABEL } from '../../config/productScope'
import {
  confirmProblemImageOCR,
  createTutoringSession,
  getLearningReadiness,
  getLLMModels,
  getProblemImageUpload,
  TutoringHttpError,
  uploadProblemImage,
  type LLMModelOption,
  type ProblemImageUpload,
  type RuntimeDegradation,
} from '../../services/tutoring'

type Notice = { title: string; message: string; tone: 'warning' | 'error' | 'info' }
type StartingPoint = 'no_idea' | 'partial' | 'alternate'

const DEMO_QUESTION = '求极限：当 x → 0 时，(eˣ − 1 − x) / x²。'
const MAX_IMAGE_BYTES = 10 * 1024 * 1024

const startingPoints: Array<{ id: StartingPoint; title: string; description: string }> = [
  { id: 'no_idea', title: '完全没思路', description: '一起找一个能出发的条件' },
  { id: 'partial', title: '做到一半', description: '保留已有步骤，接着往下想' },
  { id: 'alternate', title: '想试试另一种方法', description: '成立的不同解法，也值得探索' },
]

export function StartLearningPage() {
  const [searchParams] = useSearchParams()
  const isMethodRecognition = searchParams.get('mode') === 'method-recognition'
  const knowledgePointCode = searchParams.get('knowledge_point')
  const knowledgePointName = searchParams.get('knowledge_name')
  const isKnowledgeLearning = Boolean(knowledgePointCode && knowledgePointName)
  const [question, setQuestion] = useState(() => isMethodRecognition
    ? ''
    : isKnowledgeLearning
      ? `请通过一道${PRODUCT_SCOPE_LABEL}典型题，引导我学习“${knowledgePointName}”。请先检查相关先修知识，再让我自己建立核心关系。`
      : DEMO_QUESTION)
  const [startingPoint, setStartingPoint] = useState<StartingPoint>(() => isMethodRecognition || isKnowledgeLearning ? 'no_idea' : 'partial')
  const [existingSteps, setExistingSteps] = useState(() => isMethodRecognition || isKnowledgeLearning ? '' : '利用展开式 eˣ = 1 + x + x²/2 + o(x²)，先整理分子。')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [models, setModels] = useState<LLMModelOption[]>([])
  const [modelId, setModelId] = useState('')
  const [modelNotice, setModelNotice] = useState<Notice | null>(null)
  const [ragNotice, setRagNotice] = useState<Notice | null>(null)
  const [readinessDegradation, setReadinessDegradation] = useState<RuntimeDegradation | null>(null)
  const [serviceNotice, setServiceNotice] = useState<Notice | null>(null)
  const [imageUpload, setImageUpload] = useState<ProblemImageUpload | null>(null)
  const [imageUploading, setImageUploading] = useState(false)
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string | null>(null)
  const [formulaDrafts, setFormulaDrafts] = useState<string[]>([])
  const [ocrDirty, setOCRDirty] = useState(false)
  const [ocrConfirming, setOCRConfirming] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    void getLLMModels().then(catalog => {
      setModels(catalog.models)
      const selected = catalog.models.find(item => item.id === catalog.default_model_id && item.available)
        ?? catalog.models.find(item => item.available)
      setModelId(selected?.id ?? '')
      setModelNotice(selected ? null : {
        title: '当前没有可用模型',
        message: '题目会保留在当前页面；内置演示题仍可使用安全降级流程。',
        tone: 'warning',
      })
    }).catch(() => setModelNotice({
      title: '模型列表暂时无法读取',
      message: '题目内容已保留，请稍后重试。',
      tone: 'error',
    }))

    void getLearningReadiness().then(readiness => {
      const requiredUnavailable = Object.values(readiness.checks).some(check => check.required && check.status !== 'ready')
      setServiceNotice(requiredUnavailable ? {
        title: '学习服务暂时不可用',
        message: '必要的数据库或会话服务尚未就绪。你的题目不会被清空。',
        tone: 'error',
      } : null)
      const ragUnavailable = readiness.checks.rag.status === 'not_ready'
      setRagNotice(ragUnavailable ? {
        title: '知识检索当前处于降级状态',
        message: '仍可继续学习，本轮可能不会引用题库依据。',
        tone: 'warning',
      } : null)
      setReadinessDegradation(ragUnavailable ? {
        code: 'knowledge_retrieval_degraded',
        reason: '知识检索服务尚未就绪，当前使用基础教学链路。',
      } : null)
    }).catch(() => setServiceNotice({
      title: '无法确认学习服务状态',
      message: '网络连接可能中断。你的题目已经保留，可以稍后重试。',
      tone: 'error',
    }))
  }, [])

  useEffect(() => () => {
    if (imagePreviewUrl) URL.revokeObjectURL(imagePreviewUrl)
  }, [imagePreviewUrl])

  useEffect(() => {
    if (!imageUpload || !['pending', 'processing'].includes(imageUpload.status)) return
    let cancelled = false
    let inFlight = false
    const poll = () => {
      if (inFlight) return
      inFlight = true
      void getProblemImageUpload(imageUpload.id).then(latest => {
        if (cancelled) return
        setImageUpload(latest)
        if (latest.status === 'ready' && latest.extracted_text) setQuestion(latest.extracted_text)
      }).catch(() => {
        // 中文：短暂网络失败时保留图片和题目，由下一次轮询或手动刷新恢复。
        // English: Preserve the image and draft on transient polling failures.
      }).finally(() => {
        inFlight = false
      })
    }
    const timer = window.setInterval(poll, 1200)
    poll()
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [imageUpload?.id, imageUpload?.status])

  useEffect(() => {
    if (imageUpload?.status !== 'ready') return
    setFormulaDrafts(imageUpload.recognized_formulas)
    setOCRDirty(false)
  }, [imageUpload?.id, imageUpload?.status, imageUpload?.updated_at])

  const selectProblemImage = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (file.type && !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      setError('仅支持 JPEG、PNG 或 WebP 图片。')
      return
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setError('图片不能超过 10 MB。')
      return
    }
    if (imagePreviewUrl) URL.revokeObjectURL(imagePreviewUrl)
    setImagePreviewUrl(URL.createObjectURL(file))
    setImageUpload(null)
    setFormulaDrafts([])
    setOCRDirty(false)
    setImageUploading(true)
    setError('')
    if (question === DEMO_QUESTION) setQuestion('')
    try {
      const uploaded = await uploadProblemImage(file)
      setImageUpload(uploaded)
      if (uploaded.status === 'ready' && uploaded.extracted_text) setQuestion(uploaded.extracted_text)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '图片上传失败，请重新选择。')
    } finally {
      setImageUploading(false)
    }
  }

  const refreshImageStatus = async () => {
    if (!imageUpload) return
    setImageUploading(true)
    setError('')
    try {
      const latest = await getProblemImageUpload(imageUpload.id)
      setImageUpload(latest)
      if (latest.status === 'ready' && latest.extracted_text) setQuestion(latest.extracted_text)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '无法读取图片状态，请稍后重试。')
    } finally {
      setImageUploading(false)
    }
  }

  const confirmOCRResult = async () => {
    if (!imageUpload || imageUpload.status !== 'ready') return
    setOCRConfirming(true)
    setError('')
    try {
      const confirmed = await confirmProblemImageOCR(imageUpload.id, question.trim(), formulaDrafts)
      setImageUpload(confirmed)
      setQuestion(confirmed.extracted_text ?? question)
      setFormulaDrafts(confirmed.recognized_formulas)
      setOCRDirty(false)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '识别结果确认失败，请检查公式后重试。')
    } finally {
      setOCRConfirming(false)
    }
  }

  const startSession = async () => {
    if (!question.trim()) {
      setError('请先确认一道完整题目。')
      return
    }
    if (imageUpload?.status === 'ready' && (!imageUpload.student_confirmed_at || ocrDirty)) {
      setError('请先对照原图检查并确认 OCR 识别结果。')
      return
    }
    setSubmitting(true)
    setError('')
    setServiceNotice(null)
    try {
      const result = await createTutoringSession(question.trim(), modelId || undefined)
      window.sessionStorage.setItem(`learning-start:${result.session.id}`, JSON.stringify({
        mode: isMethodRecognition ? 'method-recognition' : isKnowledgeLearning ? 'knowledge-point-learning' : 'guided-learning',
        startingPoint,
        existingSteps: existingSteps.trim(),
        knowledgePointCode,
        knowledgePointName,
      }))
      navigate(`/learn/${result.session.id}/diagnosis`, {
        state: {
          degradation: result.degraded ? {
            code: result.degradation_code,
            reason: result.degradation_reason,
          } : readinessDegradation,
        },
      })
    } catch (cause) {
      if (cause instanceof TutoringHttpError && cause.code === 'llm_model_unavailable') {
        setModelNotice({ title: '所选模型当前不可用', message: `${cause.message}。题目和选择已保留。`, tone: 'warning' })
      } else {
        setServiceNotice({ title: '学习服务暂时不可用', message: `${cause instanceof Error ? cause.message : '请求未能完成'}。题目内容已保留。`, tone: 'error' })
      }
    } finally {
      setSubmitting(false)
    }
  }

  return <div className="page learning-workspace-page">
    <WorkspaceHeading title={isMethodRecognition ? '识别题目中的思想与方法' : '综合题，一起想'} description={isMethodRecognition ? '先观察题目结构，再判断主方法与可以关联的思考方式。' : '会知识，也能连起思路。先确认题目，再从你走到的地方出发。'} badge={isMethodRecognition ? '题目待确认' : '草稿已保留'} />
    <LearningWorkflow activeStep={1} />
    {serviceNotice && <ServiceNotice {...serviceNotice} />}
    {modelNotice && <ServiceNotice {...modelNotice} />}
    {ragNotice && <ServiceNotice {...ragNotice} />}

    <section className="workspace-callout">
      <div><h2>不急着看答案。一起弄清楚，下一步为什么往这里想。</h2><p>你的有效推导会被保留；成立的不同方法，都可以接着探索。</p></div>
      <strong>已知 → 连接 → 目标</strong>
    </section>

    <div className="problem-confirmation-grid">
      <div className="workspace-column">
        <Card className="upload-recognition-card">
          <h2>上传与识别</h2>
          <div className="image-upload-actions">
            <label className={`button button-secondary file-button ${imageUploading ? 'is-disabled' : ''}`}>
              {imageUploading ? '正在上传…' : '＋ 上传题目'}
              <input type="file" accept="image/jpeg,image/png,image/webp" aria-label="选择题目图片" disabled={imageUploading} onChange={selectProblemImage} />
            </label>
            <span>支持 JPEG、PNG、WebP 或粘贴正文</span>
            {imageUpload && <button className="text-button" type="button" disabled={imageUploading} onClick={() => void refreshImageStatus()}>刷新状态</button>}
          </div>
          {imageUpload && <p className="recognition-state">✓ {imageUpload.status_message}</p>}
          {imageUpload?.status === 'ready' && <p className="tiny-muted">
            已识别 {imageUpload.recognized_formulas.length} 个公式
            {imageUpload.ocr_confidence !== null ? ` · 置信度 ${Math.round(imageUpload.ocr_confidence * 100)}%` : ''}
            ，请核对后再开始。
          </p>}
          {imageUpload?.status === 'ready' && <div className={`formula-validation ${imageUpload.formula_validation_status}`}>
            <strong>{imageUpload.formula_validation_status === 'valid' ? '公式结构检查通过' : imageUpload.formula_validation_status === 'invalid' ? '发现需要修正的公式结构' : '有公式细节需要核对'}</strong>
            {imageUpload.formula_validation_issues.length > 0 && <ul>
              {imageUpload.formula_validation_issues.map((issue, index) => <li key={`${issue.code}-${index}`}>
                {issue.formula_index !== null ? `公式 ${issue.formula_index + 1}：` : ''}{issue.message}
              </li>)}
            </ul>}
          </div>}
        </Card>

        <Card className="editable-problem-card">
          <h2>当前题目</h2>
          <div className="problem-meta"><span>综合题</span><span>{imageUpload?.student_confirmed_at && !ocrDirty ? '已确认' : '待确认'}</span></div>
          {imagePreviewUrl && <img className="problem-image-preview light" src={imagePreviewUrl} alt="题目预览" />}
          <label className="field-label" htmlFor="question">确认或修改识别后的题目</label>
          <textarea id="question" rows={7} value={question} onChange={event => { setQuestion(event.target.value); if (imageUpload?.status === 'ready') setOCRDirty(true) }} />
          {question.trim() && <div className="problem-math-preview"><span>数学排版预览</span><MathMarkdown source={question} /></div>}
          {imageUpload?.status === 'ready' && <div className="formula-correction-list">
            <div className="formula-correction-heading"><strong>识别出的公式</strong><span>使用 LaTeX 修正</span></div>
            {formulaDrafts.length === 0 && <p className="tiny-muted">没有单独识别出公式，请重点核对上方题目正文。</p>}
            {formulaDrafts.map((formula, index) => <div className="formula-correction-row" key={index}>
              <label>
                <span>公式 {index + 1}</span>
                <input className="text-input" value={formula} onChange={event => {
                  setFormulaDrafts(current => current.map((item, itemIndex) => itemIndex === index ? event.target.value : item))
                  setOCRDirty(true)
                }} />
                {formula.trim() && <MathInline className="formula-draft-preview" source={`\\(${formula}\\)`} />}
              </label>
              <button className="text-button" type="button" onClick={() => { setFormulaDrafts(current => current.filter((_, itemIndex) => itemIndex !== index)); setOCRDirty(true) }}>删除</button>
            </div>)}
            <button className="text-button formula-add-button" type="button" onClick={() => { setFormulaDrafts(current => [...current, '']); setOCRDirty(true) }}>＋ 添加遗漏公式</button>
            <Button disabled={ocrConfirming || !question.trim()} onClick={() => void confirmOCRResult()}>
              {ocrConfirming ? '正在复检…' : imageUpload.student_confirmed_at && !ocrDirty ? '✓ 已确认识别结果' : '确认识别结果'}
            </Button>
          </div>}
          <p className="tiny-muted">关注范围与目标条件，不急着求答案。</p>
        </Card>
      </div>

      <div className="workspace-column learning-start-column">
        <h2>你现在走到哪里了？</h2>
        <div className="starting-point-list" role="radiogroup" aria-label="选择学习起点">
          {startingPoints.map(option => <button key={option.id} className={`starting-point-option ${startingPoint === option.id ? 'selected' : ''}`} type="button" role="radio" aria-checked={startingPoint === option.id} onClick={() => { setStartingPoint(option.id); if (option.id === 'no_idea') setExistingSteps('') }}>
            <span><strong>{option.title}</strong><small>{option.description}</small></span><i aria-hidden="true" />
          </button>)}
        </div>
        {startingPoint !== 'no_idea' && <Card className="existing-steps-card">
          <h2>{startingPoint === 'alternate' ? '写下想尝试的方法' : '接续已有步骤'}</h2>
          <textarea rows={5} value={existingSteps} onChange={event => setExistingSteps(event.target.value)} placeholder="写下已经完成的推导或准备尝试的方法…" />
          <p>我们不会从头覆盖你的工作。</p>
        </Card>}
        <label className="field-label" htmlFor="llm-model">本次辅导模型</label>
        <select className="text-input" id="llm-model" value={modelId} onChange={event => setModelId(event.target.value)} disabled={!models.some(item => item.available)}>
          {!models.some(item => item.available) && <option value="">使用服务端默认配置</option>}
          {models.map(item => <option key={item.id} value={item.id} disabled={!item.available}>{item.display_name}{item.is_default ? '（默认）' : ''}{item.available ? '' : '（未配置）'}</option>)}
        </select>
        {error && <p className="form-error" role="alert">{error}</p>}
        <Button disabled={submitting || imageUploading} onClick={startSession}>{submitting ? '正在建立学习空间…' : startingPoint === 'partial' ? '从我的步骤继续 →' : '开始一起思考 →'}</Button>
      </div>
    </div>
    <footer className="workspace-footer"><span>数知伙伴 · 不替你跳过思考，也不覆盖你的解法。</span><span>使用帮助 ↗</span></footer>
  </div>
}
