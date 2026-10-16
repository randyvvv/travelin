import type { TripStatus } from './types'

export const tripStatusLabel: Record<TripStatus, string> = {
  gathering: 'Collecting places',
  extracting: 'Finding places',
  voting: 'Voting',
  planning: 'Planning',
  planned: 'Planned',
  splitting: 'Splitting the bill',
  settling: 'Settling up',
  settled: 'Settled',
}

/** Expenses can be added or edited until payments start. */
export const EXPENSE_EDITABLE: ReadonlySet<TripStatus> = new Set(['planned', 'splitting'])

export const paymentLabel: Record<'unpaid' | 'waiting' | 'settled', string> = {
  unpaid: 'Unpaid',
  waiting: 'Waiting',
  settled: 'Settled',
}
