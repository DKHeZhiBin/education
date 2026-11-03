import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { MathInline, MathMarkdown } from '../../components/MathMarkdown'
import { Button, Card, Chip, ServiceNotice } from '../../components/ui'
import { PRODUCT_SCOPE_LABEL } from '../../config/productScope'
import { getKnowledgePointDetail, type KnowledgePointDetailView, type PublishedKnowledgeContent, type RelatedKnowledgePoint } from '../../services/curriculum'
import { createKnowledgeExamplePractice, listLearningRecords, type LearningRecord } from '../../services/tutoring'

const CONTENT_LABELS: Record<PublishedKnowledgeContent['content_type'], string> = {
  definition: '定义', property: '性质', theorem: '定理', formula: '公式', problem_type: '题型',
}
const CONTENT_ORDER: PublishedKnowledgeContent['content_type'][] = ['definition', 'property', 'theorem', 'formula', 'problem_type']
type PracticeDifficulty = 'easy' | 'medium' | 'hard'
const PRACTICE_DIFFICULTIES: Array<{ value: PracticeDifficulty; label: string; code: string; description: string }> = [
  { value: 'easy', label: '简单', code: 'S1 · M1 · T2', description: '同结构同方法，巩固基本步骤' },
  { value: 'medium', label: '中等', code: 'S2 · M2 · T1', description: '换运算结构，重建一个关键环节' },
  { value: 'hard', label: '困难', code: 'S3 · M3 · T4', description: '改变关系表达，切换策略并进行迁移' },
]

/** 中文：从 MySQL 内容与学习记录渲染通用知识点详情页。 English: Renders a generic knowledge-point detail page from MySQL content and learning records. */
export function KnowledgePointDetailPage() {
  const { knowledgeCode = '' } = useParams()
  const [detail, setDetail] = useState<KnowledgePointDetailView | null>(null)
  const [records, setRecords] = useState<LearningRecord[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [practiceContentKey, setPracticeContentKey] = useState<string | null>(null)
  const [practiceError, setPracticeError] = useState('')
  const [practiceErrorContentKey, setPracticeErrorContentKey] = useState<string | null>(null)
  const [practiceDifficulties, setPracticeDifficulties] = useState<Record<string, PracticeDifficulty>>({})
  const navigate = useNavigate()

  useEffect(() => {
    setLoading(true); setError('')
    Promise.all([getKnowledgePointDetail(knowledgeCode), listLearningRecords()])
      .then(([detailResult, recordResult]) => { setDetail(detailResult); setRecords(recordResult) })
      .catch(cause => setError(cause instanceof Error ? cause.message : '知识点详情暂时无法读取'))
      .finally(() => setLoading(false))
  }, [knowledgeCode])

  const evidence = useMemo(() => records.flatMap(record => record.knowledge_points ?? []).filter(item => item.code === knowledgeCode), [records, knowledgeCode])
  const groupedContents = useMemo(() => CONTENT_ORDER.map(type => ({ type, items: detail?.contents.filter(item => item.content_type === type) ?? [] })).filter(group => group.items.length), [detail])

  if (loading) return <div className="page knowledge-point-detail-page"><Card className="knowledge-detail-loading">正在读取知识点、内容与先修关系…</Card></div>
  if (!detail || error) return <div className="page knowledge-point-detail-page"><ServiceNotice title="知识点详情暂时不可用" message={error || '数据库中没有找到该知识点'} tone="error" /><Button to="/knowledge">返回知识星图</Button></div>

  const graphQuery = new URLSearchParams({ root_code: detail.root_code, selected: detail.code })
  const learningQuery = new URLSearchParams({ knowledge_point: detail.code, knowledge_name: detail.name })

  const startSimilarPractice = async (item: PublishedKnowledgeContent, difficulty: PracticeDifficulty) => {
    if (practiceContentKey) return
    setPracticeContentKey(item.content_key)
    setPracticeError('')
    setPracticeErrorContentKey(null)
    try {
      const result = await createKnowledgeExamplePractice({
        knowledgePointCode: detail.code,
        contentKey: item.content_key,
        difficulty,
      })
      window.sessionStorage.setItem(`learning-start:${result.session.id}`, JSON.stringify({
        mode: 'knowledge-example-practice',
        startingPoint: 'no_idea',
        existingSteps: '',
        knowledgePointCode: detail.code,
        knowledgePointName: detail.name,
        sourceContentKey: item.content_key,
        sourceContentTitle: item.title,
        practiceDifficulty: difficulty,
      }))
      navigate(`/learn/${result.session.id}/similar`, {
        state: {
          degradation: result.degraded ? {
            code: result.degradation_code,
            reason: result.degradation_reason,
          } : null,
        },
      })
    } catch (cause) {
      setPracticeError(cause instanceof Error ? cause.message : '相似题生成失败，请稍后重试。')
      setPracticeErrorContentKey(item.content_key)
      setPracticeContentKey(null)
    }
  }

  return <div className="page knowledge-point-detail-page">
    <header className="knowledge-point-title"><div><span className="eyebrow">{detail.catalog_title ?? '知识点详情'}</span><h1><MathInline source={detail.name} /></h1><MathMarkdown source={detail.description || '该知识点尚未填写说明。'} /></div><Chip tone={detail.category === 'core' ? 'green' : 'blue'}>{detail.category === 'core' ? '核心主题' : detail.category === 'foundation' ? '基础知识点' : '拓展知识点'}</Chip></header>
    <div className="knowledge-point-view-row"><div className="knowledge-mode-tabs"><Link className="active" to={`/knowledge?${graphQuery}`}>知识星图</Link><Link to="/knowledge/methods">思想与方法</Link><span className="disabled">我的路线</span></div><p>{PRODUCT_SCOPE_LABEL} · {detail.catalog_title ?? detail.root_code}</p></div>

    <div className="knowledge-point-detail-layout">
      <main className="knowledge-point-main">
        <section className="knowledge-definition-hero"><span>KNOWLEDGE NOTE</span><h2><MathInline source={detail.name} /></h2><MathMarkdown source={detail.description || '管理员尚未补充知识点说明。'} /><code>{detail.code}</code></section>
        {groupedContents.map(group => <section className="knowledge-content-group" key={group.type}>
          <header><span>{String(CONTENT_ORDER.indexOf(group.type) + 1).padStart(2, '0')}</span><h2>{CONTENT_LABELS[group.type]}</h2><small>{group.items.length} 条已发布内容</small></header>
          {group.items.map(item => <KnowledgeContentEntry item={item} key={`${item.content_type}-${item.content_key}`} startingPractice={practiceContentKey === item.content_key} practiceDisabled={Boolean(practiceContentKey)} practiceError={practiceErrorContentKey === item.content_key ? practiceError : ''} selectedDifficulty={practiceDifficulties[item.content_key] ?? 'medium'} onDifficultyChange={difficulty => setPracticeDifficulties(current => ({ ...current, [item.content_key]: difficulty }))} onStartSimilar={difficulty => void startSimilarPractice(item, difficulty)} />)}
        </section>)}
        {!groupedContents.length && <ServiceNotice title="这个知识点还没有已发布内容" message="管理员可以在知识内容管理台中审核草稿并发布；发布后会自动显示在这里。" />}
      </main>

      <aside className="knowledge-point-sidebar">
        <RelationCard title="学习前需要" empty="当前没有记录直接先修关系。" relations={detail.prerequisites} detail={detail} />
        <RelationCard title="学完可连接" empty="当前没有记录后续知识关系。" relations={detail.dependents} detail={detail} />
        <Card className="knowledge-learning-action"><h2>用一道题验证理解</h2><p>知识内容用于理解，完成学习活动后才会形成掌握证据。</p><Button to={`/learn/new?${learningQuery}`}>开始学习 · {detail.name}</Button></Card>
        <Card className="knowledge-evidence-card"><div><h2>掌握证据</h2><Chip tone={evidence.length ? 'green' : 'amber'}>{evidence.length ? `${evidence.length} 条` : '暂无证据'}</Chip></div>{evidence.length ? evidence.map((item, index) => <article key={`${item.code}-${index}`}><strong>{item.mastery}</strong><MathMarkdown source={item.evidence || '该记录未保存文字证据。'} /><small>{item.effective_attempt_count} 次有效尝试 · 最高 {item.hint_level} 级提示</small></article>) : <p>还没有完成并写入数据库的学习记录。浏览本页不会自动计为掌握。</p>}</Card>
        <Card className="knowledge-version-card"><h2>目录版本</h2><dl><div><dt>目录</dt><dd>{detail.catalog_title ?? detail.catalog_code ?? '未归入目录'}</dd></div><div><dt>编码</dt><dd>{detail.catalog_code ?? detail.root_code}</dd></div><div><dt>版本</dt><dd>{detail.catalog_version ?? '未设置'}</dd></div><div><dt>内容</dt><dd>{detail.contents.length} 条已发布</dd></div></dl></Card>
        <Link className="knowledge-back-link" to={`/knowledge?${graphQuery}`}>↖ 回到关联知识星图</Link>
      </aside>
    </div>
    <footer className="workspace-footer"><span>知识正文、节点和关系均来自课程数据库。</span><span>阅读不等于掌握，理解与练习共同验证。</span></footer>
  </div>
}

/** 中文：展示一条知识正文，并为题型单独渲染成对的解题框架。 English: Displays one knowledge item and renders paired solution-framework steps separately for problem types. */
function KnowledgeContentEntry({ item, startingPractice, practiceDisabled, practiceError, selectedDifficulty, onDifficultyChange, onStartSimilar }: { item: PublishedKnowledgeContent; startingPractice: boolean; practiceDisabled: boolean; practiceError: string; selectedDifficulty: PracticeDifficulty; onDifficultyChange: (difficulty: PracticeDifficulty) => void; onStartSimilar: (difficulty: PracticeDifficulty) => void }) {
  return <Card className="knowledge-content-entry">
    <div className="knowledge-content-entry-heading"><div><Chip tone="green">{CONTENT_LABELS[item.content_type]}</Chip><h3>{renderInlineMath(item.title)}</h3></div><code>{item.content_key}</code></div>
    {item.summary && <p className="knowledge-content-summary">{renderInlineMath(item.summary)}</p>}
    <RichMathContent source={item.body_markdown} />
    {item.solution_framework_json.length > 0 && <section className="knowledge-solution-framework">
      <header><span>THINKING FRAMEWORK</span><h4>解题框架</h4><p>先理解每一步为什么这样想，再看它如何落实到当前例题。</p></header>
      <ol>{item.solution_framework_json.map((step, index) => <li key={`${item.content_key}-${index}`}>
        <div className="knowledge-framework-step-title"><span>{String(index + 1).padStart(2, '0')}</span><h5>{step.title}</h5></div>
        <div className="knowledge-framework-pair">
          <div className="knowledge-framework-idea"><strong>框架思路</strong><RichMathContent source={step.framework} /></div>
          <div className="knowledge-framework-worked"><strong>对应解题步骤</strong><RichMathContent source={step.solution_step} />{step.formula_latex && <MathExpression latex={step.formula_latex} display />}</div>
        </div>
      </li>)}</ol>
    </section>}
    {item.formula_latex && <MathExpression latex={item.formula_latex} display />}
    {item.content_type === 'problem_type' && <div className="knowledge-similar-practice-action">
      <div className="knowledge-practice-copy"><strong>{startingPractice ? '正在生成并校验新题' : '选择练习难度'}</strong><p aria-live="polite">{startingPractice ? '系统正在按选定难度生成、复核并建立辅导会话。' : '难度会决定题面结构、思维变化和教学目标。'}</p>
        <div className="knowledge-practice-difficulty" role="radiogroup" aria-label="相似题难度">{PRACTICE_DIFFICULTIES.map(option => <button className={selectedDifficulty === option.value ? 'selected' : ''} disabled={practiceDisabled} key={option.value} type="button" role="radio" aria-checked={selectedDifficulty === option.value} onClick={() => onDifficultyChange(option.value)}><span>{option.label}</span><code>{option.code}</code><small>{option.description}</small></button>)}</div>
      </div>
      <Button disabled={practiceDisabled} onClick={() => onStartSimilar(selectedDifficulty)}>{startingPractice ? '生成并校验中…' : `生成${PRACTICE_DIFFICULTIES.find(option => option.value === selectedDifficulty)?.label ?? '中等'}题 →`}</Button>
    </div>}
    {practiceError && <ServiceNotice title="这道相似题生成失败" message={practiceError} tone="error" />}
  </Card>
}

/** 中文：展示一组数据库直接关系并链接到相邻知识点。 English: Displays direct database relationships and links to neighboring points. */
function RelationCard({ title, empty, relations, detail }: { title: string; empty: string; relations: RelatedKnowledgePoint[]; detail: KnowledgePointDetailView }) {
  const graphQuery = new URLSearchParams({ root_code: detail.root_code, selected: detail.code })
  return <Card className="knowledge-relation-card"><h2>{title}</h2>{relations.length ? relations.map(relation => <article key={relation.code}><div><strong><MathInline source={relation.name} /></strong><span>{relation.strength === 'required' ? '必要' : '建议'}</span></div><MathMarkdown source={relation.rationale} /><small>建议程度：{relation.required_level === 'proficient' ? '熟练运用' : relation.required_level === 'familiar' ? '理解并熟悉' : '初步接触'}</small><Link to={`/knowledge/points/${encodeURIComponent(relation.code)}`}>查看知识点 →</Link></article>) : <p className="tiny-muted">{empty}</p>}<Link className="knowledge-relation-graph-link" to={`/knowledge?${graphQuery}`}>在星图中查看关系 ↗</Link></Card>
}

/** 中文：渲染正文中的段落、简单列表、粗体及行内/独立 LaTeX。 English: Renders paragraphs, simple lists, bold text, and inline/display LaTeX. */
function RichMathContent({ source }: { source: string }) {
  const blocks = source.split(/(\$\$[\s\S]*?\$\$)/g).filter(Boolean)
  return <div className="knowledge-rich-content">{blocks.map((block, blockIndex) => {
    if (block.startsWith('$$') && block.endsWith('$$')) return <MathExpression key={blockIndex} latex={block.slice(2, -2).trim()} display />
    return block.split('\n').map((line, lineIndex) => {
      const trimmed = line.trim()
      if (!trimmed) return <span className="knowledge-rich-gap" key={`${blockIndex}-${lineIndex}`} />
      const heading = trimmed.match(/^#{1,4}\s+(.+)$/)
      if (heading) return <h4 key={`${blockIndex}-${lineIndex}`}>{renderInlineMath(heading[1])}</h4>
      const listItem = trimmed.match(/^(?:[-*]|\d+\.)\s+(.+)$/)
      if (listItem) return <p className="knowledge-rich-list-item" key={`${blockIndex}-${lineIndex}`}>{renderInlineMath(listItem[1])}</p>
      return <p key={`${blockIndex}-${lineIndex}`}>{renderInlineMath(trimmed)}</p>
    })
  })}</div>
}

/** 中文：把一行文字拆成普通文本、粗体和行内公式。 English: Splits a text line into plain text, bold text, and inline math. */
function renderInlineMath(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={index}><MathInline source={part.slice(2, -2)} /></strong>
    return <MathInline key={index} source={part} />
  })
}

/** 中文：使用 MathLive 排版只读 LaTeX 表达式。 English: Typesets a read-only LaTeX expression with MathLive. */
function MathExpression({ latex, display = false }: { latex: string; display?: boolean }) {
  return display
    ? <MathMarkdown className="knowledge-math-display-host" source={`\\[${latex}\\]`} />
    : <MathInline className="knowledge-math-inline-host" source={`\\(${latex}\\)`} />
}
