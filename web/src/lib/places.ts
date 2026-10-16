import type { Member, Place, Vote, WithId } from './types'

export const categoryLabel: Record<string, string> = {
  food: 'Food',
  cafe: 'Café',
  attraction: 'Attraction',
  nature: 'Nature',
  beach: 'Beach',
  stay: 'Stay',
  nightlife: 'Nightlife',
  shopping: 'Shopping',
  activity: 'Activity',
  other: 'Place',
}

export const priceLabel: Record<string, string> = {
  PRICE_LEVEL_FREE: 'Free',
  PRICE_LEVEL_INEXPENSIVE: 'Inexpensive',
  PRICE_LEVEL_MODERATE: 'Moderate',
  PRICE_LEVEL_EXPENSIVE: 'Expensive',
  PRICE_LEVEL_VERY_EXPENSIVE: 'Very expensive',
}

export const voteOptions: { value: Vote; label: string }[] = [
  { value: 'must', label: 'Must go' },
  { value: 'maybe', label: 'Maybe' },
  { value: 'skip', label: 'Skip' },
]

/** 74 -> "1:14", the moment a place appears in a Reel. */
export function formatSecond(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

/** "Hana", "Hana and Raka", "Hana, Raka and 2 others". */
export function listNames(names: string[]): string {
  if (names.length <= 2) return names.join(' and ')
  const others = names.length - 2
  return `${names.slice(0, 2).join(', ')} and ${others} ${others === 1 ? 'other' : 'others'}`
}

export function savedByNames(place: Place, byId: Map<string, WithId<Member>>): string {
  return listNames(
    place.savedBy.map((uid) => byId.get(uid)?.displayName.split(' ')[0] ?? 'Someone'),
  )
}

/** Most-saved first during voting; most-wanted first once votes are in. */
export function sortPlaces(places: WithId<Place>[], byVotes: boolean): WithId<Place>[] {
  const score = (place: Place) =>
    byVotes ? place.tally.must * 2 + place.tally.maybe : place.savedBy.length
  return [...places].sort(
    (a, b) =>
      score(b) - score(a) || (b.rating ?? 0) - (a.rating ?? 0) || a.name.localeCompare(b.name),
  )
}
