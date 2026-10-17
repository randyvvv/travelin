import assert from 'node:assert/strict'
import test from 'node:test'
import {
  deriveHomeTasks,
  destinationFromAddress,
  destinationFromSearch,
  selectDashboardPlaces,
  selectNextTrip,
  topHomeTasks,
} from '../src/lib/homeDashboard.ts'
import type { Member, Place, Transfer, Trip, WithId } from '../src/lib/types'

function trip(
  id: string,
  status: Trip['status'],
  startDate = '2026-10-20',
  endDate = '2026-10-23',
): WithId<Trip> {
  return {
    id,
    name: `Trip ${id}`,
    destination: { name: `Destination ${id}`, lat: null, lng: null },
    origin: 'Bandung',
    startDate,
    endDate,
    hostUid: 'member-1',
    memberUids: ['member-1', 'member-2'],
    inviteCode: 'ABCD2345',
    status,
    votingDeadline: null,
    split: { version: 2 },
    isDemo: false,
    createdAt: { toMillis: () => 0 } as Trip['createdAt'],
  }
}

function member(overrides: Partial<Member> = {}): WithId<Member> {
  return {
    id: 'member-1',
    displayName: 'Hana',
    photoURL: '',
    role: 'host',
    isBot: false,
    prefs: { budgetIdr: 0, interests: [], dietary: [], skip: [] },
    prefsDone: true,
    votes: {},
    votesSubmittedAt: null,
    splitApprovedVersion: null,
    joinedAt: { toMillis: () => 0 } as Member['joinedAt'],
    ...overrides,
  }
}

test('selects a trip underway, else the soonest upcoming unsettled trip', () => {
  const selected = selectNextTrip(
    [
      trip('later', 'planned', '2026-11-20'),
      trip('past', 'planned', '2026-10-12', '2026-10-16'),
      trip('underway', 'planned', '2026-10-16', '2026-10-22'),
      trip('settled', 'settled', '2026-10-17', '2026-10-21'),
    ],
    '2026-10-17',
  )
  assert.equal(selected?.id, 'underway')
  assert.equal(selectNextTrip([trip('settled', 'settled')], '2026-10-17'), null)
  assert.equal(selectNextTrip([], '2026-10-17'), null)
  assert.equal(
    selectNextTrip(
      [trip('later', 'planned', '2026-11-20'), trip('soon', 'planned', '2026-10-21')],
      '2026-10-17',
    )?.id,
    'soon',
  )
  assert.equal(
    selectNextTrip([trip('past', 'planned', '2026-10-12', '2026-10-15')], '2026-10-17'),
    null,
  )
})

test('creates payment, split, voting, and preference actions only while unfinished', () => {
  const trips = [
    trip('pay', 'settling'),
    trip('split', 'splitting'),
    trip('vote', 'voting'),
    trip('prefs', 'gathering'),
    trip('done', 'settled'),
  ]
  const actions = deriveHomeTasks(
    trips,
    {
      pay: member(),
      split: member({ splitApprovedVersion: 1 }),
      vote: member({ votesSubmittedAt: null }),
      prefs: member({ prefsDone: false }),
      done: member({ prefsDone: false }),
    },
    {
      pay: [
        { id: 'send', from: 'member-1', to: 'member-2', status: 'unpaid' } as WithId<Transfer>,
        { id: 'other', from: 'member-2', to: 'member-1', status: 'unpaid' } as WithId<Transfer>,
      ],
    },
    'member-1',
  )
  assert.deepEqual(
    actions.map((action) => action.kind),
    ['payment', 'split', 'vote', 'preferences'],
  )
  assert.deepEqual(
    actions.map((action) => action.to),
    ['/trips/pay/pay', '/trips/split/split', '/trips/vote/places', '/trips/prefs/prefs'],
  )
})

test('orders actions by payment, split, earliest vote deadline, then preferences', () => {
  const earlyVote = trip('vote-early', 'voting')
  earlyVote.votingDeadline = { toMillis: () => 100 } as NonNullable<Trip['votingDeadline']>
  const lateVote = trip('vote-late', 'voting')
  lateVote.votingDeadline = { toMillis: () => 200 } as NonNullable<Trip['votingDeadline']>
  const trips = [
    trip('prefs', 'gathering'),
    lateVote,
    trip('split', 'splitting'),
    trip('pay', 'settling'),
    earlyVote,
  ]
  const members = Object.fromEntries(trips.map((item) => [item.id, member({ prefsDone: false })]))
  const transfers = {
    pay: [
      { id: 'transfer', from: 'member-1', to: 'member-2', status: 'unpaid' } as WithId<Transfer>,
    ],
  }
  const actions = deriveHomeTasks(trips, members, transfers, 'member-1')
  assert.deepEqual(
    actions.slice(0, 3).map((action) => action.kind),
    ['payment', 'split', 'vote'],
  )
  assert.equal(actions[2].tripId, 'vote-early')
  assert.equal(actions.slice(0, 3).length, 3)
  assert.deepEqual(
    actions.slice(3).map((action) => action.kind),
    ['vote', 'preferences'],
  )
  assert.equal(topHomeTasks(actions).length, 3)
  assert.deepEqual(
    topHomeTasks(actions).map((action) => action.kind),
    ['payment', 'split', 'vote'],
  )
})

test('shows payment work for both an unpaid outgoing transfer and a waiting incoming transfer', () => {
  const actions = deriveHomeTasks(
    [trip('send', 'settling'), trip('confirm', 'settling')],
    { send: member(), confirm: member() },
    {
      send: [
        { id: 'outgoing', from: 'member-1', to: 'member-2', status: 'unpaid' } as WithId<Transfer>,
      ],
      confirm: [
        { id: 'incoming', from: 'member-2', to: 'member-1', status: 'waiting' } as WithId<Transfer>,
      ],
    },
    'member-1',
  )

  assert.deepEqual(
    actions.map((action) => action.tripId),
    ['confirm', 'send'],
  )
  assert.ok(actions.every((action) => action.kind === 'payment'))
})

test('omits completed payment, split, vote, and preference work and settles to an empty state', () => {
  const trips = [
    trip('pay', 'settling'),
    trip('split', 'splitting'),
    trip('vote', 'voting'),
    trip('prefs', 'gathering'),
  ]
  const actions = deriveHomeTasks(
    trips,
    {
      pay: member(),
      split: member({ splitApprovedVersion: 2 }),
      vote: member({
        votesSubmittedAt: { toMillis: () => 1 } as NonNullable<Member['votesSubmittedAt']>,
      }),
      prefs: member({ prefsDone: true }),
    },
    {
      pay: [
        { id: 'paid', from: 'member-1', to: 'member-2', status: 'confirmed' } as WithId<Transfer>,
        {
          id: 'received',
          from: 'member-2',
          to: 'member-1',
          status: 'confirmed',
        } as WithId<Transfer>,
      ],
    },
    'member-1',
  )
  assert.deepEqual(actions, [])
  assert.deepEqual(deriveHomeTasks([], {}, {}, 'member-1'), [])
})

test('puts AI ideas first while collecting, then ranks squad votes and saves', () => {
  const places = [
    place('saved', 'Saved place', { must: 0, maybe: 0, skip: 0 }, ['member-1']),
    place('suggested', 'AI pick', { must: 0, maybe: 0, skip: 0 }, [], true),
    place('votes', 'Squad favorite', { must: 2, maybe: 1, skip: 0 }, []),
    place('second', 'Second pick', { must: 1, maybe: 0, skip: 0 }, ['member-1']),
  ]
  assert.deepEqual(
    selectDashboardPlaces(places, 'gathering').map((item) => item.id),
    ['suggested', 'votes', 'second'],
  )
  assert.deepEqual(
    selectDashboardPlaces(places, 'voting').map((item) => item.id),
    ['votes', 'second', 'saved'],
  )
})

test('reads an encoded curated destination from the trip form query string', () => {
  assert.equal(destinationFromSearch('destination=Ho+Chi+Minh+City'), 'Ho Chi Minh City')
  assert.equal(destinationFromSearch('destination=%20Bali%20'), 'Bali')
  assert.equal(destinationFromSearch(''), '')
})

test('prefills a new plan with the area in a popular place address', () => {
  assert.equal(
    destinationFromAddress(
      'Taman Mini Indonesia Indah, East Jakarta, Jakarta, Indonesia',
      'Taman Mini',
    ),
    'Jakarta',
  )
  assert.equal(destinationFromAddress('Bali, Indonesia'), 'Bali')
  assert.equal(
    destinationFromAddress('', 'Taman Mini Indonesia Indah'),
    'Taman Mini Indonesia Indah',
  )
})

function place(
  id: string,
  name: string,
  tally: Place['tally'],
  savedBy: string[],
  suggestion = false,
): WithId<Place> {
  return {
    id,
    name,
    category: 'attraction',
    address: '',
    location: { lat: 0, lng: 0 },
    googleMapsUri: '',
    mentions: [],
    savedBy,
    summary: {
      highlights: [],
      bestTime: '',
      priceNote: '',
      dietaryNote: '',
      crowdNote: '',
    },
    mapsSources: [],
    tally,
    suggestion: suggestion ? { reason: 'A squad idea' } : null,
  }
}
