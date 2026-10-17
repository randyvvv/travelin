import { Link } from 'react-router'
import { Plus } from 'lucide-react'
import { useAuth } from '../app/auth-context'
import { TripList } from '../components/TripList'
import { ActionLink, PageHeading } from '../components/ui'
import { useTrips } from '../lib/hooks/useTrips'

export function Home() {
  const { user } = useAuth()
  const { trips, loading, error, uid } = useTrips()
  const ongoing = trips.filter((trip) => trip.status !== 'settled')
  const history = trips.filter((trip) => trip.status === 'settled')

  return (
    <div className="space-y-8 py-2">
      <section>
        <PageHeading
          eyebrow={`Hi ${user?.displayName?.split(' ')[0] ?? 'there'}`}
          title="Where's the squad going next?"
        />
        <ActionLink to="/trips/new" className="mt-5 w-full">
          <Plus size={19} strokeWidth={2.1} aria-hidden="true" />
          Create a trip
        </ActionLink>
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
