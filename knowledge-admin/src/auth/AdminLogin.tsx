import { FormEvent, useState } from "react";
import { login } from "../api/client";
import type { AdminUser } from "../types";

export function AdminLogin({ onLogin }: { onLogin: (user: AdminUser) => void }) {
  const [email, setEmail] = useState("admin.demo@example.com");
  const [password, setPassword] = useState("MathTutorDemo2026!");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { onLogin((await login(email, password)).user); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "登录失败"); }
    finally { setBusy(false); }
  }

  return <main className="login-page">
    <section className="login-card">
      <div className="brand-mark">数</div><p className="eyebrow">MATH KNOWLEDGE STUDIO</p>
      <h1>数知内容管理台</h1><p className="muted">维护知识星图、先修关系和教学内容</p>
      <form onSubmit={submit} className="form-stack">
        <label>管理员邮箱<input value={email} onChange={e => setEmail(e.target.value)} type="email" required /></label>
        <label>密码<input value={password} onChange={e => setPassword(e.target.value)} type="password" required /></label>
        {error && <div className="error-banner">{error}</div>}
        <button className="primary" disabled={busy}>{busy ? "正在登录…" : "进入管理台"}</button>
      </form>
    </section>
  </main>;
}
