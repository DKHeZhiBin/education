import { useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Button, Card, Chip, ServiceNotice } from '../../components/ui'
import { MathInline, MathMarkdown } from '../../components/MathMarkdown'
import { PRODUCT_DEFAULT_ROOT_CODE, PRODUCT_SCOPE_LABEL } from '../../config/productScope'
import { getKnowledgeGraph, listCurriculumCatalogs, type CurriculumCatalogSummary, type KnowledgeGraphView, type KnowledgePointView } from '../../services/curriculum'

const GRAPH_WIDTH = 1100
const GRAPH_HEIGHT = 520

/** 中文：知识点在单位球面上的三维坐标。 English: Three-dimensional coordinate of a point on the unit sphere. */
interface SphereCoordinate { key: string; name: string; point?: KnowledgePointView; x: number; y: number; z: number }

/** 中文：旋转和透视计算后的屏幕位置。 English: Screen position after rotation and perspective projection. */
interface ProjectedPoint extends SphereCoordinate { screenX: number; screenY: number; depth: number; scale: number; opacity: number }

/** 中文：用于绘制的知识关系边。 English: Knowledge relationship edge used for graph rendering. */
interface GraphEdge { from: string; to: string; kind: 'required' | 'recommended' | 'hierarchy'; rationale?: string }

/** 中文：知识星球总览页面，负责读取真实目录并按新版球面星图展示。 English: Knowledge Planet overview that renders the real catalog in the updated spherical map. */
export function KnowledgePlanetPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [graph, setGraph] = useState<KnowledgeGraphView | null>(null)
  const [catalogs, setCatalogs] = useState<CurriculumCatalogSummary[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [selectedCode, setSelectedCode] = useState('')
  const [zoom, setZoom] = useState(1)
  const rootCode = searchParams.get('root_code') ?? PRODUCT_DEFAULT_ROOT_CODE

  /** 中文：重新读取知识目录并恢复 URL 指定的选中知识点。 English: Reloads the catalog and restores the point selected by the URL. */
  const loadGraph = async () => {
    setLoading(true)
    setError('')
    try {
      const [result, catalogResult] = await Promise.all([
        getKnowledgeGraph({ rootCode }),
        listCurriculumCatalogs(),
      ])
      setGraph(result)
      setCatalogs(catalogResult)
      const requested = searchParams.get('selected') ?? result.root_code
      setSelectedCode(result.knowledge_points.some(point => point.code === requested) ? requested : result.root_code)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '知识目录暂时无法读取')
    } finally { setLoading(false) }
  }

  useEffect(() => { void loadGraph() }, [rootCode])

  const selected = graph?.knowledge_points.find(point => point.code === selectedCode) ?? graph?.knowledge_points.find(point => point.code === graph.root_code) ?? null
  const selectedRelations = graph?.prerequisites.filter(relation => relation.knowledge_code === selected?.code || relation.prerequisite_code === selected?.code) ?? []
  const selectedPrerequisites = selectedRelations.filter(relation => relation.knowledge_code === selected?.code)
  const nextConnections = selectedRelations.filter(relation => relation.prerequisite_code === selected?.code)
  const primaryPrerequisite = selectedPrerequisites.find(relation => relation.strength === 'required') ?? selectedPrerequisites[0]
  const learningParams = new URLSearchParams({ knowledge_point: selected?.code ?? '', knowledge_name: selected?.name ?? '' })

  return <div className="page knowledge-planet-page knowledge-planet-v2">
    <header className="knowledge-heading"><div><h1>知识星球</h1><p>{graph ? `${graph.title}｜节点与学习关系来自课程数据库。` : '正在读取课程数据库…'}</p></div><Chip tone="green">知识导航</Chip></header>
    <div className="knowledge-view-row">
      <div className="knowledge-tabs" role="tablist" aria-label="知识星球视图"><button className="active" type="button" role="tab" aria-selected="true">知识星球</button><Link to="/knowledge/methods" role="tab" aria-selected="false">思想与方法</Link><button type="button" role="tab" aria-selected="false" disabled>我的路线</button></div>
      <p>{PRODUCT_SCOPE_LABEL} / {graph?.title ?? '课程目录'}</p>
    </div>

    {error && <ServiceNotice title="知识星球暂时不可用" message={error} tone="error" />}
    {loading && <Card className="knowledge-loading"><span className="knowledge-loader" />正在读取知识点与先修关系…</Card>}
    {!loading && !error && graph && <>
      <section className="knowledge-catalog-row">
        <div><strong>{graph.title}</strong><span>{graph.knowledge_points.length} 个知识点 · {graph.prerequisites.length} 条知识关系 · v{graph.catalog_version}</span></div>
        <div className="knowledge-filter-group"><label className="knowledge-search"><span aria-hidden="true">⌕</span><input value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索知识点或关系" />{search && <button type="button" onClick={() => setSearch('')} aria-label="清除搜索">×</button>}</label><select className="knowledge-domain-select" aria-label="选择知识目录" value={graph.root_code} onChange={event => { const catalog = catalogs.find(item => item.root_code === event.target.value); if (!catalog) return; setSearchParams({ root_code: catalog.root_code, selected: catalog.root_code }) }}>{catalogs.map(catalog => <option key={`${catalog.code}-${catalog.version}`} value={catalog.root_code}>{catalog.title}</option>)}</select></div>
      </section>

      <KnowledgeGraphCanvas graph={graph} search={search} selectedCode={selected?.code ?? ''} onSelect={setSelectedCode} zoom={zoom} onZoom={setZoom} />

      <div className="knowledge-recommendation-grid">
        <Card className="knowledge-recommendation-card"><div className="knowledge-recommendation-heading"><h2>当前：<MathInline source={selected?.name ?? ''} /></h2><Chip tone="blue">数据库节点</Chip></div><div className="knowledge-recommendation-action"><MathMarkdown source={`${selected?.description || '从相邻知识出发，理解它与当前主题的数学联系。'}${primaryPrerequisite ? ` 建议先回访“${graph.knowledge_points.find(point => point.code === primaryPrerequisite.prerequisite_code)?.name ?? primaryPrerequisite.prerequisite_code}”。` : ''}`} /><Button to={`/knowledge/points/${encodeURIComponent(selected?.code ?? graph.root_code)}`}>查看知识点内容 →</Button></div></Card>
        <Card className="knowledge-relation-reminder"><h2>这是知识关系，不是解题步骤</h2><p>箭头表示数学关联，线型区分必要先修、建议先修与目录层级；选择节点后可查看数据库中的关系说明。</p></Card>
      </div>

      <Card className="knowledge-selected-detail">
        <div className="knowledge-selected-heading">
          <div><span className="eyebrow">当前知识点</span><h2><MathInline source={selected?.name ?? ''} /></h2></div>
          <div className="knowledge-selected-tags"><Chip tone="green">{selected?.category || '知识点'}</Chip><code>{selected?.code}</code></div>
        </div>
        <MathMarkdown className="knowledge-selected-description" source={selected?.description || '该知识点暂无说明。'} />
        <div className="knowledge-relation-summary">
          <div><strong>{selectedPrerequisites.length}</strong><span>个直接先修</span></div>
          <p>{selectedPrerequisites.length
            ? `学习“${selected?.name}”前，建议先确认${selectedPrerequisites.map(relation => graph.knowledge_points.find(point => point.code === relation.prerequisite_code)?.name ?? relation.prerequisite_code).join('、')}。`
            : `“${selected?.name}”在当前目录中没有记录直接先修，可以从典型问题开始建立理解。`}</p>
          <div><strong>{nextConnections.length}</strong><span>个后续连接</span></div>
        </div>
        <div className="knowledge-selected-relations">
          {selectedRelations.length ? selectedRelations.map(relation => {
            const outgoing = relation.prerequisite_code === selected?.code
            const neighborCode = outgoing ? relation.knowledge_code : relation.prerequisite_code
            const neighbor = graph.knowledge_points.find(point => point.code === neighborCode)
            return <button key={`${relation.prerequisite_code}-${relation.knowledge_code}`} type="button" onClick={() => setSelectedCode(neighborCode)}>
              <span>{outgoing ? '学完可连接' : '学习前需要'} · {relation.strength === 'required' ? '必要关系' : '建议关系'}</span>
              <strong><MathInline source={neighbor?.name ?? neighborCode} /></strong>
              <small><MathInline source={`${relation.rationale || '目录已记录这两个知识点的关联。'} 建议达到“${relation.required_level === 'proficient' ? '熟练运用' : relation.required_level === 'familiar' ? '理解并熟悉' : '初步接触'}”。`} /></small>
            </button>
          }) : <p className="knowledge-empty-relation">当前目录未记录与这个知识点直接相连的关系。</p>}
        </div>
        <div className="knowledge-selected-actions">
          <Button to={`/learn/new?${learningParams.toString()}`}>用一道题学习{selected?.name}</Button>
          <Link to={`/knowledge/points/${encodeURIComponent(selected?.code ?? graph.root_code)}`}>查看定义、性质、定理、公式与题型 →</Link>
        </div>
        <small className="knowledge-mastery-note">浏览和旋转星球不会自动计为掌握；只有完成学习活动并形成记录后，才会更新掌握证据。</small>
      </Card>
      <footer className="knowledge-page-footer"><span>知识关系导航 · 看过不等于掌握，理解与练习共同验证。</span><Link to="/knowledge/methods">数学思想与方法 ↗</Link></footer>
    </>}
  </div>
}

/** 中文：渲染支持拖动、自转、透视和节点聚焦的三维知识星球。 English: Renders a draggable, auto-rotating 3D knowledge planet with perspective and focus. */
function KnowledgeGraphCanvas({ graph, search, selectedCode, onSelect, zoom, onZoom }: { graph: KnowledgeGraphView; search: string; selectedCode: string; onSelect: (code: string) => void; zoom: number; onZoom: (zoom: number) => void }) {
  const spherePoints = useMemo(() => buildSpherePoints(graph), [graph])
  const edges = useMemo(() => buildGraphEdges(graph), [graph])
  const [rotation, setRotation] = useState({ yaw: -.35, pitch: -.08 })
  const [dragging, setDragging] = useState(false)
  const drag = useRef({ pointerId: -1, x: 0, y: 0, yaw: 0, pitch: 0, moved: false })

  useEffect(() => {
    const point = spherePoints.find(item => item.point?.code === selectedCode)
    if (!point) return
    const yaw = Math.atan2(-point.x, point.z)
    const horizontalDepth = Math.sqrt(point.x * point.x + point.z * point.z)
    setRotation({ yaw, pitch: Math.atan2(point.y, horizontalDepth) })
  }, [selectedCode, spherePoints])

  const projected = useMemo(() => projectSphere(spherePoints, rotation.yaw, rotation.pitch), [spherePoints, rotation])
  const projectedMap = new Map(projected.map(point => [point.key, point]))
  const normalizedSearch = search.trim().toLocaleLowerCase()
  const selectedEdges = edges.filter(edge => edge.from === selectedCode || edge.to === selectedCode).slice(0, 5)
  const neighbors = new Set(selectedEdges.flatMap(edge => edge.from === selectedCode ? [edge.to] : [edge.from]))

  /** 中文：开始记录球面拖动。 English: Starts tracking a planet drag gesture. */
  const startDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    if ((event.target as HTMLElement).closest('.knowledge-star-node')) return
    event.currentTarget.setPointerCapture(event.pointerId)
    drag.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, yaw: rotation.yaw, pitch: rotation.pitch, moved: false }
    setDragging(true)
  }

  /** 中文：把指针位移换算为水平和垂直旋转角度。 English: Converts pointer movement into horizontal and vertical rotation. */
  const moveDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (drag.current.pointerId !== event.pointerId) return
    const dx = event.clientX - drag.current.x
    const dy = event.clientY - drag.current.y
    if (Math.abs(dx) + Math.abs(dy) > 4) drag.current.moved = true
    setRotation({ yaw: drag.current.yaw + dx * .0065, pitch: Math.max(-1.05, Math.min(1.05, drag.current.pitch - dy * .005)) })
  }

  /** 中文：结束拖动并恢复缓慢自转。 English: Ends dragging and resumes slow auto-rotation. */
  const endDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (drag.current.pointerId !== event.pointerId) return
    drag.current.pointerId = -1
    setDragging(false)
  }

  /** 中文：选择知识点并将其旋转到球体正面。 English: Selects a point and rotates it to the front of the planet. */
  const focusPoint = (point: ProjectedPoint) => {
    if (drag.current.moved || !point.point) { drag.current.moved = false; return }
    onSelect(point.point.code)
  }

  return <>
    <Card className={`knowledge-graph-card knowledge-sphere-card ${dragging ? 'is-dragging' : ''}`}>
      <div className="knowledge-sphere-caption"><span>{graph.title} · 旋转星球</span><strong>{dragging ? '正在旋转' : '拖动探索'}</strong></div>
      <div className="knowledge-graph-scroll"><div className="knowledge-graph-stage knowledge-planet-stage" style={{ '--graph-zoom': zoom } as CSSProperties} onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag}>
        <div className="knowledge-planet-glow" /><div className="knowledge-planet-equator" /><div className="knowledge-planet-meridian" />
        <svg viewBox={`0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`} aria-hidden="true"><defs><linearGradient id="active-relation" x1="0" x2="1"><stop stopColor="#56cdb6" stopOpacity=".18"/><stop offset=".5" stopColor="#94f5dd" stopOpacity=".9"/><stop offset="1" stopColor="#56cdb6" stopOpacity=".18"/></linearGradient></defs>{selectedEdges.map(edge => { const from = projectedMap.get(edge.from); const to = projectedMap.get(edge.to); if (!from || !to || from.depth < -.45 || to.depth < -.45) return null; return <path key={`${edge.from}-${edge.to}`} className={`knowledge-sphere-edge ${edge.kind} highlighted`} d={`M ${from.screenX} ${from.screenY} Q ${(from.screenX + to.screenX) / 2} ${(from.screenY + to.screenY) / 2 - 12} ${to.screenX} ${to.screenY}`}><title>{edge.rationale}</title></path> })}</svg>
        {projected.sort((a, b) => a.depth - b.depth).map(point => {
          const selected = point.point?.code === selectedCode
          const connected = point.point ? neighbors.has(point.point.code) : false
          const matched = !normalizedSearch || `${point.name} ${point.point?.code ?? ''}`.toLocaleLowerCase().includes(normalizedSearch)
          const style = { left: point.screenX, top: point.screenY, opacity: matched ? point.opacity : .08, transform: `translate(-50%,-50%) scale(${point.scale})`, zIndex: Math.round((point.depth + 1) * 50) + 2, '--point-depth': point.depth } as CSSProperties
          return <button key={point.key} type="button" style={style} className={`knowledge-star-node ${selected ? 'selected' : ''} ${connected ? 'connected' : ''}`} aria-pressed={selected} onClick={() => focusPoint(point)}><i /><span>{point.name}</span></button>
        })}
        <p className="knowledge-drag-hint">按住并拖动旋转 · 点击知识点聚焦</p>
      </div></div>
    </Card>
    <div className="knowledge-map-controls"><span>● 当前知识点&nbsp;&nbsp; ◐ 相邻知识&nbsp;&nbsp; ○ 远处知识</span><div className="knowledge-zoom" aria-label="缩放知识星球"><button type="button" onClick={() => onZoom(Math.max(.8, +(zoom - .1).toFixed(1)))} aria-label="缩小">−</button><button type="button" onClick={() => onZoom(1)} aria-label="恢复默认缩放">{Math.round(zoom * 100)}%</button><button type="button" onClick={() => onZoom(Math.min(1.3, +(zoom + .1).toFixed(1)))} aria-label="放大">＋</button><button type="button" onClick={() => setRotation({ yaw: -.35, pitch: -.08 })}>归位</button><button type="button" onClick={() => onZoom(.8)}>全景</button></div></div>
  </>
}

/** 中文：把数据库知识点均匀放到单位球面。 English: Distributes database-backed knowledge points evenly on a unit sphere. */
function buildSpherePoints(graph: KnowledgeGraphView): SphereCoordinate[] {
  const items = [...graph.knowledge_points].sort((a, b) => a.sort_order - b.sort_order || a.code.localeCompare(b.code)).map(point => ({ key: point.code, name: point.name, point }))
  const goldenAngle = Math.PI * (3 - Math.sqrt(5))
  return items.map((item, index) => {
    const y = 1 - ((index + .5) / items.length) * 2
    const radius = Math.sqrt(1 - y * y)
    const angle = index * goldenAngle
    return { ...item, x: Math.cos(angle) * radius, y, z: Math.sin(angle) * radius }
  })
}

/** 中文：构造目录中的真实关系，层级关系仅作为选中节点的补充。 English: Builds real catalog relations, using hierarchy only as a selected-node supplement. */
function buildGraphEdges(graph: KnowledgeGraphView) {
  const edges: GraphEdge[] = graph.prerequisites.map(relation => ({ from: relation.prerequisite_code, to: relation.knowledge_code, kind: relation.strength, rationale: relation.rationale }))
  const pairs = new Set(edges.map(edge => `${edge.from}|${edge.to}`))
  for (const point of graph.knowledge_points) if (point.parent_code && !pairs.has(`${point.parent_code}|${point.code}`)) edges.push({ from: point.parent_code, to: point.code, kind: 'hierarchy' })
  return edges
}

/** 中文：旋转三维坐标并投影到二维画布，产生远近缩放和透明度。 English: Rotates 3D coordinates and projects them with depth scale and opacity. */
function projectSphere(points: SphereCoordinate[], yaw: number, pitch: number): ProjectedPoint[] {
  const cosYaw = Math.cos(yaw); const sinYaw = Math.sin(yaw); const cosPitch = Math.cos(pitch); const sinPitch = Math.sin(pitch)
  return points.map(point => {
    const x1 = point.x * cosYaw + point.z * sinYaw
    const z1 = -point.x * sinYaw + point.z * cosYaw
    const y1 = point.y * cosPitch - z1 * sinPitch
    const z2 = point.y * sinPitch + z1 * cosPitch
    const perspective = 1 + z2 * .12
    return { ...point, screenX: GRAPH_WIDTH / 2 + x1 * 390 * perspective, screenY: GRAPH_HEIGHT / 2 + y1 * 215 * perspective, depth: z2, scale: .62 + (z2 + 1) * .31, opacity: .2 + (z2 + 1) * .4 }
  })
}
