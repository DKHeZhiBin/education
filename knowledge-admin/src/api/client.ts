import type { TokenResponse } from "../types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/v1";
const TOKEN_KEY = "knowledge_admin_access_token";

export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (value: string) => sessionStorage.setItem(TOKEN_KEY, value),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

async function refreshAccessToken(): Promise<string | null> {
  const response = await fetch(`${BASE_URL}/auth/refresh`, { method: "POST", credentials: "include" });
  if (!response.ok) return null;
  const payload = await response.json() as TokenResponse;
  tokenStore.set(payload.access_token);
  return payload.access_token;
}

export async function api<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response = await fetch(`${BASE_URL}${path}`, { ...options, headers, credentials: "include" });
  if (response.status === 401 && retry) {
    const refreshedToken = await refreshAccessToken();
    if (refreshedToken) {
      // 中文：直接更新 Headers，避免大小写不同的两个 Authorization 被合并后导致重试仍然返回 401。
      // English: Mutate Headers directly so differently cased Authorization keys cannot be merged and invalidate the retry.
      headers.set("Authorization", `Bearer ${refreshedToken}`);
      response = await fetch(`${BASE_URL}${path}`, { ...options, headers, credentials: "include" });
    }
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { message?: string; detail?: string } | null;
    throw new Error(body?.message ?? body?.detail ?? `请求失败（${response.status}）`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const body = new URLSearchParams({ username: email, password });
  const response = await fetch(`${BASE_URL}/auth/token`, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, credentials: "include", body });
  if (!response.ok) throw new Error("登录失败，请检查管理员邮箱和密码");
  const payload = await response.json() as TokenResponse;
  if (payload.user.role !== "admin") throw new Error("该账号没有知识管理权限");
  tokenStore.set(payload.access_token);
  return payload;
}
