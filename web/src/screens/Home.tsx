import { collection, orderBy, query, where } from 'firebase/firestore'
import { useMemo } from 'react'
import { Link } from 'react-router'
import { useAuth } from '../app/auth-context'
import { ChevronRightIcon } from '../components/icons'
import { db } from '../lib/firebase'
import { formatDateRange } from '../lib/format'
import { useCollection } from '../lib/hooks/useCollection'
import { tripStatusLabel } from '../lib/status'
import type { Trip, WithId } from '../lib/types'

export function Home() {
  const { user } = useAuth()
  const tripsQuery = useMemo(
    () =>
      user
        ? query(
            collection(db, 'trips'),
            where('memberUids', 'array-contains', user.uid),
            orderBy('createdAt', 'desc'),
          )
        : null,
    [user],
  )
  const { data: trips, loading } = useCollection<Trip>(tripsQuery)
  const ongoing = trips.filter((trip) => trip.status !== 'settled')
  const history = trips.filter((trip) => trip.status === 'settled')

  return (
    <div className="space-y-8 py-2">
      <section>
        <p className="text-muted">Hi {user?.displayName?.split(' ')[0] ?? 'there'},</p>
        <h1 className="text-2xl font-extrabold tracking-tight">Where's the squad going next?</h1>
        <Link
          to="/trips/new"
          className="mt-5 flex h-12 items-center justify-center rounded-full bg-lagoon font-semibold text-white transition hover:bg-lagoon-dark"
        >
          Create a trip
        </Link>
      </section>

      <TripList title="Ongoing" trips={ongoing} loading={loading} empty="No trips yet." />
      {history.length > 0 && <TripList title="History" trips={history} loading={false} />}
    </div>
  )
}

function TripList({
  title,
  trips,
  loading,
  empty,
}: {
  title: string
  trips: WithId<Trip>[]
  loading: boolean
  empty?: string
}) {
  return (
    <section>
      <h2 className="mb-3 text-sm font-bold tracking-wide text-muted uppercase">{title}</h2>
      {loading ? (
        <div className="h-20 animate-pulse rounded-2xl bg-line/60" />
      ) : trips.length === 0 ? (
        <p className="text-muted">{empty}</p>
      ) : (
        <ul className="space-y-3">
          {trips.map((trip) => (
            <li key={trip.id}>
              <Link
                to={`/trips/${trip.id}`}
                className="flex items-center gap-3 rounded-2xl border border-line bg-card p-4 transition hover:border-lagoon"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate font-bold">{trip.name}</p>
                  <p className="truncate text-sm text-muted">
                    {trip.destination.name} · {formatDateRange(trip.startDate, trip.endDate)}
                  </p>
                </div>
                <span className="shrink-0 rounded-full bg-paper px-2.5 py-1 text-xs font-semibold">
                  {tripStatusLabel[trip.status]}
                </span>
                <ChevronRightIcon className="shrink-0 text-muted" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
