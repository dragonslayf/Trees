/**
 * POST /api/session/init 的统一解析（数据管理页与单木分割页共用逻辑形态）
 */
export type SessionInitOutcome =
  | { ok: true; data: Record<string, unknown> }
  | { ok: false; reason: 'full' | 'error'; detail: string; status: number }

export async function fetchSessionInit(
  api: (path: string) => string,
): Promise<SessionInitOutcome> {
  const r = await fetch(api('/api/session/init'), {
    method: 'POST',
    credentials: 'include',
  })
  const data = (await r.json().catch(() => ({}))) as Record<string, unknown>

  if (r.status === 429) {
    return {
      ok: false,
      reason: 'full',
      detail:
        typeof data.detail === 'string'
          ? data.detail
          : '当前活跃会话已达上限（10），请稍后再试',
      status: 429,
    }
  }
  if (!r.ok) {
    return {
      ok: false,
      reason: 'error',
      detail:
        typeof data.detail === 'string'
          ? data.detail
          : `会话建立失败 (${r.status})`,
      status: r.status,
    }
  }
  return { ok: true, data }
}
