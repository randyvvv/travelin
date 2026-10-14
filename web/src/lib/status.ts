import type { TripStatus } from './types'

export const tripStatusLabel: Record<TripStatus, string> = {
  gathering: 'Collecting Reels',
  extracting: 'Finding places',
  voting: 'Voting',
  planning: 'Planning',
  planned: 'Planned',
  splitting: 'Splitting the bill',
  settling: 'Settling up',
  settled: 'Settled',
}
