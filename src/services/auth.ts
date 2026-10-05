const API_BASE_URL = import.meta.env.VITE_AGENT_API_URL ?? 'http://localhost:8000/v1'
const TOKEN_KEY = 'math-tutor-access-token'

export type UserRole = 'student' | 'guardian' | 'admin'

export interface AuthUser {
  id: string
  email: string
  role: UserRole
  account_status: string
  token_version: number
  display_name: string
  grade_band: string | null
  email_verified: boolean
}

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: AuthUser
}

export interface ActionResponse {
  message: string
  development_action_url: string | null
}

export interface RegistrationResponse {
  user: AuthUser
  message: string
  development_verification_url: string | null
}

export interface GuardianLink {
  id: string
  guardian_user_id: string
  student_user_id: string
  guardian_name: string
  student_name: string
  relationship: string
  status: 'pending' | 'active' | 'revoked'
  consented_at: string | null
  created_at: string
}

export function getAccessToken() {
  return sessionStorage.getItem(TOKEN_KEY)
}

export function hasAccessToken() {
  return Boolean(getAccessToken())
}

export function clearAccessToken() {
  sessionStorage.removeItem(TOKEN_KEY)
}

function saveSession(result: TokenResponse) {
  sessionStorage.setItem(TOKEN_KEY, result.access_token)
  return result
}

let refreshInFlight: Promise<TokenResponse> | null = null

export async function logout() {
  const token = getAccessToken()
  try {
    await fetch(`${API_BASE_URL}/auth/logout`, {
      method: 'POST',
      credentials: 'include',
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    })
  } catch {
    // Local sign-out must still succeed when the API is temporarily unavailable.
  } finally {
    clearAccessToken()
  }
}

export async function login(email: string, password: string) {
  const form = new URLSearchParams({ username: email, password })
  const response = await fetch(`${API_BASE_URL}/auth/token`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form,
  })
  return saveSession(await parseResponse<TokenResponse>(response))
}

export async function refreshAccessToken() {
  if (refreshInFlight) return refreshInFlight
  refreshInFlight = performRefresh()
  try {
    return await refreshInFlight
  } finally {
    refreshInFlight = null
  }
}

async function performRefresh() {
  const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) {
    clearAccessToken()
    await parseResponse(response)
  }
  return saveSession(await response.json() as TokenResponse)
}

export async function register(input: {
  email: string
  password: string
  role: 'student' | 'guardian'
  display_name: string
  grade_band?: string
}) {
  const response = await fetch(`${API_BASE_URL}/auth/register`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  return parseResponse<RegistrationResponse>(response)
}

export async function requestEmailVerification(email: string) {
  return publicJsonRequest<ActionResponse>('/auth/email-verification/request', { email })
}

export async function confirmEmailVerification(token: string) {
  return publicJsonRequest<AuthUser>('/auth/email-verification/confirm', { token })
}

export async function requestPasswordReset(email: string) {
  return publicJsonRequest<ActionResponse>('/auth/password/forgot', { email })
}

export async function resetPassword(token: string, newPassword: string) {
  const response = await fetch(`${API_BASE_URL}/auth/password/reset`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, new_password: newPassword }),
  })
  if (!response.ok) await parseResponse(response)
  clearAccessToken()
}

export async function changePassword(currentPassword: string, newPassword: string) {
  const response = await authorizedFetch('/auth/password/change', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
  if (!response.ok) await parseResponse(response)
  clearAccessToken()
}

export async function getCurrentUser() {
  return authorizedRequest<AuthUser>('/auth/me')
}

export async function listGuardianLinks() {
  return authorizedRequest<GuardianLink[]>('/auth/guardian-links')
}

export async function requestGuardianLink(studentEmail: string, relationship: string) {
  return authorizedRequest<GuardianLink>('/auth/guardian-links', {
    method: 'POST',
    body: JSON.stringify({ student_email: studentEmail, relationship }),
  })
}

export async function acceptGuardianLink(linkId: string) {
  return authorizedRequest<GuardianLink>(`/auth/guardian-links/${linkId}/accept`, {
    method: 'POST',
  })
}

export async function revokeGuardianLink(linkId: string) {
  const response = await authorizedFetch(`/auth/guardian-links/${linkId}`, { method: 'DELETE' })
  if (!response.ok) await parseResponse(response)
}

export async function authorizedFetch(path: string, init?: RequestInit, retry = true): Promise<Response> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getAccessToken() ?? ''}`,
      ...init?.headers,
    },
  })
  if (response.status === 401 && retry) {
    try {
      await refreshAccessToken()
      return authorizedFetch(path, init, false)
    } catch {
      clearAccessToken()
    }
  }
  return response
}

async function authorizedRequest<T>(path: string, init?: RequestInit) {
  const response = await authorizedFetch(path, init)
  return parseResponse<T>(response)
}

async function publicJsonRequest<T>(path: string, body: object) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseResponse<T>(response)
}

export async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? '账号服务暂时不可用，请稍后重试')
  }
  return response.json() as Promise<T>
}
