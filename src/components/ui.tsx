import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

export function PageTitle({ eyebrow, title, description }: { eyebrow?: string; title: string; description?: string }) {
  return <header className="page-title">
    {eyebrow && <span className="eyebrow">{eyebrow}</span>}
    <div className="title-row"><h1>{title}</h1><span className="avatar title-avatar" aria-label="林晓">晓</span></div>
    {description && <p>{description}</p>}
  </header>
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`card ${className}`}>{children}</section>
}

export function Button({ children, to, onClick, secondary = false, type = 'button', disabled = false }: {
  children: ReactNode
  to?: string
  onClick?: () => void
  secondary?: boolean
  type?: 'button' | 'submit'
  disabled?: boolean
}) {
  const className = `button ${secondary ? 'button-secondary' : ''}`
  return to
    ? <Link className={className} to={to}>{children}</Link>
    : <button className={className} type={type} onClick={onClick} disabled={disabled}>{children}</button>
}

export function Chip({ children, tone = 'blue' }: { children: ReactNode; tone?: 'blue' | 'green' | 'amber' }) {
  return <span className={`chip ${tone}`}>{children}</span>
}

export function ProgressBar({ value, tone = 'teal', label }: { value: number; tone?: 'teal' | 'blue'; label?: string }) {
  return <div className="progress-track" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={value}>
    <div className={`progress-fill ${tone}`} style={{ width: `${value}%` }} />
  </div>
}

export function ServiceNotice({ title, message, tone = 'warning' }: {
  title: string
  message: string
  tone?: 'warning' | 'error' | 'info'
}) {
  return <div className={`service-notice ${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
    <strong>{title}</strong><span>{message}</span>
  </div>
}
