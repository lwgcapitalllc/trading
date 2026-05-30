import { toast } from 'sonner'

const BASE = '/api'

async function request<T>(path: string, init?: RequestInit, asText?: boolean): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...init?.headers },
      ...init,
    })
  } catch (err) {
    const msg = `Cannot reach backend — is it running? (${err})`
    toast.error(msg)
    throw new Error(msg)
  }
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    let detail = text
    try { detail = JSON.parse(text).detail ?? text } catch { /* not json */ }
    const msg = `${res.status} ${detail}`
    toast.error(msg)
    throw new Error(msg)
  }
  if (asText) return res.text() as Promise<T>
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  get:     <T>(path: string) => request<T>(path),
  getText: (path: string)    => request<string>(path, undefined, true),
  put:     <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  post:    <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  patch:   <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete:  <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}
