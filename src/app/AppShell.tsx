import type { ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { logout } from '../services/auth'

const navigation = [
  { to: '/home', label: '学习', icon: '⌂' },
  { to: '/learn/new', label: '开始', icon: '◉' },
  { to: '/mistakes', label: '错题', icon: '⊗' },
  { to: '/progress', label: '进度', icon: '▤' },
  { to: '/profile', label: '我的', icon: '◎' },
]

export function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const activePath = pathname.startsWith('/learn') ? '/learn/new' : pathname

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link to="/home" className="brand"><span className="brand-mark">知</span><span>数知伙伴</span></Link>
        <div className="topbar-right"><span className="grade-pill">初二 · 数学</span><button className="avatar" type="button" aria-label="退出登录" onClick={async () => { await logout(); navigate('/auth', { replace: true }) }}>晓</button></div>
      </header>
      <aside className="sidebar">
        <div className="side-caption">学习空间</div>
        {navigation.map(item => <NavigationLink key={item.to} item={item} active={activePath === item.to} />)}
        <div className="side-note"><span className="spark">✦</span><strong>慢慢来，也会进步</strong><p>先找到卡点，再一步步学会。</p></div>
      </aside>
      <main className="main-area">{children}</main>
      <nav className="bottom-nav" aria-label="主导航">
        {navigation.map(item => <NavigationLink key={item.to} item={item} active={activePath === item.to} compact />)}
      </nav>
    </div>
  )
}

function NavigationLink({ item, active, compact = false }: {
  item: (typeof navigation)[number]
  active: boolean
  compact?: boolean
}) {
  return <Link to={item.to} className={`${compact ? '' : 'side-link '}${active ? 'is-active' : ''}`} aria-current={active ? 'page' : undefined}>
    <span className={compact ? undefined : 'nav-icon'}>{item.icon}</span>{compact ? <small>{item.label}</small> : item.label}
  </Link>
}
