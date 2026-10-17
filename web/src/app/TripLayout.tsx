import { collection, doc, orderBy, query } from 'firebase/firestore'
import { ArrowLeft } from 'lucide-react'
import { useMemo } from 'react'
import { Link, Outlet, useParams } from 'react-router'
import { Splash } from '../components/Splash'
import { IconLink } from '../components/ui'
import { db } from '../lib/firebase'
import { useCollection } from '../lib/hooks/useCollection'
import { useDoc } from '../lib/hooks/useDoc'
import type { Member, Trip } from '../lib/types'
import type { TripContext } from './trip-context'

export function TripLayout() {
  const { tripId } = useParams()
  const { data: trip, loading, error } = useDoc<Trip>(tripId ? doc(db, 'trips', tripId) : null)
  const membersQuery = useMemo(
    () =>
      tripId && trip
        ? query(collection(db, 'trips', tripId, 'members'), orderBy('joinedAt'))
        : null,
    // Subscribe once the trip is readable, i.e. once we know the user is a member.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tripId, Boolean(trip)],
  )
  const { data: members } = useCollection<Member>(membersQuery)

  if (loading) return <Splash />
  if (error || !trip) {
    return (
      <section className="py-12 text-center">
        <h1 className="page-title page-title--compact">Trip not available</h1>
        <p className="mt-2 text-muted">It doesn't exist, or you're not in this trip's squad.</p>
        <Link to="/" className="mt-6 inline-block font-semibold text-lagoon">
          Back to home
        </Link>
      </section>
    )
  }

  return (
    <>
      <header className="mb-3 flex min-h-12 items-center gap-2 border-b border-line/70 pb-2">
        <IconLink to="/trips" label="Back to planned trips" className="-ml-2">
          <ArrowLeft size={21} strokeWidth={1.9} aria-hidden="true" />
        </IconLink>
        <Link
          to={`/trips/${trip.id}`}
          className="min-w-0 flex-1 truncate text-sm font-semibold text-ink"
        >
          {trip.name}
        </Link>
      </header>
      <Outlet context={{ trip, members } satisfies TripContext} />
    </>
  )
}
