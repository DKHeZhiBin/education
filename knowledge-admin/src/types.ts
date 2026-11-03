export type ContentType = "definition" | "property" | "theorem" | "formula" | "problem_type";
export type PublishStatus = "draft" | "published" | "archived";
export interface SolutionFrameworkStep { title: string; framework: string; solution_step: string; formula_latex: string | null }

export interface AdminUser { id: string; email: string; role: string; display_name?: string }
export interface TokenResponse { access_token: string; user: AdminUser }
export interface Dashboard { catalogs: number; knowledge_points: number; active_points: number; relations: number; contents_by_type: Record<string, number>; draft_contents: number; published_contents: number }
export interface Catalog { id: number; code: string; version: string; title: string; subject: string; grade_band: string; topic: string; sort_order: number; status: PublishStatus; version_lock: number; knowledge_point_count: number; updated_at: string }
export interface KnowledgePoint { id: number; catalog_id: number | null; subject: string; grade_band: string; code: string; name: string; description: string; category: "foundation" | "core" | "extension"; parent_code: string | null; sort_order: number; active: boolean; version_lock: number; content_counts: Record<ContentType, number> }
export interface Relation { knowledge_code: string; prerequisite_code: string; knowledge_name: string; prerequisite_name: string; strength: "required" | "recommended"; required_level: "introduced" | "familiar" | "proficient"; rationale: string }
export interface KnowledgeContent { id: string; knowledge_point_id: number; knowledge_point_code: string; knowledge_point_name: string; content_type: ContentType; content_key: string; title: string; summary: string; body_markdown: string; formula_latex: string | null; structured_json: Record<string, unknown>; solution_framework_json: SolutionFrameworkStep[]; status: PublishStatus; sort_order: number; version_lock: number; created_at: string; updated_at: string }
export type ThinkingMethodKind = "thought" | "strategy" | "technique" | "theorem_tool";
export type ThinkingMethodLevel = "入门" | "深化" | "进阶";
export interface ThinkingMethodCategory { id: number; code: string; label: string; symbol: string; focus: string; description: string; reminder: string; sort_order: number; status: PublishStatus; version_lock: number; method_count: number; updated_at: string }
export interface ThinkingMethod { id: number; code: string; category_id: number; category_code: string; category_label: string; parent_method_id: number | null; parent_method_code: string | null; name: string; kind: ThinkingMethodKind; level: ThinkingMethodLevel; goal: string; example: string; grade_bands: string[]; domain_tags: string[]; aliases: string[]; detail: Record<string, unknown>; sort_order: number; status: PublishStatus; version_lock: number; updated_at: string }
