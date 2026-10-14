import { doc } from 'firebase/firestore'
import { Link, Outlet, useParams } from 'react-router'
import { Splash } from '../components/Splash'
import { db } from '../lib/firebase'
import { useDoc } from '../lib/hooks/useDoc'
import type { Trip } from '../lib/types'
import type { TripContext } from './trip-context'

export function TripLayout() {
  const { tripId } = useParams()
  const { data: trip, loading, error } = useDoc<Trip>(tripId ? doc(db, 'trips', tripId) : null)

  if (loading) return <Splash />
  if (error || !trip) {
    return (
      <section className="py-12 text-center">
        <h1 className="text-xl font-bold">Trip not available</h1>
        <p className="mt-2 text-muted">It doesn't exist, or you're not in this trip's squad.</p>
        <Link to="/" className="mt-6 inline-block font-semibold text-lagoon">
          Back to home
        </Link>
      </section>
    )
  }

  return (
    <>
      <Link to={`/trips/${trip.id}`} className="text-sm font-semibold text-lagoon">
        {trip.name}
      </Link>
      <Outlet context={{ trip } satisfies TripContext} />
    </>
  )
}
