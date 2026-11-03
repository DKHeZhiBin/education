import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, Chip } from '../../components/ui'
import { MathInline } from '../../components/MathMarkdown'
import searchMethodsIcon from '../../assets/figma/search-methods.svg'
import { getThinkingMethodCatalog, type PublishedThinkingMethodCategory } from '../../services/curriculum'

/** 中文：从数据库读取数学思想与方法目录，并提供关键词搜索。 English: Loads the thinking-method catalog from the database with keyword search. */
export function ThinkingMethodsPage() {
  const [catalog, setCatalog] = useState<PublishedThinkingMethodCategory[]>([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const resultAnchor = useRef<HTMLDivElement | null>(null)
  const normalizedQuery = query.trim().toLocaleLowerCase()

  /** 中文：加载管理员发布的方法目录。 English: Loads the administrator-published method catalog. */
  const loadCatalog = () => {
    setLoading(true); setError('')
    void getThinkingMethodCatalog().then(setCatalog).catch(reason => setError(reason instanceof Error ? reason.message : '方法目录暂时不可用')).finally(() => setLoading(false))
  }

  useEffect(loadCatalog, [])

  const categories = useMemo(() => catalog.map(category => ({
    ...category,
    methods: category.methods.filter(method => !normalizedQuery || `${method.name} ${method.aliases.join(' ')} ${method.domain_tags.join(' ')} ${category.label} ${category.focus} ${method.goal} ${method.example}`.toLocaleLowerCase().includes(normalizedQuery)),
  })).filter(category => category.methods.length > 0), [catalog, normalizedQuery])
  const resultCount = categories.reduce((total, category) => total + category.methods.length, 0)

  /** 中文：执行目录搜索并定位到结果。 English: Runs catalog search and moves focus to its results. */
  const submitSearch = () => resultAnchor.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })

  return <div className="page thinking-methods-page" id="method-catalog-top">
    <header className="knowledge-heading method-catalog-heading"><div><h1>数学思维方法总目录</h1><p>按通用分类组织方法；先理解核心思想，再在题目中识别与运用。</p></div><Chip tone="green">结构 · 策略 · 迁移</Chip></header>
    <div className="method-module-row"><div className="knowledge-mode-tabs" aria-label="知识星球模块"><Link to="/knowledge">基础知识</Link><span className="active">思想与方法</span><span className="disabled">我的路线</span></div><nav className="method-view-nav" aria-label="方法目录功能"><a className="active" href="#method-catalog-top">分类目录</a><Link to="/knowledge">关系星图</Link><a href="#method-results">方法学习</a><Link to="/learn/new?mode=method-recognition">识别训练</Link><Link to="/progress">复盘与迁移</Link></nav></div>
    <Card className="method-catalog-note"><strong>按通用思想组织方法，具体技巧由内容管理台持续维护</strong><p>{catalog.length || 10} 类方法覆盖转化、数形、分类、函数、特殊与一般、整体与局部、极限与逼近、构造与对应、逻辑与证明、计数与组合。</p><span>入门：形成思考习惯 / 深化：关注条件与论证 / 进阶：处理抽象结构与严谨证明</span></Card>
    <form className="method-search-row" onSubmit={event => { event.preventDefault(); submitSearch() }}><label><img src={searchMethodsIcon} alt="" /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索方法名称、别名或题目特征" />{query && <button type="button" onClick={() => setQuery('')} aria-label="清除搜索">×</button>}</label><button type="submit">搜索方法</button></form>
    <div className="method-stage-filter" id="method-results" ref={resultAnchor}><span>方法目录</span><small>{normalizedQuery ? `找到 ${resultCount} 个方法` : `全部方法 · ${catalog.length || 10} 类均可探索`}</small></div>
    {loading && <Card className="method-empty"><strong>正在读取方法目录…</strong><p>内容来自数据库中的已发布版本。</p></Card>}
    {!loading && error && <Card className="method-empty"><strong>方法目录暂时不可用</strong><p>{error}</p><button type="button" onClick={loadCatalog}>重新加载</button></Card>}
    {!loading && !error && !categories.length && <Card className="method-empty"><strong>没有找到匹配的方法</strong><p>试试“画图”“参数”“证明”或清空当前搜索。</p><button type="button" onClick={() => setQuery('')}>查看全部方法</button></Card>}
    <div className="method-category-list">{categories.map(category => <MethodCategorySection key={category.code} category={category} showAll={Boolean(normalizedQuery)} />)}</div>
  </div>
}

/** 中文：渲染一个分类，长列表可按需展开。 English: Renders one category with optional expansion for long lists. */
function MethodCategorySection({ category, showAll }: { category: PublishedThinkingMethodCategory; showAll: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const visible = showAll || expanded ? category.methods : category.methods.slice(0, 8)
  return <section className="method-category-section" id={`method-category-${category.code}`}><header><span className="method-category-symbol" aria-hidden="true">{category.symbol}</span><div><div><h2>{category.label}</h2><Chip tone="green">{category.focus}</Chip></div><p>{category.description}</p></div><Link to={`/learn/new?mode=method-recognition&category=${category.code}`}>进入识别训练 ↗</Link></header><div className="method-table"><div className="method-table-head"><span>方法或技巧</span><span>核心思想</span><span>识别信号 / 应用示例</span><span>学习入口</span></div>{visible.map(method => <article key={method.code} className="method-row"><div><strong>{method.name}</strong><p><span>{kindName(method.kind)}</span><em>{method.level}</em></p></div><p><MathInline source={method.goal} /></p><p><MathInline source={method.example} /></p><Link to={`/knowledge/methods/${method.code}`}>查看方法 →</Link></article>)}</div>{!showAll && category.methods.length > 8 && <button className="method-expand-category" type="button" onClick={() => setExpanded(value => !value)}>{expanded ? '收起本分类' : `展开其余 ${category.methods.length - 8} 个方法`}</button>}<p className="method-reminder">{category.reminder}</p></section>
}

/** 中文：把数据库方法层级转换为界面文案。 English: Converts a database method kind into interface copy. */
function kindName(kind: string) {
  return ({ thought: '数学思想', strategy: '通用策略', technique: '具体技巧', theorem_tool: '定理工具' } as Record<string, string>)[kind] ?? '具体方法'
}
