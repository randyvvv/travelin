import { Link } from 'react-router'
import { useAuth } from '../app/auth-context'
import { TripList } from '../components/TripList'
import { buttonClass } from '../components/styles'
import { useTrips } from '../lib/hooks/useTrips'

export function Home() {
  const { user } = useAuth()
  const { trips, loading, error, uid } = useTrips()
  const ongoing = trips.filter((trip) => trip.status !== 'settled')
  const history = trips.filter((trip) => trip.status === 'settled')

  return (
    <div className="space-y-8 py-2">
      <section>
        <p className="text-muted">Hi {user?.displayName?.split(' ')[0] ?? 'there'},</p>
        <h1 className="text-2xl font-extrabold tracking-tight">Where's the squad going next?</h1>
        <Link to="/trips/new" className={`${buttonClass('primary')} mt-5 w-full`}>
          Create a trip
        </Link>
      </section>

      <TripList
        title="Ongoing"
        trips={ongoing}
        uid={uid}
        loading={loading}
        error={error ? tripLoadError(error.code) : null}
        empty="No trips yet."
      />
      {history.length > 0 && (
        <TripList
          title="History"
          trips={history}
          uid={uid}
          loading={false}
          error={error ? tripLoadError(error.code) : null}
        />
      )}
      <p className="text-center text-sm text-muted">
        <Link to="/trips" className="font-semibold text-lagoon">
          View all planned trips
        </Link>
        {history.length > 0 && (
          <>
            {' · '}
            <Link to="/trips/history" className="font-semibold text-lagoon">
              Full history
            </Link>
          </>
        )}
      </p>
    </div>
  )
}

function tripLoadError(code: string | undefined): string {
  if (code === 'permission-denied') {
    return 'Trip access was denied. Check that you are signed in and a member of the trip.'
  }
  return 'Trips could not be loaded. Check your connection and try again.'
}
