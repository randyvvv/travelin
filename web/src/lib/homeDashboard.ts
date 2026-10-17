import type { Member, Place, Transfer, Trip, WithId } from './types'

export interface HomeTask {
  kind: 'payment' | 'split' | 'vote' | 'preferences'
  tripId: string
  destination: string
  title: string
  detail: string
  to: string
  priority: number
  dueAt: number
  deadline: number | null
}

export function topHomeTasks(tasks: HomeTask[]): HomeTask[] {
  return tasks.slice(0, 3)
}

/** Use the viewer's local calendar date so trip boundaries stay intuitive. */
export function localIsoDate(date = new Date()): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/** Current trip first, otherwise the closest future trip that is not settled. */
export function selectNextTrip(trips: WithId<Trip>[], today = localIsoDate()): WithId<Trip> | null {
  const active = trips.filter((trip) => trip.status !== 'settled')
  const underway = active
    .filter((trip) => trip.startDate <= today && trip.endDate >= today)
    .sort((a, b) => a.endDate.localeCompare(b.endDate) || a.startDate.localeCompare(b.startDate))
  if (underway.length > 0) return underway[0]

  return (
    active
      .filter((trip) => trip.startDate > today)
      .sort((a, b) => a.startDate.localeCompare(b.startDate))[0] ?? null
  )
}

/** At most one clear next action per trip, with payment work at the top. */
export function deriveHomeTasks(
  trips: WithId<Trip>[],
  members: Record<string, WithId<Member> | null | undefined>,
  transfers: Record<string, WithId<Transfer>[] | undefined>,
  uid: string,
): HomeTask[] {
  const tasks: HomeTask[] = []
  for (const trip of trips) {
    if (trip.status === 'settled') continue
    const member = members[trip.id]
    if (!member) continue

    if (
      trip.status === 'settling' &&
      (transfers[trip.id] ?? []).some(
        (transfer) =>
          (transfer.from === uid && transfer.status === 'unpaid') ||
          (transfer.to === uid && transfer.status === 'waiting'),
      )
    ) {
      tasks.push({
        kind: 'payment',
        tripId: trip.id,
        destination: trip.destination.name,
        title: 'Finish trip payments',
        detail: 'Send or confirm a squad payment',
        to: `/trips/${trip.id}/pay`,
        priority: 0,
        dueAt: 0,
        deadline: null,
      })
    }

    if (trip.status === 'splitting' && member.splitApprovedVersion !== trip.split.version) {
      tasks.push({
        kind: 'split',
        tripId: trip.id,
        destination: trip.destination.name,
        title: 'Review the trip split',
        detail: `Approve expenses for ${trip.destination.name}`,
        to: `/trips/${trip.id}/split`,
        priority: 1,
        dueAt: 0,
        deadline: null,
      })
    }

    if (trip.status === 'voting' && member.votesSubmittedAt == null) {
      tasks.push({
        kind: 'vote',
        tripId: trip.id,
        destination: trip.destination.name,
        title: 'Vote on places',
        detail: `Choose places in ${trip.destination.name}`,
        to: `/trips/${trip.id}/places`,
        priority: 2,
        dueAt: trip.votingDeadline?.toMillis() ?? Number.MAX_SAFE_INTEGER,
        deadline: trip.votingDeadline?.toMillis() ?? null,
      })
    }

    if ((trip.status === 'gathering' || trip.status === 'extracting') && !member.prefsDone) {
      tasks.push({
        kind: 'preferences',
        tripId: trip.id,
        destination: trip.destination.name,
        title: 'Set your preferences',
        detail: `Add budget and interests for ${trip.destination.name}`,
        to: `/trips/${trip.id}/prefs`,
        priority: 3,
        dueAt: 0,
        deadline: null,
      })
    }
  }

  return tasks.sort(
    (a, b) =>
      a.priority - b.priority ||
      (a.priority === 2 ? a.dueAt - b.dueAt : 0) ||
      a.destination.localeCompare(b.destination),
  )
}

/** Curating uses AI suggestions first; later trip stages surface the strongest ideas. */
export function selectDashboardPlaces(
  places: WithId<Place>[],
  status: Trip['status'],
): WithId<Place>[] {
  const sorted = [...places].sort((a, b) => {
    if (status === 'gathering') {
      const suggested = Number(Boolean(b.suggestion)) - Number(Boolean(a.suggestion))
      if (suggested !== 0) return suggested
    }
    const aScore = a.tally.must * 3 + a.tally.maybe * 2 + a.savedBy.length
    const bScore = b.tally.must * 3 + b.tally.maybe * 2 + b.savedBy.length
    return bScore - aScore || a.name.localeCompare(b.name)
  })
  return sorted.slice(0, 3)
}

export function destinationFromSearch(search: string): string {
  return new URLSearchParams(search).get('destination')?.trim() ?? ''
}

/** Prefer the locality in a formatted Google address, then fall back to its first part. */
export function destinationFromAddress(address: string, fallback = ''): string {
  const parts = address
    .split(',')
    .map((part) =>
      part
        .trim()
        .replace(/\b\d{5,6}\b/g, '')
        .trim(),
    )
    .filter(Boolean)
  if (parts.length > 1) {
    const area = parts.at(-2)
    if (area && !/^(Indonesia|Vietnam|Thailand|Singapore|Malaysia)$/i.test(area)) return area
  }
  return parts[0] || fallback
}
