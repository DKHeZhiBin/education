import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { Dashboard } from "../../types";

const contentNames: Record<string, string> = { definition: "定义", property: "性质", theorem: "定理", formula: "公式", problem_type: "题型" };

export function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api<Dashboard>("/admin/curriculum/dashboard").then(setData).catch(reason => setError(reason.message)); }, []);
  return <div className="page"><header className="page-header"><div><p className="eyebrow">CONTENT OPERATIONS</p><h1>知识内容总览</h1><p>查看星图节点与教学内容的维护进度</p></div></header>
    {error && <div className="error-banner">{error}</div>}
    <div className="stat-grid">{[
      ["知识目录", data?.catalogs ?? "—"], ["知识点", data?.knowledge_points ?? "—"], ["启用节点", data?.active_points ?? "—"], ["先修关系", data?.relations ?? "—"], ["已发布内容", data?.published_contents ?? "—"], ["待完善草稿", data?.draft_contents ?? "—"],
    ].map(([label, value]) => <article className="stat-card" key={label}><span>{label}</span><strong>{value}</strong></article>)}</div>
    <section className="panel"><div className="panel-title"><div><h2>内容构成</h2><p>知识点下五类内容的当前数量</p></div></div><div className="content-breakdown">{Object.entries(contentNames).map(([key, label]) => <div key={key}><span>{label}</span><strong>{data?.contents_by_type[key] ?? 0}</strong><i style={{ width: `${Math.min(100, (data?.contents_by_type[key] ?? 0) * 8)}%` }} /></div>)}</div></section>
  </div>;
}
