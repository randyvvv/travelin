import { collection, limit, orderBy, query } from 'firebase/firestore'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { useTrip } from '../../app/trip-context'
import { ErrorText } from '../../components/ErrorText'
import { buttonClass } from '../../components/styles'
import { api, errorMessage } from '../../lib/api'
import { db } from '../../lib/firebase'
import { formatIdr } from '../../lib/format'
import { useCollection } from '../../lib/hooks/useCollection'
import type { Booking, Plan } from '../../lib/types'

/** The planner's suggested stay or tour, and the squad's booking of it. */
export function StayCard({ stay }: { stay: NonNullable<Plan['stay']> }) {
  const trip = useTrip()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const latestQuery = useMemo(
    () =>
      query(collection(db, 'trips', trip.id, 'bookings'), orderBy('createdAt', 'desc'), limit(1)),
    [trip.id],
  )
  const { data: bookings } = useCollection<Booking>(latestQuery)
  const latest = bookings[0]
  const active = latest && latest.status !== 'failed' ? latest : null

  async function propose() {
    setBusy(true)
    setError(null)
    try {
      const { bookingId } = await api<{ bookingId: string }>(`/v1/trips/${trip.id}/bookings`, {
        method: 'POST',
      })
      navigate(`/trips/${trip.id}/booking/${bookingId}`)
    } catch (err) {
      setError(errorMessage(err, "Couldn't start the booking. Please try again."))
      setBusy(false)
    }
  }

  return (
    <section className="space-y-3 surface-card p-4">
      <div>
        <p className="text-sm font-semibold text-lagoon">
          Suggested {stay.type === 'stay' ? 'stay' : 'tour'}
        </p>
        <h2 className="font-bold">{stay.title}</h2>
        <p className="text-sm text-muted tabular-nums">
          {formatIdr(stay.priceIdr)} per {stay.unit}
        </p>
        <p className="mt-2 text-sm">{stay.reason}</p>
      </div>

      {active ? (
        <Link
          to={`../booking/${active.id}`}
          relative="path"
          className={`${buttonClass('outline')} w-full`}
        >
          {active.status === 'paid' ? 'Booked. View booking' : 'View the group booking'}
        </Link>
      ) : (
        trip.status === 'planned' && (
          <>
            {latest?.status === 'failed' && (
              <p className="text-sm text-red-800">Last attempt failed: {latest.failureReason}</p>
            )}
            <ErrorText>{error}</ErrorText>
            <button
              type="button"
              onClick={propose}
              disabled={busy}
              className={`${buttonClass('primary')} w-full`}
            >
              {busy ? 'Getting a price…' : 'Book it with the squad'}
            </button>
            <p className="text-center text-xs text-muted">
              Nothing is paid until everyone approves.
            </p>
          </>
        )
      )}
    </section>
  )
}
