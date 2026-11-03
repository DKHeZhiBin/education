import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Button, Card, Chip } from '../../components/ui'
import { MathInline, MathMarkdown } from '../../components/MathMarkdown'
import { getThinkingMethodCatalog, getThinkingMethodDetail, type PublishedThinkingMethod, type ThinkingMethodDetailView } from '../../services/curriculum'

const sections = [['method-what', '01', '它是什么'], ['method-signals', '02', '看到什么，考虑用它'], ['method-how', '03', '怎样使用'], ['method-examples', '04', '例题带你看'], ['method-misuse', '05', '别这样用'], ['method-related', '06', '关联知识与方法'], ['method-challenge', '07', '轮到你']]

interface MethodExample { title: string; tag: string; problem: string; signal: string; reason: string; steps: string[]; derivation: string; conclusion: string; check: string }
interface MethodType { name: string; slogan: string; definition: string; suitable: string; warning: string }
interface MethodDetailContent { subtitle: string; summary: string; distinction: string; types: MethodType[]; signals: string[]; steps: string[]; examples: MethodExample[]; misuses: string[]; prerequisites: string; related: string; challenge: string }
interface Neighbor { categoryLabel: string; method: PublishedThinkingMethod }

/** 中文：从数据库读取并渲染数学方法详情。 English: Loads and renders a database-backed mathematical method detail. */
export function ThinkingMethodDetailPage() {
  const { methodId = '' } = useParams()
  const [method, setMethod] = useState<ThinkingMethodDetailView | null>(null)
  const [neighbors, setNeighbors] = useState<{ previous: Neighbor | null; next: Neighbor | null }>({ previous: null, next: null })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true); setError('')
    void Promise.all([getThinkingMethodDetail(methodId), getThinkingMethodCatalog()]).then(([detail, catalog]) => {
      setMethod(detail)
      const flattened = catalog.flatMap(category => category.methods.map(item => ({ categoryLabel: category.label, method: item })))
      const index = flattened.findIndex(item => item.method.code === methodId)
      setNeighbors({ previous: index > 0 ? flattened[index - 1] : null, next: index >= 0 && index < flattened.length - 1 ? flattened[index + 1] : null })
    }).catch(reason => setError(reason instanceof Error ? reason.message : '方法详情暂时不可用')).finally(() => setLoading(false))
  }, [methodId])

  if (loading) return <div className="page method-detail-page"><Card className="method-empty"><strong>正在读取方法详情…</strong><p>内容来自数据库中的已发布版本。</p></Card></div>
  if (error || !method) return <div className="page method-detail-page"><Card className="method-empty"><strong>无法打开这个方法</strong><p>{error || '该方法可能已归档。'}</p><Button to="/knowledge/methods">返回总目录</Button></Card></div>
  const detail = normalizeDetail(method)

  return <div className="page method-detail-page">
    <header className="method-detail-heading"><div><p><strong>{method.category_label} · 建议学习重点</strong><span>{method.level} · 从识别到解释</span></p><h1>{method.name}</h1><MathMarkdown source={detail.subtitle} /></div><Link to="/knowledge/methods">↖ 返回总目录</Link></header>
    <div className="method-detail-module-row"><div className="knowledge-mode-tabs"><Link to="/knowledge">基础知识</Link><Link className="active" to="/knowledge/methods">思想与方法</Link><span className="disabled">我的路线</span></div><p>方法学习　/　<Link to="/learn/new?mode=method-recognition">识别训练</Link>　/　<Link to="/progress">复盘与迁移</Link></p></div>
    <div className="method-detail-layout"><main className="method-detail-content">
      <MethodSection id="method-what" number="01" title="它是什么"><MathMarkdown source={detail.summary} /><div className="method-distinction"><MathMarkdown source={detail.distinction} /></div>{detail.types.length > 0 && <div className="method-type-grid">{detail.types.map((item, index) => <article key={item.name}><header><span>{String(index + 1).padStart(2, '0')}</span><div><h3>{item.name}</h3><strong><MathInline source={item.slogan} /></strong></div></header><MathMarkdown source={item.definition} /><dl><div><dt>适合</dt><dd><MathInline source={item.suitable} /></dd></div><div><dt>注意</dt><dd><MathInline source={item.warning} /></dd></div></dl></article>)}</div>}</MethodSection>
      <MethodSection id="method-signals" number="02" title="看到什么，考虑用它"><NumberedList items={detail.signals} tone="green" /></MethodSection>
      <MethodSection id="method-how" number="03" title="怎样使用"><NumberedList items={detail.steps} tone="blue" /></MethodSection>
      <section className="method-example-section" id="method-examples"><header><h2><span>04</span> 例题带你看</h2><small>{detail.examples.length} 道例题 · 全部展开</small></header>{detail.examples.map((item, index) => <Card className="method-example-card" key={`${item.title}-${index}`}><h3><MathInline source={item.title} /> <Chip tone={index === 2 ? 'amber' : 'blue'}>{item.tag}</Chip></h3><MathMarkdown className="method-example-problem" source={item.problem} /><div className="method-example-reason"><div><strong>识别信号</strong><MathMarkdown source={item.signal} /></div><div><strong>选择理由</strong><MathMarkdown source={item.reason} /></div></div><ol>{item.steps.map(step => <li key={step}><MathMarkdown source={step} /></li>)}</ol><div className="method-derivation"><MathMarkdown source={item.derivation} /></div><p><b>结论　</b><MathInline source={item.conclusion} /></p><small>✓ 条件检验　<MathInline source={item.check} /></small></Card>)}</section>
      <MethodSection id="method-misuse" number="05" title="别这样用" tone="warning"><ul>{detail.misuses.map(item => <li key={item}><MathInline source={item} /></li>)}</ul></MethodSection>
      <MethodSection id="method-related" number="06" title="关联知识与方法"><div className="method-related-grid"><div><strong>知识前提 · 已学工具</strong><MathMarkdown source={detail.prerequisites} /></div><div><strong>搭配方法 · 思考策略</strong><MathMarkdown source={detail.related} /></div></div></MethodSection>
      <MethodSection id="method-challenge" number="07" title="轮到你" tone="practice"><MathMarkdown source={detail.challenge} /><div className="method-challenge-action"><span>先识别、解释并作答；此处不展示答案。</span><Button to="/learn/new?mode=method-recognition">开始迁移练习 →</Button></div></MethodSection>
    </main><aside className="method-detail-sidebar"><Card className="method-page-index"><h2>本页目录</h2>{sections.map(([id, number, title]) => <a key={id} href={`#${id}`}><span>{number}</span>{title}</a>)}</Card><Card className="method-mastery-card"><h2>怎样算真正掌握？</h2><p><b>识别：</b>指出题目的结构信号</p><p><b>解释：</b>说清为何选这个方法</p><p><b>使用：</b>独立完成并检查条件</p><p><b>迁移：</b>换个情境仍能选择策略</p><strong>看过 ≠ 掌握</strong></Card><Card className="method-stage-note"><h2>按自己的基础学习</h2><p>学段表示建议学习重点，不是官方必修清单。同一思想可跨学段深化，请结合教材与基础调整。</p></Card></aside></div>
    <nav className="method-neighbor-nav">{neighbors.previous ? <Link to={`/knowledge/methods/${neighbors.previous.method.code}`}><small>← 上一篇</small><strong>{neighbors.previous.categoryLabel} · {neighbors.previous.method.name}</strong></Link> : <span />}{neighbors.next ? <Link to={`/knowledge/methods/${neighbors.next.method.code}`}><small>下一篇 →</small><strong>{neighbors.next.categoryLabel} · {neighbors.next.method.name}</strong></Link> : <span />}</nav>
    <footer className="workspace-footer"><span>数知伙伴 · 方法成长由识别、解释、使用与迁移共同验证；看过不等于掌握。</span></footer>
  </div>
}

/** 中文：把可编辑 JSON 规范化为稳定页面结构。 English: Normalizes editable JSON into a stable page structure. */
function normalizeDetail(method: ThinkingMethodDetailView): MethodDetailContent {
  const raw = method.detail
  const text = (key: string, fallback: string) => typeof raw[key] === 'string' && raw[key] ? raw[key] as string : fallback
  const strings = (key: string, fallback: string[]) => Array.isArray(raw[key]) ? (raw[key] as unknown[]).filter((item): item is string => typeof item === 'string') : fallback
  const rawExamples = Array.isArray(raw.examples) ? raw.examples : []
  const examples = rawExamples.map((value, index) => normalizeExample(value, index, method)).filter((value): value is MethodExample => Boolean(value))
  const rawTypes = Array.isArray(raw.types) ? raw.types : []
  const types = rawTypes.map(normalizeMethodType).filter((value): value is MethodType => Boolean(value))
  return {
    subtitle: text('subtitle', method.goal),
    summary: text('summary', `${method.name}帮助学习者${method.goal}`),
    distinction: text('distinction', '方法提供思考方向，具体公式和运算仍需满足原题条件。'),
    types,
    signals: strings('signals', [method.goal, method.example]),
    steps: strings('steps', ['标出条件、目标和关键结构。', `说明为什么选择${method.name}。`, '完成推理并检查边界与结论。']),
    examples: examples.length ? examples : [normalizeExample({}, 0, method)!],
    misuses: strings('misuses', ['只记方法名称，没有指出识别信号。', '忽略定义域、边界或实际意义。']),
    prerequisites: text('prerequisites', '当前课程中已经学过的定义、公式和基本运算。'),
    related: text('related', '可回到总目录比较同类方法的适用条件。'),
    challenge: text('challenge', `找一道适合使用${method.name}的题，先写识别信号和选择理由。`),
  }
}

/** 中文：安全解析管理员维护的方法分类说明。 English: Safely parses an administrator-maintained method-type explanation. */
function normalizeMethodType(value: unknown): MethodType | null {
  if (!value || typeof value !== 'object') return null
  const raw = value as Record<string, unknown>
  const text = (key: string) => typeof raw[key] === 'string' ? raw[key] as string : ''
  const name = text('name')
  if (!name) return null
  return { name, slogan: text('slogan'), definition: text('definition'), suitable: text('suitable'), warning: text('warning') }
}

/** 中文：安全解析管理员维护的单个结构化例题。 English: Safely parses one administrator-maintained structured example. */
function normalizeExample(value: unknown, index: number, method: ThinkingMethodDetailView): MethodExample | null {
  const raw = value && typeof value === 'object' ? value as Record<string, unknown> : {}
  const text = (key: string, fallback: string) => typeof raw[key] === 'string' ? raw[key] as string : fallback
  const steps = Array.isArray(raw.steps) ? raw.steps.filter((item): item is string => typeof item === 'string') : ['识别结构与目标。', '选择方法并逐步验证。']
  return { title: text('title', `例 ${index + 1} · 识别示范`), tag: text('tag', '目录示例'), problem: text('problem', method.example), signal: text('signal', method.goal), reason: text('reason', `该情境体现${method.name}的典型使用入口。`), steps, derivation: text('derivation', '识别结构 → 解释选择 → 完成推理 → 检验条件'), conclusion: text('conclusion', '请结合具体题目完成推导。'), check: text('check', '结论应回答原问题且不遗漏限制条件。') }
}

/** 中文：渲染带编号和锚点的教学章节。 English: Renders a numbered teaching section with an anchor. */
function MethodSection({ id, number, title, tone = '', children }: { id: string; number: string; title: string; tone?: string; children: React.ReactNode }) { return <Card className={`method-learning-section ${tone}`}><div id={id} className="method-section-anchor" /><h2><span>{number}</span>{title}</h2>{children}</Card> }

/** 中文：渲染带两位序号的教学步骤列表。 English: Renders a teaching list with two-digit step numbers. */
function NumberedList({ items, tone }: { items: string[]; tone: 'green' | 'blue' }) { return <ol className={`method-number-list ${tone}`}>{items.map((item, index) => <li key={`${item}-${index}`}><span>{String(index + 1).padStart(2, '0')}</span><MathInline source={item} /></li>)}</ol> }
