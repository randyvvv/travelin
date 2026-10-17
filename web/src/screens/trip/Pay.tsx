import { collection, query } from 'firebase/firestore'
import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { useSquad, useTrip } from '../../app/trip-context'
import { ErrorText } from '../../components/ErrorText'
import { buttonClass } from '../../components/styles'
import { PageHeading, SectionHeading, StatusBadge } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import { db } from '../../lib/firebase'
import { formatIdr } from '../../lib/format'
import { useCollection } from '../../lib/hooks/useCollection'
import type { Transfer, TransferStatus, WithId } from '../../lib/types'

const statusChip: Record<TransferStatus, { label: string; tone: 'danger' | 'warm' | 'success' }> = {
  unpaid: { label: 'Unpaid', tone: 'danger' },
  waiting: { label: 'Waiting', tone: 'warm' },
  confirmed: { label: 'Confirmed', tone: 'success' },
}

export function Pay() {
  const trip = useTrip()
  const { me } = useSquad()
  const transfersQuery = useMemo(
    () => query(collection(db, 'trips', trip.id, 'transfers')),
    [trip.id],
  )
  const { data: transfers, loading } = useCollection<Transfer>(transfersQuery)

  if (trip.status !== 'settling' && trip.status !== 'settled') {
    return (
      <div className="space-y-2 py-2">
        <PageHeading
          title="Payments"
          description={
            <>
              Payments start once everyone approves the split.{' '}
              <Link to="../split" relative="path" className="font-semibold text-lagoon">
                Go to Split bill
              </Link>
            </>
          }
        />
      </div>
    )
  }

  const mine = transfers.filter((t) => t.from === me?.id)
  const incoming = transfers.filter((t) => t.to === me?.id)
  const others = transfers.filter((t) => t.from !== me?.id && t.to !== me?.id)

  return (
    <div className="space-y-6 py-2">
      <PageHeading
        title="Payments"
        description="Travelin never moves money. Each person sends their own transfer by bank or e-wallet, and the person receiving it confirms."
      />

      {trip.status === 'settled' && (
        <p className="rounded-2xl bg-lagoon/10 p-4 font-semibold text-lagoon-dark">
          Everyone is settled up. This trip is now in your history.
        </p>
      )}

      {loading ? (
        <div className="h-24 animate-pulse rounded-2xl bg-line/60" />
      ) : (
        <>
          <TransferList title="You pay" transfers={mine} empty="You don't owe anyone." />
          <TransferList title="You receive" transfers={incoming} empty="Nobody owes you." />
          {others.length > 0 && <TransferList title="Rest of the squad" transfers={others} />}
        </>
      )}
    </div>
  )
}

function TransferList({
  title,
  transfers,
  empty,
}: {
  title: string
  transfers: WithId<Transfer>[]
  empty?: string
}) {
  return (
    <section>
      <SectionHeading title={title} />
      {transfers.length === 0 ? (
        <p className="text-muted">{empty}</p>
      ) : (
        <ul className="space-y-3">
          {transfers.map((transfer) => (
            <TransferCard key={transfer.id} transfer={transfer} />
          ))}
        </ul>
      )}
    </section>
  )
}

function TransferCard({ transfer }: { transfer: WithId<Transfer> }) {
  const trip = useTrip()
  const { me, byId } = useSquad()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const name = (uid: string) => byId.get(uid)?.displayName.split(' ')[0] ?? 'Someone'
  const amount = formatIdr(transfer.amountIdr)
  const isPayer = transfer.from === me?.id
  const isPayee = transfer.to === me?.id
  const chip = statusChip[transfer.status]

  async function advance(action: 'send' | 'confirm') {
    setBusy(true)
    setError(null)
    try {
      await api(`/v1/trips/${trip.id}/transfers/${transfer.id}:${action}`, { method: 'POST' })
    } catch (err) {
      setError(errorMessage(err, "Couldn't update the payment. Please try again."))
    } finally {
      setBusy(false)
    }
  }

  let guidance: string | null = null
  let action: { label: string; run: () => void } | null = null
  if (isPayer && transfer.status === 'unpaid') {
    guidance = `Send ${amount} to ${name(transfer.to)} with your bank or e-wallet, then tap below.`
    action = { label: "I've sent it", run: () => advance('send') }
  } else if (isPayer && transfer.status === 'waiting') {
    guidance = `Waiting for ${name(transfer.to)} to confirm it arrived.`
  } else if (isPayee && transfer.status === 'waiting') {
    guidance = `${name(transfer.from)} says the money is on its way. Check your account first.`
    action = { label: 'Confirm received', run: () => advance('confirm') }
  } else if (isPayee && transfer.status === 'unpaid') {
    guidance = `${name(transfer.from)} hasn't sent it yet.`
  }

  return (
    <li className="space-y-3 surface-card p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="font-semibold">
          {isPayer
            ? `To ${name(transfer.to)}`
            : isPayee
              ? `From ${name(transfer.from)}`
              : `${name(transfer.from)} → ${name(transfer.to)}`}
        </p>
        <StatusBadge tone={chip.tone}>{chip.label}</StatusBadge>
      </div>
      <p className="text-2xl font-extrabold tabular-nums">{amount}</p>
      {guidance && <p className="text-sm text-muted">{guidance}</p>}
      <ErrorText>{error}</ErrorText>
      {action && (
        <button
          type="button"
          onClick={action.run}
          disabled={busy}
          className={`${buttonClass('primary')} w-full`}
        >
          {busy ? 'Saving…' : action.label}
        </button>
      )}
    </li>
  )
}
