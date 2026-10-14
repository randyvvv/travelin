import { auth } from './firebase'

const baseUrl = import.meta.env.VITE_API_URL

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

interface ApiOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
}

/** Calls travelin-api with the signed-in user's Firebase ID token. */
export async function api<T>(path: string, { method, body }: ApiOptions = {}): Promise<T> {
  const token = await auth.currentUser?.getIdToken()
  const response = await fetch(`${baseUrl}${path}`, {
    method: method ?? (body === undefined ? 'GET' : 'POST'),
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (!response.ok) {
    const detail: unknown = await response
      .json()
      .then((data: { detail?: unknown }) => data.detail)
      .catch(() => undefined)
    throw new ApiError(response.status, typeof detail === 'string' ? detail : response.statusText)
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}
