import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { api, tokenStore } from "./api/client";
import { AdminLogin } from "./auth/AdminLogin";
import { CatalogsPage } from "./features/catalogs/CatalogsPage";
import { DashboardPage } from "./features/dashboard/DashboardPage";
import { KnowledgePointsPage } from "./features/points/KnowledgePointsPage";
import { RelationsPage } from "./features/relations/RelationsPage";
import { ThinkingMethodsAdminPage } from "./features/methods/ThinkingMethodsPage";
import { AdminShell } from "./layout/AdminShell";
import type { AdminUser } from "./types";

export default function App() {
  const [user, setUser] = useState<AdminUser | null>(null); const [checking, setChecking] = useState(Boolean(tokenStore.get()));
  useEffect(() => { if (!tokenStore.get()) return; api<AdminUser>("/auth/me").then(value => { if (value.role === "admin") setUser(value); else tokenStore.clear(); }).catch(() => tokenStore.clear()).finally(() => setChecking(false)); }, []);
  if (checking) return <div className="boot-screen">正在进入管理台…</div>;
  if (!user) return <AdminLogin onLogin={setUser} />;
  return <BrowserRouter><Routes><Route element={<AdminShell user={user} onLogout={() => { tokenStore.clear(); setUser(null); }} />}><Route index element={<DashboardPage />} /><Route path="catalogs" element={<CatalogsPage />} /><Route path="points" element={<KnowledgePointsPage />} /><Route path="relations" element={<RelationsPage />} /><Route path="methods" element={<ThinkingMethodsAdminPage />} /><Route path="*" element={<Navigate to="/" replace />} /></Route></Routes></BrowserRouter>;
}
