import { useState, type FormEvent } from 'react'
import { Button, Card } from '../../components/ui'
import {
  createClientTurnId,
  reportTutoringContentIssue,
  TutoringHttpError,
  type ContentIssueType,
} from '../../services/tutoring'

const issueOptions: Array<{ value: ContentIssueType; label: string }> = [
  { value: 'incorrect_answer', label: '答案可能有误' },
  { value: 'answer_conflict', label: '不同答案相互冲突' },
  { value: 'incorrect_question', label: '题目或条件有误' },
  { value: 'ambiguous_content', label: '题目存在歧义' },
  { value: 'incorrect_hint', label: '提示或讲解有误' },
  { value: 'other', label: '其他问题' },
]

export function ContentIssueReporter({
  sessionId,
  problemId,
}: {
  sessionId: string
  problemId?: string | null
}) {
  const [open, setOpen] = useState(false)
  const [issueType, setIssueType] = useState<ContentIssueType>('incorrect_answer')
  const [description, setDescription] = useState('')
  const [clientReportId, setClientReportId] = useState(createClientTurnId)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [submitted, setSubmitted] = useState(false)

  const updateDraft = (next: { issueType?: ContentIssueType; description?: string }) => {
    if (next.issueType !== undefined) setIssueType(next.issueType)
    if (next.description !== undefined) setDescription(next.description)
    setClientReportId(createClientTurnId())
    setError('')
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const detail = description.trim()
    if (detail.length < 3) {
      setError('请用至少 3 个字说明你发现的问题。')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      await reportTutoringContentIssue(sessionId, {
        problem_id: problemId,
        issue_type: issueType,
        description: detail,
        client_report_id: clientReportId,
      })
      setSubmitted(true)
    } catch (cause) {
      if (cause instanceof TutoringHttpError && cause.code === 'invalid_content_issue_reference') {
        setError('当前会话没有可重新验证的题库内容，暂时无法提交此类报告。')
      } else {
        setError(cause instanceof Error ? cause.message : '报告提交失败，请稍后重试。')
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (submitted) {
    return <div className="content-issue-success" role="status">
      <span>✓</span>
      <div><strong>问题已记录</strong><p>相关题库内容已进入重新验证流程，感谢你的反馈。</p></div>
    </div>
  }

  return <div className="content-issue-reporter">
    {!open && <button className="content-issue-trigger" type="button" onClick={() => setOpen(true)}>
      发现题目或答案有误？报告问题
    </button>}
    {open && <Card className="content-issue-form-card">
      <form onSubmit={submit}>
        <div className="content-issue-heading">
          <div><span className="eyebrow">内容反馈</span><h3>报告题目或答案错误</h3></div>
          <button type="button" className="content-issue-close" aria-label="关闭报告表单" onClick={() => setOpen(false)}>×</button>
        </div>
        <label className="field-label" htmlFor={`issue-type-${sessionId}`}>问题类型</label>
        <select
          className="text-input"
          id={`issue-type-${sessionId}`}
          value={issueType}
          disabled={submitting}
          onChange={event => updateDraft({ issueType: event.target.value as ContentIssueType })}
        >
          {issueOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
        <label className="field-label content-issue-description-label" htmlFor={`issue-description-${sessionId}`}>具体说明</label>
        <textarea
          id={`issue-description-${sessionId}`}
          rows={3}
          maxLength={2000}
          value={description}
          disabled={submitting}
          placeholder="例如：第二个根代回原方程后不成立"
          onChange={event => updateDraft({ description: event.target.value })}
        />
        <div className="content-issue-form-meta">
          <span>反馈会绑定本次学习会话，并触发独立重新验证。</span>
          <span>{description.length} / 2000</span>
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="content-issue-actions">
          <button type="button" className="text-button" disabled={submitting} onClick={() => setOpen(false)}>取消</button>
          <Button type="submit" disabled={submitting || description.trim().length < 3}>{submitting ? '正在提交…' : '提交报告'}</Button>
        </div>
      </form>
    </Card>}
  </div>
}
