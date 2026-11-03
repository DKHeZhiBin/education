import { useEffect, useState, type ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { AUTH_SESSION_EXPIRED_EVENT, getCurrentUser, logout, type AuthUser } from '../services/auth'

const navigation = [
  { to: '/home', label: '首页', icon: '⌂' },
  { to: '/learn/new', label: '开始学习', icon: '＋' },
  { to: '/learn', label: '思路引导', icon: '⌘' },
  { to: '/knowledge', label: '知识星球', icon: '◎' },
  { to: null, label: '练习', icon: '✎' },
  { to: '/mistakes', label: '错题本', icon: '◇' },
  { to: '/progress', label: '学习进度', icon: '↗' },
] as const

export function AppShell({ children }: { children: ReactNode }) {
  const { pathname, search, hash } = useLocation()
  const navigate = useNavigate()
  const [user, setUser] = useState<AuthUser | null>(null)
  const isLearningFlow = /^\/learn\/[^/]+\//.test(pathname)
  const isKnowledgeFlow = pathname.startsWith('/knowledge')
  const isThinkingMethods = pathname.startsWith('/knowledge/methods')
  const activePath = isLearningFlow ? '/learn' : isKnowledgeFlow ? '/knowledge' : pathname

  useEffect(() => {
    void getCurrentUser().then(setUser).catch(() => setUser(null))
  }, [])

  useEffect(() => {
    /**
     * 登录过期后保留当前地址并返回登录页。 / Preserve the current location and return to sign-in after expiry.
     */
    const handleSessionExpired = () => {
      const returnTo = `${pathname}${search}${hash}`
      navigate(`/auth?reason=session_expired&return_to=${encodeURIComponent(returnTo)}`, { replace: true })
    }
    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired)
    return () => window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired)
  }, [hash, navigate, pathname, search])

  const displayName = user?.display_name || '学习者'

  return <div className="app-shell">
    <header className="topbar">
      <p className="breadcrumb">学习空间&nbsp; / &nbsp;{breadcrumbFor(pathname)}</p>
      <div className="topbar-right">
        <span className="sync-state">✓ 学习记录已同步</span>
        <button className="avatar" type="button" aria-label="退出登录" onClick={async () => { await logout(); navigate('/auth', { replace: true }) }}>{displayName.slice(0, 1)}</button>
      </div>
    </header>
    <aside className="sidebar">
      <Link to="/home" className="sidebar-brand"><strong>数知伙伴</strong><span>理解 × 练习 = 进步</span></Link>
      <nav className="sidebar-navigation" aria-label="主导航">
        {navigation.map(item => <NavigationLink key={item.label} item={item} active={activePath === item.to} />)}
      </nav>
      <div className="side-note"><strong>{isLearningFlow ? '综合题 · 思路工作台' : isThinkingMethods ? '数学思想与方法' : isKnowledgeFlow ? '进阶探索 · 独立星域' : '我的学习空间'}</strong><p>{isLearningFlow ? '接住已有步骤\n一起理解关键连接' : isThinkingMethods ? '从看见结构，到选择策略。\n与基础知识并行探索。' : isKnowledgeFlow ? '自由探索大学微积分\n不影响当前课程进度' : '先找到卡点，再一步步学会。'}</p></div>
      <div className="sidebar-user"><strong>{displayName} · 大学高数</strong><span>连续学习 6 天</span></div>
    </aside>
    <main className="main-area">{children}</main>
    <nav className="bottom-nav" aria-label="移动端主导航">
      {navigation.filter(item => item.to).slice(0, 5).map(item => <NavigationLink key={item.label} item={item} active={activePath === item.to} compact />)}
    </nav>
  </div>
}

function NavigationLink({ item, active, compact = false }: {
  item: (typeof navigation)[number]
  active: boolean
  compact?: boolean
}) {
  const content = <><span className={compact ? undefined : 'nav-icon'}>{item.icon}</span>{compact ? <small>{item.label}</small> : item.label}</>
  if (!item.to) return <span className={`${compact ? '' : 'side-link '}is-disabled`} aria-disabled="true">{content}</span>
  const destination = item.to === '/learn' ? '/learn/new' : item.to
  return <Link to={destination} className={`${compact ? '' : 'side-link '}${active ? 'is-active' : ''}`} aria-current={active ? 'page' : undefined}>{content}</Link>
}

function breadcrumbFor(pathname: string) {
  if (pathname === '/home') return '首页'
  if (pathname === '/learn/new') return '思路引导 / 确认题目'
  if (pathname.endsWith('/diagnosis')) return '思路引导 / 接续步骤'
  if (pathname.endsWith('/coach')) return '思路引导 / 一起思考'
  if (pathname.endsWith('/map')) return '思路引导 / 思路地图'
  if (pathname.endsWith('/hints')) return '思路引导 / 按需提示'
  if (pathname.endsWith('/practice')) return '练习 / 迁移练习'
  if (pathname.endsWith('/feedback')) return '思路引导 / 完成复盘'
  if (pathname === '/mistakes') return '错题本'
  if (pathname === '/progress') return '学习进度'
  if (pathname === '/knowledge') return '知识星球 / 进阶探索 · 微积分'
  if (pathname.startsWith('/knowledge/points/')) return '知识星球 / 进阶探索 · 微积分'
  if (pathname.startsWith('/knowledge/methods/')) {
    return '方法总目录 / 方法学习'
  }
  if (pathname === '/knowledge/methods') return '知识星球 / 数学思想与方法'
  if (pathname === '/profile') return '账号与设置'
  return '学习空间'
}
