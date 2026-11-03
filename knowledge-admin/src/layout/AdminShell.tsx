import { NavLink, Outlet } from "react-router-dom";
import type { AdminUser } from "../types";

const links = [
  ["/", "总览", "◫"], ["/catalogs", "知识目录", "▤"], ["/points", "知识点与内容", "✦"], ["/relations", "先修关系", "⌁"], ["/methods", "思想与方法", "∵"],
];

export function AdminShell({ user, onLogout }: { user: AdminUser; onLogout: () => void }) {
  return <div className="admin-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark small">数</span><div><strong>数知</strong><small>内容管理台</small></div></div>
      <nav>{links.map(([to, label, icon]) => <NavLink key={to} to={to} end={to === "/"}><span>{icon}</span>{label}</NavLink>)}</nav>
      <div className="sidebar-user"><span className="avatar">管</span><div><strong>{user.display_name ?? "知识管理员"}</strong><small>{user.email}</small></div><button onClick={onLogout}>退出</button></div>
    </aside>
    <section className="workspace"><Outlet /></section>
  </div>;
}
