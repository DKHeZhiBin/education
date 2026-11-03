import { authorizedFetch, parseResponse } from './auth'

/** 中文：知识点在关系图中的角色。 English: Role of a knowledge point in the graph. */
export type KnowledgeGraphRole = 'topic' | 'prerequisite'
/** 中文：先修关系的强度。 English: Strength of a prerequisite relationship. */
export type PrerequisiteStrength = 'required' | 'recommended'
/** 中文：进入后续知识前建议达到的掌握层级。 English: Recommended mastery level before progressing. */
export type MasteryLevel = 'introduced' | 'familiar' | 'proficient'

/** 中文：后端返回的知识点只读视图。 English: Read-only knowledge point view returned by the API. */
export interface KnowledgePointView {
  code: string
  name: string
  description: string
  category: string
  parent_code: string | null
  sort_order: number
  graph_role: KnowledgeGraphRole
}

/** 中文：知识点之间的先修关系视图。 English: Prerequisite relationship view between knowledge points. */
export interface KnowledgePrerequisiteView {
  knowledge_code: string
  prerequisite_code: string
  strength: PrerequisiteStrength
  required_level: MasteryLevel
  rationale: string
}

/** 中文：完整知识图谱接口响应。 English: Complete knowledge graph API response. */
export interface KnowledgeGraphView {
  catalog_code: string
  catalog_version: string
  title: string
  subject: string
  grade_band: string
  root_code: string
  knowledge_points: KnowledgePointView[]
  prerequisites: KnowledgePrerequisiteView[]
}

/** 中文：学生端可选择的知识目录摘要。 English: Curriculum catalog summary available to learners. */
export interface CurriculumCatalogSummary {
  code: string
  version: string
  title: string
  subject: string
  grade_band: string
  topic: string
  root_code: string
}

/** 中文：题型中成对展示的框架思路与实际解题步骤。 English: A framework idea paired with its worked solution step in a problem type. */
export interface SolutionFrameworkStep {
  title: string
  framework: string
  solution_step: string
  formula_latex: string | null
}

/** 中文：知识点详情中的已发布内容。 English: Published content in a knowledge-point detail response. */
export interface PublishedKnowledgeContent {
  content_type: 'definition' | 'property' | 'theorem' | 'formula' | 'problem_type'
  content_key: string
  title: string
  summary: string
  body_markdown: string
  formula_latex: string | null
  structured_json: Record<string, unknown>
  solution_framework_json: SolutionFrameworkStep[]
  sort_order: number
}

/** 中文：直接相连的先修或后续知识点。 English: Direct prerequisite or dependent knowledge point. */
export interface RelatedKnowledgePoint {
  code: string
  name: string
  strength: PrerequisiteStrength
  required_level: MasteryLevel
  rationale: string
}

/** 中文：知识点及其数据库教学内容详情。 English: Knowledge point detail with database-backed teaching content. */
export interface KnowledgePointDetailView {
  code: string
  name: string
  description: string
  category: string
  grade_band: string
  parent_code: string | null
  catalog_code: string | null
  catalog_version: string | null
  catalog_title: string | null
  root_code: string
  contents: PublishedKnowledgeContent[]
  prerequisites: RelatedKnowledgePoint[]
  dependents: RelatedKnowledgePoint[]
}

/** 中文：学生端可见的数学方法。 English: Learner-facing mathematical method. */
export interface PublishedThinkingMethod {
  code: string
  parent_method_code: string | null
  name: string
  kind: 'thought' | 'strategy' | 'technique' | 'theorem_tool'
  level: '入门' | '深化' | '进阶'
  goal: string
  example: string
  grade_bands: string[]
  domain_tags: string[]
  aliases: string[]
  detail: Record<string, unknown>
  sort_order: number
}

/** 中文：学生端数学思想分类及其方法。 English: Learner-facing thinking category and its methods. */
export interface PublishedThinkingMethodCategory {
  code: string
  label: string
  symbol: string
  focus: string
  description: string
  reminder: string
  sort_order: number
  methods: PublishedThinkingMethod[]
}

/** 中文：带分类信息的数学方法详情。 English: Mathematical method detail with category metadata. */
export interface ThinkingMethodDetailView extends PublishedThinkingMethod {
  category_code: string
  category_label: string
}

/** 中文：读取学生端可用的知识目录。 English: Fetches curriculum catalogs available to learners. */
export async function listCurriculumCatalogs() {
  const response = await authorizedFetch('/curriculum/catalogs')
  return parseResponse<CurriculumCatalogSummary[]>(response)
}

/**
 * 中文：读取指定学科、学段和根知识点的知识图谱。
 * English: Fetches the knowledge graph for a subject, grade band, and root knowledge point.
 */
export async function getKnowledgeGraph(input: {
  rootCode?: string
} = {}) {
  const query = new URLSearchParams({
    root_code: input.rootCode ?? 'UC.C1',
  })
  const response = await authorizedFetch(`/curriculum/knowledge-graph?${query}`)
  return parseResponse<KnowledgeGraphView>(response)
}

/** 中文：读取知识点、已发布正文及其直接关系。 English: Fetches a point, published content, and direct relationships. */
export async function getKnowledgePointDetail(code: string) {
  const response = await authorizedFetch(`/curriculum/knowledge-points/${encodeURIComponent(code)}`)
  return parseResponse<KnowledgePointDetailView>(response)
}

/** 中文：读取数据库维护的数学思想与方法总目录。 English: Fetches the database-managed thinking-method catalog. */
export async function getThinkingMethodCatalog() {
  const response = await authorizedFetch('/curriculum/thinking-methods')
  return parseResponse<PublishedThinkingMethodCategory[]>(response)
}

/** 中文：按稳定编码读取一个数学方法详情。 English: Fetches one mathematical method detail by stable code. */
export async function getThinkingMethodDetail(code: string) {
  const response = await authorizedFetch(`/curriculum/thinking-methods/${encodeURIComponent(code)}`)
  return parseResponse<ThinkingMethodDetailView>(response)
}
