import { computed } from 'vue'

/**
 * 构建 API 请求路径，并提示「为何开发环境要留空 VITE_API_BASE_URL」。
 * 留空时使用同源相对路径（配合 Vite proxy），Cookie 与页面一致；填 127.0.0.1 而页面用 localhost 会导致会话丢失。
 */
export function useApiBase() {
  const raw = import.meta.env.VITE_API_BASE_URL
  const useSameOrigin =
    raw === undefined || raw === null || String(raw).trim() === ''

  function api(path: string): string {
    const p = path.startsWith('/') ? path : `/${path}`
    if (useSameOrigin) return p
    return `${String(raw).replace(/\/$/, '')}${p}`
  }

  const apiRootHint = computed(() => {
    if (useSameOrigin) {
      if (typeof window === 'undefined') return '同源 /api（Vite 代理）'
      return `${window.location.origin}（经 Vite 代理，Cookie 同源）`
    }
    return String(raw)
  })

  /** 将 api() 返回的相对或绝对地址转为可在新标签打开的完整 URL */
  function toAbsoluteUrl(href: string): string {
    if (href.startsWith('http')) return href
    const p = href.startsWith('/') ? href : `/${href}`
    if (useSameOrigin) {
      if (typeof window === 'undefined') return p
      return new URL(p, window.location.origin).href
    }
    return `${String(raw).replace(/\/$/, '')}${p}`
  }

  return { api, apiRootHint, toAbsoluteUrl, useSameOrigin }
}
