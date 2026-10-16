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

/** FastAPI sends a string for HTTPException and a list for validation errors. */
function describe(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const first: unknown = detail[0]
    if (first && typeof first === 'object' && 'msg' in first && typeof first.msg === 'string') {
      return first.msg.replace(/^Value error, /, '')
    }
  }
  return fallback
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
    throw new ApiError(response.status, describe(detail, response.statusText))
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

/** A message to show the user for any error thrown by `api`. */
export function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback
}

export interface CreateTripResponse {
  tripId: string
  inviteCode: string
}

export interface InvitePreview {
  tripId: string
  name: string
  destination: string
  startDate: string
  endDate: string
  hostName: string
  memberCount: number
  alreadyMember: boolean
  joinable: boolean
}

export interface SplitPreview {
  balances: Record<string, number>
  transfers: { from: string; to: string; amountIdr: number }[]
}

export interface ScanResult {
  merchant: string
  items: { name: string; unitPriceIdr: number; qty: number }[]
  subtotalIdr: number
  taxIdr: number
  serviceIdr: number
  discountIdr: number
  totalIdr: number
  warnings: string[]
}

/** What the expense editor receives after a receipt scan. */
export interface ScannedReceipt extends ScanResult {
  storagePath: string
}

export interface PlaceHit {
  placeId: string
  name: string
  address: string
  rating: number | null
  userRatingCount: number | null
  category: string
  onBoard: boolean
}
