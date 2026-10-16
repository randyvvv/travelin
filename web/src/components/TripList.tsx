import { Link } from 'react-router'
import { ErrorText } from './ErrorText'
import { ChevronRightIcon } from './icons'
import { formatDateRange } from '../lib/format'
import { paymentLabel, tripStatusLabel } from '../lib/status'
import type { Trip, WithId } from '../lib/types'

export function TripList({
  title,
  trips,
  uid,
  loading,
  error,
  empty,
}: {
  title: string
  trips: WithId<Trip>[]
  uid: string | undefined
  loading: boolean
  error?: string | null
  empty?: string
}) {
  return (
    <section>
      <h2 className="mb-3 text-sm font-bold tracking-wide text-muted uppercase">{title}</h2>
      {loading ? (
        <div className="h-20 animate-pulse rounded-2xl bg-line/60" />
      ) : error ? (
        <ErrorText>{error}</ErrorText>
      ) : trips.length === 0 ? (
        <p className="text-muted">{empty ?? 'No trips here yet.'}</p>
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
                  {(uid && trip.paymentStatus?.[uid] && paymentLabel[trip.paymentStatus[uid]]) ||
                    tripStatusLabel[trip.status]}
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
