import { ErrorText } from './ErrorText'
import { ChevronRight } from 'lucide-react'
import { ListRow, SectionHeading, StatusBadge } from './ui'
import { formatDateRange } from '../lib/format'
import { paymentLabel, tripStatusLabel } from '../lib/status'
import type { Trip, WithId } from '../lib/types'
import type { ReactNode } from 'react'

export function TripList({
  title,
  trips,
  uid,
  loading,
  error,
  empty,
  action,
}: {
  title: string
  trips: WithId<Trip>[]
  uid: string | undefined
  loading: boolean
  error?: string | null
  empty?: string
  action?: ReactNode
}) {
  const tripStatus = (trip: WithId<Trip>) =>
    (uid && trip.paymentStatus?.[uid] && paymentLabel[trip.paymentStatus[uid]]) ||
    tripStatusLabel[trip.status]

  return (
    <section>
      <SectionHeading title={title} action={action} />
      {loading ? (
        <div className="h-20 animate-pulse rounded-2xl bg-line/60" aria-hidden="true" />
      ) : error ? (
        <ErrorText>{error}</ErrorText>
      ) : trips.length === 0 ? (
        <p className="text-muted">{empty ?? 'No trips here yet.'}</p>
      ) : (
        <ul className="list-surface divide-y divide-line">
          {trips.map((trip) => (
            <li key={trip.id}>
              <ListRow
                to={`/trips/${trip.id}`}
                title={trip.name}
                subtitle={`${trip.destination.name} · ${formatDateRange(trip.startDate, trip.endDate)}`}
                trailing={
                  <span className="flex shrink-0 items-center gap-2">
                    <StatusBadge tone={trip.status === 'settled' ? 'success' : 'neutral'}>
                      {tripStatus(trip)}
                    </StatusBadge>
                    <ChevronRight size={19} className="text-muted" aria-hidden="true" />
                  </span>
                }
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
