import { doc } from 'firebase/firestore'
import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { useSquad, useTrip } from '../../app/trip-context'
import { ErrorText } from '../../components/ErrorText'
import { Splash } from '../../components/Splash'
import { buttonClass } from '../../components/styles'
import { PageHeading, StatusBadge } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import { db } from '../../lib/firebase'
import { formatDateTime, formatIdr } from '../../lib/format'
import { useDoc } from '../../lib/hooks/useDoc'
import { listNames } from '../../lib/places'
import type { Booking as BookingDoc } from '../../lib/types'

const statusChip: Record<
  BookingDoc['status'],
  { label: string; tone: 'warm' | 'success' | 'danger' }
> = {
  approving: { label: 'Waiting for approvals', tone: 'warm' },
  paying: { label: 'Paying', tone: 'warm' },
  paid: { label: 'Booked', tone: 'success' },
  failed: { label: "Didn't go through", tone: 'danger' },
}

export function Booking() {
  const trip = useTrip()
  const { members, me, byId } = useSquad()
  const { bookingId } = useParams()
  const { data: booking, loading } = useDoc<BookingDoc>(
    bookingId ? doc(db, 'trips', trip.id, 'bookings', bookingId) : null,
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (loading) return <Splash />
  if (!booking || !bookingId) {
    return <p className="py-10 text-center text-muted">This booking doesn't exist.</p>
  }

  const firstName = (uid: string) => byId.get(uid)?.displayName.split(' ')[0] ?? 'Someone'
  const approved = new Set(
    Object.entries(booking.approvals)
      .filter(([, approval]) => approval.cartHash === booking.cartHash)
      .map(([uid]) => uid),
  )
  const waitingFor = members.filter((member) => !approved.has(member.id))
  const cart = booking.cartMandate.contents
  const chip = statusChip[booking.status]

  async function approve() {
    setBusy(true)
    setError(null)
    try {
      await api(`/v1/trips/${trip.id}/bookings/${bookingId}:approve`, { method: 'POST' })
    } catch (err) {
      setError(errorMessage(err, "Couldn't approve. Please try again."))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5 py-2">
      <div className="space-y-1">
        <PageHeading eyebrow="Group booking" title={booking.title} />
        <StatusBadge tone={chip.tone}>{chip.label}</StatusBadge>
      </div>

      <section className="surface-card p-4">
        <ul className="space-y-1 text-sm">
          {cart.payment_request.details.display_items.map((item) => (
            <li key={item.label} className="flex justify-between gap-3">
              <span>{item.label}</span>
              <span className="tabular-nums">{formatIdr(item.amount.value)}</span>
            </li>
          ))}
        </ul>
        <p className="mt-3 flex justify-between border-t border-line pt-3 font-bold tabular-nums">
          <span>Total</span>
          <span>{formatIdr(booking.amountIdr)}</span>
        </p>
        <p className="mt-2 text-xs text-muted">
          Price signed by {cart.merchant_name}. Offer valid until{' '}
          {formatDateTime(new Date(cart.cart_expiry))}.
        </p>
      </section>

      <section>
        <h2 className="mb-2 font-bold tabular-nums">
          {approved.size} of {members.length} approved
        </h2>
        <ul className="space-y-1">
          {members.map((member) => (
            <li key={member.id} className="flex justify-between text-sm">
              <span>{member.displayName}</span>
              <span
                className={
                  approved.has(member.id) ? 'font-semibold text-lagoon-dark' : 'text-muted'
                }
              >
                {approved.has(member.id) ? 'Approved' : 'Waiting'}
              </span>
            </li>
          ))}
        </ul>
      </section>

      {booking.status === 'approving' && me && !approved.has(me.id) && (
        <section className="space-y-2">
          <ErrorText>{error}</ErrorText>
          <button
            type="button"
            onClick={approve}
            disabled={busy}
            className={`${buttonClass('primary')} w-full`}
          >
            {busy ? 'Approving…' : 'Approve this booking'}
          </button>
          <p className="text-center text-xs text-muted">
            {firstName(booking.payerUid)} pays the merchant once everyone approves, and the cost
            goes into Split bill.
          </p>
        </section>
      )}
      {booking.status === 'approving' && me && approved.has(me.id) && (
        <p className="text-center text-sm text-muted">
          You approved. Waiting for {listNames(waitingFor.map((member) => firstName(member.id)))}.
        </p>
      )}
      {booking.status === 'paying' && (
        <p role="status" className="text-center font-semibold">
          Everyone approved. Paying the merchant…
        </p>
      )}
      {booking.status === 'paid' && booking.receipt && (
        <section className="rounded-2xl bg-lagoon/10 p-4">
          <p className="font-bold text-lagoon-dark">Booked</p>
          <p className="mt-1 text-sm">
            {firstName(booking.payerUid)} paid {formatIdr(booking.receipt.amount_idr)} to{' '}
            {booking.receipt.merchant_name} (order {booking.receipt.order_id}). It's in Split bill,
            shared by everyone.
          </p>
          <Link
            to="../../split"
            relative="path"
            className="mt-2 inline-block text-sm font-semibold text-lagoon"
          >
            Open Split bill
          </Link>
        </section>
      )}
      {booking.status === 'failed' && (
        <section className="rounded-2xl bg-red-50 p-4 text-sm">
          <p className="font-semibold text-red-800">{booking.failureReason}</p>
          <Link
            to="../../itinerary"
            relative="path"
            className="mt-2 inline-block font-semibold text-lagoon"
          >
            Back to the itinerary
          </Link>
        </section>
      )}

      {booking.status === 'approving' && approved.size < booking.guests && (
        <GuardrailCheck
          tripId={trip.id}
          bookingId={bookingId}
          approved={approved.size}
          guests={booking.guests}
        />
      )}

      <section className="space-y-2 text-sm text-muted">
        <h2 className="font-bold text-ink">How the booking stays safe</h2>
        <ol className="list-decimal space-y-1 pl-5">
          <li>The merchant signs the cart (an AP2 Cart Mandate), so the price can't change.</li>
          <li>Every member approves that exact cart.</li>
          <li>
            Only then does Travelin sign one payment for the squad (an AP2 Payment Mandate). The
            merchant checks every approval itself before charging.
          </li>
        </ol>
        <p>In this prototype the merchant and the payment are simulated.</p>
      </section>
    </div>
  )
}

function GuardrailCheck({
  tripId,
  bookingId,
  approved,
  guests,
}: {
  tripId: string
  bookingId: string
  approved: number
  guests: number
}) {
  const [result, setResult] = useState<{ rejected: boolean; reason: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run() {
    setBusy(true)
    setError(null)
    try {
      setResult(
        await api(`/v1/trips/${tripId}/bookings/${bookingId}:test-guardrail`, { method: 'POST' }),
      )
    } catch (err) {
      setError(errorMessage(err, "Couldn't run the check. Please try again."))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="space-y-2 rounded-2xl border border-dashed border-line p-4">
      <h2 className="font-bold">Safety check</h2>
      <p className="text-sm text-muted">
        See what happens if someone tries to pay before everyone has approved.
      </p>
      <button
        type="button"
        onClick={run}
        disabled={busy}
        className={`${buttonClass('outline')} w-full`}
      >
        {busy ? 'Asking the merchant…' : `Try paying with ${approved} of ${guests} approvals`}
      </button>
      <ErrorText>{error}</ErrorText>
      {result && (
        <p
          role="status"
          className={`text-sm font-semibold ${result.rejected ? 'text-lagoon-dark' : 'text-red-800'}`}
        >
          {result.rejected ? `Refused by the merchant: ${result.reason}` : result.reason}
        </p>
      )}
    </section>
  )
}
