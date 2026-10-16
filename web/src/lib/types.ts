// Firestore document shapes. Keep in sync with docs/IMPLEMENTATION_PLAN.md §6.
import type { Timestamp } from 'firebase/firestore'

export type WithId<T> = T & { id: string }

export interface LatLng {
  lat: number
  lng: number
}

export type TripStatus =
  | 'gathering'
  | 'extracting'
  | 'voting'
  | 'planning'
  | 'planned'
  | 'splitting'
  | 'settling'
  | 'settled'

export interface Trip {
  name: string
  startDate: string
  endDate: string
  origin: string
  // lat/lng are null until the destination is geocoded
  destination: { name: string; lat: number | null; lng: number | null }
  hostUid: string
  memberUids: string[]
  inviteCode: string
  status: TripStatus
  votingDeadline: Timestamp | null
  split: { version: number }
  pipeline?: {
    stage: string
    done: number
    total: number
    dropped: { name: string; reason: string }[]
    error?: string
    usedFallback?: boolean
  }
  paymentStatus?: Record<string, 'unpaid' | 'waiting' | 'settled'>
  planning?: {
    stage: 'starting' | 'drafting' | 'revising' | 'done' | 'failed'
    attempt: number
    error?: string
  }
  isDemo: boolean
  createdAt: Timestamp
}

export type Vote = 'must' | 'maybe' | 'skip'

export interface Preferences {
  budgetIdr: number
  interests: string[]
  dietary: string[]
  skip: string[]
}

export interface Member {
  displayName: string
  photoURL: string
  role: 'host' | 'member'
  isBot: boolean
  prefs: Preferences
  prefsDone: boolean
  votes: Record<string, Vote>
  votesSubmittedAt: Timestamp | null
  splitApprovedVersion: number | null
  joinedAt: Timestamp
}

export interface Reel {
  uploaderUid: string
  source: 'upload' | 'link'
  storagePath?: string
  sourceUrl?: string
  platform: 'instagram' | 'tiktok' | 'youtube' | 'other'
  status: 'queued' | 'processing' | 'done' | 'failed' | 'link_only'
  contentHash?: string
  fileName?: string
  placesFound?: number
  error?: string
  createdAt: Timestamp
}

export interface MapsSource {
  title: string
  uri: string
  placeId?: string
}

export interface Place {
  name: string
  category: string
  address: string
  location: LatLng
  googleMapsUri: string
  rating?: number
  userRatingCount?: number
  priceLevel?: string
  openingHours?: { weekdayDescriptions?: string[] } | null
  photoName?: string
  mentions: { reelId: string; atSec: number; evidence: string }[]
  savedBy: string[]
  summary: {
    highlights: string[]
    bestTime: string
    priceNote: string
    dietaryNote: string
    crowdNote: string
  }
  mapsSources: MapsSource[]
  tally: Record<Vote, number>
}

export interface Stop {
  placeId: string
  start: string
  end: string
  attendees: string[]
  estCostPerPersonIdr: number
  note: string
}

export interface ItineraryDay {
  date: string
  title: string
  stops: Stop[]
}

export interface Plan {
  whyThisPlan: string
  compromises: { uid: string; gaveUp: string; got: string; reason: string }[]
  estimates: { uid: string; amountIdr: number }[]
  warnings: string[]
  stay: {
    sku: string
    type: 'stay' | 'tour'
    title: string
    priceIdr: number
    unit: 'night' | 'person'
    reason: string
  } | null
  model: string
  attempts: number
  generatedAt: Timestamp
}

export type SplitMode = 'equal' | 'shares' | 'exact' | 'items'

export interface ExpenseItem {
  name: string
  unitPriceIdr: number
  qty: number
  portions: Record<string, number>
}

export interface Expense {
  title: string
  amountIdr: number
  paidBy: string
  split: {
    mode: SplitMode
    participants: string[]
    shares: Record<string, number> | null
    exact: Record<string, number> | null
  }
  items: ExpenseItem[]
  taxIdr: number
  serviceIdr: number
  discountIdr: number
  computedShares: Record<string, number>
  receiptPath: string | null
  source: 'manual' | 'receipt' | 'booking'
  createdBy: string
  createdAt: Timestamp
  updatedAt: Timestamp
}

export type TransferStatus = 'unpaid' | 'waiting' | 'confirmed'

export interface Transfer {
  from: string
  to: string
  amountIdr: number
  status: TransferStatus
  splitVersion: number
  sentAt?: Timestamp
  confirmedAt?: Timestamp
}

export interface PaymentAmount {
  currency: string
  value: number
}

/** AP2 CartMandate as the merchant signed it (snake_case, as AP2 defines it). */
export interface CartMandate {
  contents: {
    id: string
    cart_expiry: string
    merchant_name: string
    payment_request: {
      details: {
        display_items: { label: string; amount: PaymentAmount }[]
        total: { label: string; amount: PaymentAmount }
      }
    }
  }
  merchant_authorization: string | null
}

export interface Booking {
  sku: string
  type: 'stay' | 'tour'
  title: string
  amountIdr: number
  guests: number
  payerUid: string
  cartMandate: CartMandate
  cartHash: string
  approvals: Record<string, { at: Timestamp | null; cartHash: string }>
  status: 'approving' | 'paying' | 'paid' | 'failed'
  failureReason?: string
  receipt?: { order_id: string; amount_idr: number; merchant_name: string; paid_at: string }
  createdAt: Timestamp
}

export type NotificationType =
  | 'joined'
  | 'voting_open'
  | 'voting_deadline'
  | 'plan_ready'
  | 'split_reopened'
  | 'approval_needed'
  | 'bill'
  | 'payment_sent'
  | 'payment_confirmed'
  | 'booking_proposed'
  | 'booking_paid'

export interface AppNotification {
  type: NotificationType
  text: string
  tripId: string
  link: string
  read: boolean
  createdAt: Timestamp
}
