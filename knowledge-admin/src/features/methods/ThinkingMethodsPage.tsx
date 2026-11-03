import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import { Modal } from "../../components/Modal";
import type { PublishStatus, ThinkingMethod, ThinkingMethodCategory, ThinkingMethodKind, ThinkingMethodLevel } from "../../types";

const emptyCategory = { code: "", label: "", symbol: "", focus: "", description: "", reminder: "同一方法统一记录；学段与实际表现用于推荐讲解深度，不是访问门槛。", sort_order: 0, status: "draft" as PublishStatus };
const emptyMethod = { code: "", category_id: "", parent_method_id: "", name: "", kind: "technique" as ThinkingMethodKind, level: "深化" as ThinkingMethodLevel, goal: "", example: "", grade_bands: "university", domain_tags: "", aliases: "", detail: "{}", sort_order: 0, status: "draft" as PublishStatus };

/** 中文：维护数学思想分类、方法层级和结构化教学内容。 English: Manages thinking categories, method hierarchy, and structured teaching content. */
export function ThinkingMethodsAdminPage() {
  const [categories, setCategories] = useState<ThinkingMethodCategory[]>([]);
  const [methods, setMethods] = useState<ThinkingMethod[]>([]);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [editingCategory, setEditingCategory] = useState<ThinkingMethodCategory | null | undefined>();
  const [editingMethod, setEditingMethod] = useState<ThinkingMethod | null | undefined>();
  const [categoryForm, setCategoryForm] = useState(emptyCategory);
  const [methodForm, setMethodForm] = useState(emptyMethod);
  const [error, setError] = useState("");

  /** 中文：从管理接口刷新分类和方法。 English: Refreshes categories and methods from administration APIs. */
  const load = () => Promise.all([
    api<ThinkingMethodCategory[]>("/admin/thinking-methods/categories"),
    api<ThinkingMethod[]>("/admin/thinking-methods/methods"),
  ]).then(([categoryRows, methodRows]) => { setCategories(categoryRows); setMethods(methodRows); }).catch(reason => setError(reason.message));

  useEffect(() => { void load(); }, []);

  const visibleMethods = useMemo(() => methods.filter(item =>
    (!categoryFilter || item.category_id === Number(categoryFilter)) &&
    (!statusFilter || item.status === statusFilter) &&
    (!search.trim() || `${item.name} ${item.code} ${item.goal}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()))
  ), [categoryFilter, methods, search, statusFilter]);

  /** 中文：打开分类编辑器。 English: Opens the category editor. */
  function openCategory(item?: ThinkingMethodCategory) {
    setEditingCategory(item ?? null);
    setCategoryForm(item ? { code: item.code, label: item.label, symbol: item.symbol, focus: item.focus, description: item.description, reminder: item.reminder, sort_order: item.sort_order, status: item.status } : emptyCategory);
  }

  /** 中文：保存思想分类并携带乐观锁版本。 English: Saves a category with its optimistic-lock version. */
  async function saveCategory(event: FormEvent) {
    event.preventDefault(); setError("");
    try {
      await api(editingCategory ? `/admin/thinking-methods/categories/${editingCategory.id}` : "/admin/thinking-methods/categories", { method: editingCategory ? "PUT" : "POST", body: JSON.stringify({ ...categoryForm, expected_version: editingCategory?.version_lock }) });
      setEditingCategory(undefined); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "分类保存失败"); }
  }

  /** 中文：打开方法编辑器并将结构化字段转为文本。 English: Opens the method editor and serializes structured fields as text. */
  function openMethod(item?: ThinkingMethod) {
    setEditingMethod(item ?? null);
    setMethodForm(item ? { code: item.code, category_id: String(item.category_id), parent_method_id: item.parent_method_id ? String(item.parent_method_id) : "", name: item.name, kind: item.kind, level: item.level, goal: item.goal, example: item.example, grade_bands: "university", domain_tags: item.domain_tags.join(", "), aliases: item.aliases.join(", "), detail: JSON.stringify(item.detail, null, 2), sort_order: item.sort_order, status: item.status } : { ...emptyMethod, category_id: categoryFilter || String(categories[0]?.id ?? "") });
  }

  /** 中文：保存方法并校验详情 JSON。 English: Saves a method after validating its detail JSON. */
  async function saveMethod(event: FormEvent) {
    event.preventDefault(); setError("");
    try {
      const split = (value: string) => value.split(/[,，]/).map(item => item.trim()).filter(Boolean);
      const payload = { ...methodForm, category_id: Number(methodForm.category_id), parent_method_id: methodForm.parent_method_id ? Number(methodForm.parent_method_id) : null, grade_bands: ["university"], domain_tags: split(methodForm.domain_tags), aliases: split(methodForm.aliases), detail: JSON.parse(methodForm.detail || "{}"), expected_version: editingMethod?.version_lock };
      await api(editingMethod ? `/admin/thinking-methods/methods/${editingMethod.id}` : "/admin/thinking-methods/methods", { method: editingMethod ? "PUT" : "POST", body: JSON.stringify(payload) });
      setEditingMethod(undefined); await load();
    } catch (reason) { setError(reason instanceof SyntaxError ? "详情 JSON 格式不正确" : reason instanceof Error ? reason.message : "方法保存失败"); }
  }

  /** 中文：归档一个思想分类。 English: Archives one thinking category. */
  async function archiveCategory(item: ThinkingMethodCategory) {
    if (!window.confirm(`确定归档分类“${item.label}”吗？\n\n分类下不能存在未归档方法。`)) return;
    try { await api(`/admin/thinking-methods/categories/${item.id}`, { method: "DELETE" }); await load(); } catch (reason) { setError(reason instanceof Error ? reason.message : "归档失败"); }
  }

  /** 中文：归档一个数学方法。 English: Archives one mathematical method. */
  async function archiveMethod(item: ThinkingMethod) {
    if (!window.confirm(`确定归档方法“${item.name}”吗？\n\n归档后学生端将不再展示。`)) return;
    try { await api(`/admin/thinking-methods/methods/${item.id}`, { method: "DELETE" }); await load(); } catch (reason) { setError(reason instanceof Error ? reason.message : "归档失败"); }
  }

  return <div className="page methods-admin-page">
    <header className="page-header"><div><p className="eyebrow">THINKING METHODS</p><h1>思想与方法</h1><p>维护大学高数的方法分类、层级和教学详情</p></div><div className="header-actions"><button className="secondary" onClick={() => openCategory()}>＋ 新建分类</button><button className="primary" onClick={() => openMethod()}>＋ 新建方法</button></div></header>
    {error && <div className="error-banner">{error}</div>}
    <section className="method-category-cards">{categories.map(item => <article className={`panel method-category-admin-card ${item.status}`} key={item.id}><header><span>{item.symbol || "·"}</span><div><strong>{item.label}</strong><small>{item.code} · {item.method_count} 个方法</small></div></header><p>{item.description}</p><footer><span className={`status ${item.status}`}>{statusName(item.status)}</span><button className="text-button" onClick={() => openCategory(item)}>编辑</button><button className="text-button danger" onClick={() => archiveCategory(item)}>归档</button></footer></article>)}</section>
    <section className="panel method-admin-panel"><div className="method-admin-toolbar"><select value={categoryFilter} onChange={event => setCategoryFilter(event.target.value)}><option value="">全部分类</option>{categories.map(item => <option value={item.id} key={item.id}>{item.label}</option>)}</select><select value={statusFilter} onChange={event => setStatusFilter(event.target.value)}><option value="">全部状态</option><option value="published">已发布</option><option value="draft">草稿</option><option value="archived">已归档</option></select><input value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索名称、编码或目标" /><span>{visibleMethods.length} 项</span></div>
      <div className="table-panel"><table><thead><tr><th>方法</th><th>分类</th><th>层级 / 深度</th><th>适用范围</th><th>状态</th><th></th></tr></thead><tbody>{visibleMethods.map(item => <tr key={item.id}><td><strong>{item.name}</strong><small>{item.code}</small></td><td>{item.category_label}</td><td>{kindName(item.kind)} · {item.level}</td><td>大学高数</td><td><span className={`status ${item.status}`}>{statusName(item.status)}</span></td><td><div className="row-actions"><button className="text-button" onClick={() => openMethod(item)}>编辑</button>{item.status !== "archived" && <button className="text-button danger" onClick={() => archiveMethod(item)}>归档</button>}</div></td></tr>)}</tbody></table>{!visibleMethods.length && <div className="empty">没有符合条件的方法</div>}</div>
    </section>
    {editingCategory !== undefined && <Modal title={editingCategory ? "编辑思想分类" : "新建思想分类"} onClose={() => setEditingCategory(undefined)}><form className="form-grid" onSubmit={saveCategory}><label>分类名称<input value={categoryForm.label} onChange={e => setCategoryForm({ ...categoryForm, label: e.target.value })} required /></label><label>稳定编码<input value={categoryForm.code} onChange={e => setCategoryForm({ ...categoryForm, code: e.target.value })} required /></label><label>图形符号<input value={categoryForm.symbol} onChange={e => setCategoryForm({ ...categoryForm, symbol: e.target.value })} /></label><label>思想定位<input value={categoryForm.focus} onChange={e => setCategoryForm({ ...categoryForm, focus: e.target.value })} /></label><label>显示顺序<input type="number" min="0" value={categoryForm.sort_order} onChange={e => setCategoryForm({ ...categoryForm, sort_order: Number(e.target.value) })} /></label><label>状态<select value={categoryForm.status} onChange={e => setCategoryForm({ ...categoryForm, status: e.target.value as PublishStatus })}><option value="draft">草稿</option><option value="published">已发布</option><option value="archived">已归档</option></select></label><label className="full">分类说明<textarea value={categoryForm.description} onChange={e => setCategoryForm({ ...categoryForm, description: e.target.value })} /></label><label className="full">学习提醒<textarea value={categoryForm.reminder} onChange={e => setCategoryForm({ ...categoryForm, reminder: e.target.value })} /></label><footer className="form-actions full"><button type="button" onClick={() => setEditingCategory(undefined)}>取消</button><button className="primary">保存分类</button></footer></form></Modal>}
    {editingMethod !== undefined && <Modal title={editingMethod ? "编辑数学方法" : "新建数学方法"} onClose={() => setEditingMethod(undefined)} wide><form className="form-grid" onSubmit={saveMethod}><label>方法名称<input value={methodForm.name} onChange={e => setMethodForm({ ...methodForm, name: e.target.value })} required /></label><label>稳定编码<input value={methodForm.code} onChange={e => setMethodForm({ ...methodForm, code: e.target.value })} required /></label><label>所属分类<select value={methodForm.category_id} onChange={e => setMethodForm({ ...methodForm, category_id: e.target.value, parent_method_id: "" })} required><option value="">请选择</option>{categories.filter(item => item.status !== "archived").map(item => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label><label>上级方法<select value={methodForm.parent_method_id} onChange={e => setMethodForm({ ...methodForm, parent_method_id: e.target.value })}><option value="">无上级</option>{methods.filter(item => item.category_id === Number(methodForm.category_id) && item.id !== editingMethod?.id && item.status !== "archived").map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label>内容层级<select value={methodForm.kind} onChange={e => setMethodForm({ ...methodForm, kind: e.target.value as ThinkingMethodKind })}><option value="thought">思想</option><option value="strategy">策略</option><option value="technique">技巧</option><option value="theorem_tool">定理工具</option></select></label><label>学习深度<select value={methodForm.level} onChange={e => setMethodForm({ ...methodForm, level: e.target.value as ThinkingMethodLevel })}><option>入门</option><option>深化</option><option>进阶</option></select></label><label>显示顺序<input type="number" min="0" value={methodForm.sort_order} onChange={e => setMethodForm({ ...methodForm, sort_order: Number(e.target.value) })} /></label><label>状态<select value={methodForm.status} onChange={e => setMethodForm({ ...methodForm, status: e.target.value as PublishStatus })}><option value="draft">草稿</option><option value="published">已发布</option><option value="archived">已归档</option></select></label><label className="full">核心目标<textarea value={methodForm.goal} onChange={e => setMethodForm({ ...methodForm, goal: e.target.value })} /></label><label className="full">识别信号 / 应用示例<textarea value={methodForm.example} onChange={e => setMethodForm({ ...methodForm, example: e.target.value })} /></label><label>知识领域（逗号分隔）<input value={methodForm.domain_tags} onChange={e => setMethodForm({ ...methodForm, domain_tags: e.target.value })} /></label><label className="full">别名 / 搜索词（逗号分隔）<input value={methodForm.aliases} onChange={e => setMethodForm({ ...methodForm, aliases: e.target.value })} /></label><label className="full">结构化详情 JSON<textarea className="editor method-detail-json" value={methodForm.detail} onChange={e => setMethodForm({ ...methodForm, detail: e.target.value })} /></label><footer className="form-actions full"><button type="button" onClick={() => setEditingMethod(undefined)}>取消</button><button className="primary">保存方法</button></footer></form></Modal>}
  </div>;
}

/** 中文：返回发布状态中文名。 English: Returns a Chinese publish-status label. */
function statusName(status: PublishStatus) { return status === "published" ? "已发布" : status === "draft" ? "草稿" : "已归档"; }
/** 中文：返回方法内容层级中文名。 English: Returns a Chinese method-kind label. */
function kindName(kind: ThinkingMethodKind) { return ({ thought: "思想", strategy: "策略", technique: "技巧", theorem_tool: "定理工具" } as const)[kind]; }
