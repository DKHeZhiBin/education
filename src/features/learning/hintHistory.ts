import type { TutorReply } from '../../services/tutoring'

export type HintLevel = 1 | 2 | 3 | 4
export type HintHistory = Partial<Record<HintLevel, TutorReply>>

function storageKey(sessionId: string) {
  return `learning-hints:${sessionId}`
}

export function loadHintHistory(sessionId: string): HintHistory {
  try {
    const raw = window.sessionStorage.getItem(storageKey(sessionId))
    return raw ? JSON.parse(raw) as HintHistory : {}
  } catch {
    return {}
  }
}

export function rememberHintReply(sessionId: string, reply: TutorReply | null): HintHistory {
  const history = loadHintHistory(sessionId)
  if (!reply?.hint_level || reply.hint_level < 1 || reply.hint_level > 4) return history
  const next = { ...history, [reply.hint_level]: reply }
  window.sessionStorage.setItem(storageKey(sessionId), JSON.stringify(next))
  return next
}
