import { Link } from 'react-router'
import { TripList } from '../components/TripList'
import { buttonClass } from '../components/styles'
import { useTrips } from '../lib/hooks/useTrips'

export function PlannedTrips() {
  const { trips, loading, error, uid } = useTrips()
  const unfinished = trips.filter((trip) => trip.status !== 'settled')

  return (
    <div className="space-y-6 py-2">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Planned trips</h1>
        <p className="mt-1 text-muted">Trips still in progress or ready for your itinerary.</p>
        <Link to="/trips/new" className={`${buttonClass('primary')} mt-4 w-full`}>
          Create a trip
        </Link>
      </header>
      <TripList
        title="Trips"
        trips={unfinished}
        uid={uid}
        loading={loading}
        error={error ? tripLoadError(error.code) : null}
        empty="No planned trips yet. Create a trip or join one with an invite link."
      />
    </div>
  )
}

export function TripHistory() {
  const { trips, loading, error, uid } = useTrips()
  const settled = trips.filter((trip) => trip.status === 'settled')

  return (
    <div className="space-y-6 py-2">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Trip history</h1>
        <p className="mt-1 text-muted">Trips where everyone has settled up.</p>
      </header>
      <TripList
        title="History"
        trips={settled}
        uid={uid}
        loading={loading}
        error={error ? tripLoadError(error.code) : null}
        empty="Settled trips will appear here."
      />
    </div>
  )
}

function tripLoadError(code: string | undefined): string {
  if (code === 'permission-denied') {
    return 'Trip access was denied. Check that you are signed in and a member of the trip.'
  }
  return 'Trips could not be loaded. Check your connection and try again.'
}
