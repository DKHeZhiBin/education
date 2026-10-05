import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Button, Card, Chip } from '../../components/ui'
import {
  confirmEmailVerification,
  login,
  refreshAccessToken,
  register,
  requestEmailVerification,
  requestPasswordReset,
  resetPassword,
} from '../../services/auth'

type AuthMode = 'login' | 'register' | 'forgot' | 'reset' | 'message'

export function AuthPage() {
  const [searchParams] = useSearchParams()
  const resetToken = searchParams.get('reset_token')
  const verifyToken = searchParams.get('verify_token')
  const [mode, setMode] = useState<AuthMode>(resetToken ? 'reset' : 'login')
  const [role, setRole] = useState<'student' | 'guardian'>('student')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [message, setMessage] = useState('')
  const [developmentUrl, setDevelopmentUrl] = useState<string | null>(null)
  const [canResendVerification, setCanResendVerification] = useState(false)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    if (verifyToken) {
      setSubmitting(true)
      void confirmEmailVerification(verifyToken)
        .then(() => {
          setMessage('邮箱验证完成，现在可以登录了。')
          setCanResendVerification(false)
          setMode('message')
          navigate('/auth', { replace: true })
        })
        .catch(cause => setError(cause instanceof Error ? cause.message : '邮箱验证失败'))
        .finally(() => setSubmitting(false))
      return
    }
    if (!resetToken) {
      void refreshAccessToken()
        .then(() => navigate('/home', { replace: true }))
        .catch(() => undefined)
    }
  }, [navigate, resetToken, verifyToken])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    setMessage('')
    setDevelopmentUrl(null)
    try {
      if (mode === 'register') {
        const result = await register({
          email,
          password,
          role,
          display_name: displayName,
          grade_band: role === 'student' ? 'middle' : undefined,
        })
        setMessage(result.message)
        setDevelopmentUrl(result.development_verification_url)
        setCanResendVerification(true)
        setMode('message')
      } else if (mode === 'forgot') {
        const result = await requestPasswordReset(email)
        setMessage(result.message)
        setDevelopmentUrl(result.development_action_url)
        setCanResendVerification(false)
        setMode('message')
      } else if (mode === 'reset' && resetToken) {
        await resetPassword(resetToken, newPassword)
        setMessage('密码已更新，请使用新密码登录。')
        setCanResendVerification(false)
        setMode('message')
        navigate('/auth', { replace: true })
      } else {
        const result = await login(email, password)
        navigate(result.user.role === 'student' ? '/onboarding' : '/home', { replace: true })
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '账号服务暂时不可用')
    } finally {
      setSubmitting(false)
    }
  }

  const resend = async () => {
    setSubmitting(true)
    setError('')
    try {
      const result = await requestEmailVerification(email)
      setMessage(result.message)
      setDevelopmentUrl(result.development_action_url)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '验证邮件发送失败')
    } finally {
      setSubmitting(false)
    }
  }

  const title = mode === 'register'
    ? '创建账号'
    : mode === 'forgot'
      ? '找回密码'
      : mode === 'reset'
        ? '设置新密码'
        : mode === 'message'
          ? '检查你的邮箱'
          : '登录数知伙伴'

  return <main className="onboarding-wrap">
    <section className="welcome-card">
      <span className="welcome-brand">数知伙伴</span>
      <h1>每一次学习，<br />都属于你自己。</h1>
      <p>登录后保存学习过程，并按授权范围与家长共享。</p>
      <div className="welcome-orbit orbit-one" /><div className="welcome-orbit orbit-two" /><span className="welcome-star">✳</span>
    </section>
    <form className="onboarding-form" onSubmit={submit}>
      <Chip tone="green">账号与学习记录安全关联</Chip>
      <h2>{title}</h2>
      <Card>
        {mode === 'register' && <>
          <label className="field-label" htmlFor="display-name">怎么称呼你</label>
          <input className="text-input" id="display-name" value={displayName} onChange={event => setDisplayName(event.target.value)} maxLength={40} required />
          <label className="field-label" htmlFor="role">账号类型</label>
          <select className="text-input" id="role" value={role} onChange={event => setRole(event.target.value as 'student' | 'guardian')}>
            <option value="student">学生</option><option value="guardian">家长</option>
          </select>
        </>}
        {(mode === 'login' || mode === 'register' || mode === 'forgot') && <>
          <label className="field-label" htmlFor="email">邮箱</label>
          <input className="text-input" id="email" type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} required />
        </>}
        {(mode === 'login' || mode === 'register') && <>
          <label className="field-label" htmlFor="password">密码</label>
          <input className="text-input" id="password" type="password" minLength={8} maxLength={128} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={event => setPassword(event.target.value)} required />
        </>}
        {mode === 'reset' && <>
          <label className="field-label" htmlFor="new-password">新密码</label>
          <input className="text-input" id="new-password" type="password" minLength={8} maxLength={128} autoComplete="new-password" value={newPassword} onChange={event => setNewPassword(event.target.value)} required />
        </>}
        {mode === 'message' && <p>{message}</p>}
        {developmentUrl && <p><a className="text-link" href={developmentUrl}>开发环境：打开一次性链接 →</a></p>}
        {error && <p className="form-error" role="alert">{error}</p>}
      </Card>
      {mode !== 'message' && <Button type="submit">{submitting ? '请稍候…' : mode === 'login' ? '登录 →' : mode === 'register' ? '创建账号 →' : mode === 'forgot' ? '发送重置邮件 →' : '更新密码 →'}</Button>}
      {mode === 'login' && <button className="auth-mode-button" type="button" onClick={() => setMode('forgot')}>忘记密码？</button>}
      {mode === 'login' && <button className="auth-mode-button" type="button" onClick={() => setMode('register')}>还没有账号？创建账号</button>}
      {mode === 'register' && <button className="auth-mode-button" type="button" onClick={() => setMode('login')}>已经有账号？直接登录</button>}
      {(mode === 'forgot' || mode === 'reset' || mode === 'message') && <button className="auth-mode-button" type="button" onClick={() => { setMode('login'); setMessage(''); setError('') }}>返回登录</button>}
      {mode === 'message' && canResendVerification && email && <button className="auth-mode-button" type="button" disabled={submitting} onClick={() => void resend()}>重新发送验证邮件</button>}
    </form>
  </main>
}
