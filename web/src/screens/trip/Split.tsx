import { collection, orderBy, query } from 'firebase/firestore'
import { ref, uploadBytes } from 'firebase/storage'
import { Plus, ScanLine } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { useAuth } from '../../app/auth-context'
import { useSquad, useTrip } from '../../app/trip-context'
import { ErrorText } from '../../components/ErrorText'
import { buttonClass } from '../../components/styles'
import {
  ActionButton,
  BottomSheet,
  PageHeading,
  SectionHeading,
  SurfaceCard,
} from '../../components/ui'
import {
  api,
  errorMessage,
  type ScanResult,
  type ScannedReceipt,
  type SplitPreview,
} from '../../lib/api'
import { db, storage } from '../../lib/firebase'
import { formatIdr } from '../../lib/format'
import { useCollection } from '../../lib/hooks/useCollection'
import { listNames } from '../../lib/places'
import { EXPENSE_EDITABLE } from '../../lib/status'
import type { Expense, WithId } from '../../lib/types'

const SPLIT_STAGES = new Set(['planned', 'splitting', 'settling', 'settled'])
const MAX_RECEIPT_BYTES = 10 * 1024 * 1024

export function Split() {
  const trip = useTrip()
  if (!SPLIT_STAGES.has(trip.status)) {
    return (
      <div className="space-y-2 py-2">
        <PageHeading
          title="Split bill"
          description="Split bill opens once the itinerary is ready."
        />
      </div>
    )
  }
  return <SplitBoard />
}

function useSplitPreview(tripId: string, refreshKey: string) {
  const [preview, setPreview] = useState<SplitPreview | null>(null)
  useEffect(() => {
    let active = true
    api<SplitPreview>(`/v1/trips/${tripId}/split:preview`)
      .then((result) => active && setPreview(result))
      .catch(() => active && setPreview(null))
    return () => {
      active = false
    }
  }, [tripId, refreshKey])
  return preview
}

function SplitBoard() {
  const trip = useTrip()
  const { me, byId } = useSquad()
  const expensesQuery = useMemo(
    () => query(collection(db, 'trips', trip.id, 'expenses'), orderBy('createdAt', 'desc')),
    [trip.id],
  )
  const { data: expenses, loading } = useCollection<Expense>(expensesQuery)
  const refreshKey = [
    trip.status,
    trip.split.version,
    ...expenses.map((e) => `${e.id}:${e.amountIdr}:${e.updatedAt?.seconds ?? ''}`),
  ].join('|')
  const preview = useSplitPreview(trip.id, refreshKey)
  const editable = EXPENSE_EDITABLE.has(trip.status)
  const firstName = (uid: string) => byId.get(uid)?.displayName.split(' ')[0] ?? 'Someone'
  const myBalance = me && preview ? (preview.balances[me.id] ?? 0) : null

  return (
    <div className="space-y-5 pt-2 pb-48">
      <PageHeading
        title="Split bill"
        description="Log what each person paid. Travelin works out the fewest transfers that settle everyone up."
      />

      {preview && myBalance !== null && trip.status !== 'settled' && (
        <SurfaceCard className="border-transparent bg-lagoon/10 p-4 shadow-none">
          <p className="text-lg font-bold tabular-nums">
            {myBalance > 0
              ? `You get back ${formatIdr(myBalance)}`
              : myBalance < 0
                ? `You owe ${formatIdr(-myBalance)}`
                : "You're even"}
          </p>
          {preview.transfers.length > 0 && (
            <ul className="mt-2 space-y-1 text-sm tabular-nums">
              {preview.transfers.map((transfer) => (
                <li key={`${transfer.from}-${transfer.to}`}>
                  {firstName(transfer.from)} pays {firstName(transfer.to)}{' '}
                  <span className="font-semibold">{formatIdr(transfer.amountIdr)}</span>
                </li>
              ))}
            </ul>
          )}
        </SurfaceCard>
      )}

      {editable && (
        <div className="grid grid-cols-2 gap-3">
          <Link to="new" className={`${buttonClass('dark')} w-full`}>
            <Plus size={18} aria-hidden="true" />
            Add expense
          </Link>
          <ScanReceipt />
        </div>
      )}

      <section>
        <SectionHeading title={`Expenses · ${expenses.length}`} />
        {loading ? (
          <div className="h-20 animate-pulse rounded-2xl bg-line/60" />
        ) : expenses.length === 0 ? (
          <p className="text-muted">Nothing logged yet. Add the first expense or scan a receipt.</p>
        ) : (
          <ul className="space-y-2">
            {expenses.map((expense) => (
              <ExpenseRow key={expense.id} expense={expense} editable={editable} />
            ))}
          </ul>
        )}
      </section>

      <SettleBar expenseCount={expenses.length} />
    </div>
  )
}

function ExpenseRow({ expense, editable }: { expense: WithId<Expense>; editable: boolean }) {
  const { byId } = useSquad()
  const people = Object.keys(expense.computedShares).length
  const how =
    expense.source === 'booking'
      ? 'Group booking'
      : expense.split.mode === 'items'
        ? `By item · ${people} people`
        : `Split ${people} ${people === 1 ? 'way' : 'ways'}`
  const content = (
    <>
      <div className="min-w-0 flex-1">
        <p className="truncate font-semibold">{expense.title}</p>
        <p className="text-sm text-muted">
          {byId.get(expense.paidBy)?.displayName.split(' ')[0] ?? 'Someone'} paid · {how}
        </p>
      </div>
      <p className="shrink-0 font-semibold tabular-nums">{formatIdr(expense.amountIdr)}</p>
    </>
  )
  const className = 'flex items-center gap-3 surface-card p-4'
  return (
    <li>
      {editable && expense.source !== 'booking' ? (
        <Link to={expense.id} className={`${className} hover:border-lagoon`}>
          {content}
        </Link>
      ) : (
        <div className={className}>{content}</div>
      )}
    </li>
  )
}

function ScanReceipt() {
  const trip = useTrip()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [stage, setStage] = useState<'idle' | 'uploading' | 'reading'>('idle')
  const [error, setError] = useState<string | null>(null)

  async function scan(file: File | undefined) {
    if (!file || !user) return
    if (!file.type.startsWith('image/')) return setError('Choose a photo of the receipt.')
    if (file.size > MAX_RECEIPT_BYTES) return setError('That photo is over 10 MB.')
    setError(null)
    setStage('uploading')
    try {
      const extension = file.name.split('.').pop()?.toLowerCase() || 'jpg'
      const storagePath = `trips/${trip.id}/receipts/${user.uid}/${Date.now()}.${extension}`
      await uploadBytes(ref(storage, storagePath), file, { contentType: file.type })
      setStage('reading')
      const result = await api<ScanResult>(`/v1/trips/${trip.id}/receipts:scan`, {
        body: { storagePath },
      })
      const receipt: ScannedReceipt = { ...result, storagePath }
      navigate('new', { state: { receipt } })
    } catch (err) {
      setError(errorMessage(err, "Couldn't read that receipt. Please try again."))
      setStage('idle')
    }
  }

  const busy = stage !== 'idle'
  return (
    <div className="space-y-1">
      <label
        htmlFor="receipt-photo"
        aria-disabled={busy}
        className={`${buttonClass('outline')} w-full cursor-pointer ${busy ? 'pointer-events-none opacity-60' : ''}`}
      >
        <ScanLine size={18} aria-hidden="true" />
        {stage === 'uploading' ? 'Uploading…' : stage === 'reading' ? 'Reading…' : 'Scan receipt'}
      </label>
      <input
        id="receipt-photo"
        type="file"
        accept="image/*"
        capture="environment"
        disabled={busy}
        onChange={(event) => scan(event.target.files?.[0])}
        className="sr-only"
      />
      <ErrorText>{error}</ErrorText>
    </div>
  )
}

function SettleBar({ expenseCount }: { expenseCount: number }) {
  const trip = useTrip()
  const { members, me } = useSquad()
  const [busy, setBusy] = useState(false)
  const [confirmingAdjust, setConfirmingAdjust] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const version = trip.split.version
  const waitingFor = members
    .filter((member) => member.splitApprovedVersion !== version)
    .map((member) => member.displayName.split(' ')[0])
  const approved = me?.splitApprovedVersion === version

  async function call(path: string, body?: unknown) {
    setBusy(true)
    setError(null)
    try {
      await api(`/v1/trips/${trip.id}/${path}`, { method: 'POST', body })
      setConfirmingAdjust(false)
    } catch (err) {
      setError(errorMessage(err, 'Something went wrong. Please try again.'))
    } finally {
      setBusy(false)
    }
  }

  const adjust = (
    <>
      <ActionButton
        type="button"
        variant="tertiary"
        onClick={() => setConfirmingAdjust(true)}
        className="min-h-10 w-full"
      >
        Adjust split
      </ActionButton>
      <BottomSheet
        open={confirmingAdjust}
        title="Adjust this split?"
        description="Everyone will need to approve the updated split again."
        onClose={() => setConfirmingAdjust(false)}
      >
        <div className="grid grid-cols-2 gap-3">
          <ActionButton type="button" variant="outline" onClick={() => setConfirmingAdjust(false)}>
            Cancel
          </ActionButton>
          <ActionButton type="button" onClick={() => call('split:adjust')} disabled={busy}>
            {busy ? 'Adjusting…' : 'Adjust split'}
          </ActionButton>
        </div>
      </BottomSheet>
    </>
  )

  let body
  if (trip.status === 'planned') {
    body = (
      <>
        <button
          type="button"
          onClick={() => call('split:open')}
          disabled={busy || expenseCount === 0}
          className={`${buttonClass('primary')} w-full`}
        >
          Settle up
        </button>
        <p className="text-center text-xs text-muted">
          Once you settle up, everyone approves the same split before anyone pays.
        </p>
      </>
    )
  } else if (trip.status === 'splitting') {
    body = (
      <>
        <p className="text-center text-sm tabular-nums">
          {members.length - waitingFor.length} of {members.length} approved
          {approved && waitingFor.length > 0 && ` · waiting for ${listNames(waitingFor)}`}
        </p>
        {!approved && (
          <button
            type="button"
            onClick={() => call('split:approve', { version })}
            disabled={busy}
            className={`${buttonClass('primary')} w-full`}
          >
            Approve this split
          </button>
        )}
        {adjust}
      </>
    )
  } else if (trip.status === 'settling') {
    body = (
      <>
        <Link to="../pay" relative="path" className={`${buttonClass('primary')} w-full`}>
          Go to payments
        </Link>
        {adjust}
      </>
    )
  } else {
    body = <p className="text-center font-semibold">Everyone is settled up.</p>
  }

  return (
    <div className="fixed inset-x-0 bottom-[calc(var(--bottom-nav-height)+env(safe-area-inset-bottom))] z-10 border-t border-line bg-card/95 px-4 pt-3 pb-3 shadow-[0_-6px_24px_rgba(27,27,31,0.06)] backdrop-blur">
      <div className="mx-auto max-w-md space-y-2">
        <ErrorText>{error}</ErrorText>
        {body}
      </div>
    </div>
  )
}
