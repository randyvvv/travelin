import { doc } from 'firebase/firestore'
import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router'
import { useSquad, useTrip } from '../../app/trip-context'
import { ErrorText } from '../../components/ErrorText'
import { Field } from '../../components/Field'
import { Splash } from '../../components/Splash'
import { buttonClass, chipClass, inputClass } from '../../components/styles'
import { PageHeading } from '../../components/ui'
import { api, errorMessage, type ScannedReceipt } from '../../lib/api'
import { db } from '../../lib/firebase'
import { formatIdr } from '../../lib/format'
import { useDoc } from '../../lib/hooks/useDoc'
import { computeShares, SplitError, type SplitInput } from '../../lib/split'
import { EXPENSE_EDITABLE } from '../../lib/status'
import type { Expense, ExpenseItem, Member, SplitMode, WithId } from '../../lib/types'

interface FormState {
  title: string
  amount: string
  paidBy: string
  mode: SplitMode
  participants: string[]
  shares: Record<string, number>
  exact: Record<string, string>
  items: ExpenseItem[]
  tax: string
  service: string
  discount: string
  receiptPath: string | null
}

const modes: { value: SplitMode; label: string }[] = [
  { value: 'equal', label: 'Equally' },
  { value: 'shares', label: 'By shares' },
  { value: 'exact', label: 'Exact' },
  { value: 'items', label: 'By item' },
]

const digits = (value: string) => value.replace(/\D/g, '')
const toNumber = (value: string) => Number(value || 0)
const firstName = (member: Member) => member.displayName.split(' ')[0]

function initialState(
  members: WithId<Member>[],
  myId: string,
  expense: Expense | null,
  receipt: ScannedReceipt | undefined,
): FormState {
  const everyone = members.map((member) => member.id)
  const base: FormState = {
    title: '',
    amount: '',
    paidBy: myId,
    mode: 'equal',
    participants: everyone,
    shares: Object.fromEntries(everyone.map((uid) => [uid, 1])),
    exact: {},
    items: [],
    tax: '',
    service: '',
    discount: '',
    receiptPath: null,
  }
  if (expense) {
    return {
      ...base,
      title: expense.title,
      amount: String(expense.amountIdr),
      paidBy: expense.paidBy,
      mode: expense.split.mode,
      participants: expense.split.participants,
      shares: { ...base.shares, ...(expense.split.shares ?? {}) },
      exact: Object.fromEntries(
        Object.entries(expense.split.exact ?? {}).map(([uid, value]) => [uid, String(value)]),
      ),
      items: expense.items,
      tax: expense.taxIdr ? String(expense.taxIdr) : '',
      service: expense.serviceIdr ? String(expense.serviceIdr) : '',
      discount: expense.discountIdr ? String(expense.discountIdr) : '',
      receiptPath: expense.receiptPath,
    }
  }
  if (receipt) {
    return {
      ...base,
      title: receipt.merchant || 'Receipt',
      mode: 'items',
      items: receipt.items.map((item) => ({ ...item, portions: {} })),
      tax: receipt.taxIdr ? String(receipt.taxIdr) : '',
      service: receipt.serviceIdr ? String(receipt.serviceIdr) : '',
      discount: receipt.discountIdr ? String(receipt.discountIdr) : '',
      receiptPath: receipt.storagePath,
    }
  }
  return base
}

function splitInput(state: FormState, memberIds: string[]): SplitInput {
  const exact = Object.fromEntries(
    Object.entries(state.exact).map(([uid, value]) => [uid, toNumber(value)]),
  )
  const participants =
    state.mode === 'equal'
      ? state.participants
      : state.mode === 'shares'
        ? memberIds.filter((uid) => (state.shares[uid] ?? 0) > 0)
        : state.mode === 'exact'
          ? memberIds.filter((uid) => (exact[uid] ?? 0) > 0)
          : []
  return {
    mode: state.mode,
    amount: toNumber(state.amount),
    participants,
    shares: state.shares,
    exact,
    items: state.items,
    tax: toNumber(state.tax),
    service: toNumber(state.service),
    discount: toNumber(state.discount),
  }
}

export function ExpenseEditor() {
  const trip = useTrip()
  const { members, me } = useSquad()
  const { expenseId = 'new' } = useParams()
  const location = useLocation()
  const isNew = expenseId === 'new'
  const { data: expense, loading } = useDoc<Expense>(
    isNew ? null : doc(db, 'trips', trip.id, 'expenses', expenseId),
  )
  const receipt = (location.state as { receipt?: ScannedReceipt } | null)?.receipt

  if (!me || members.length === 0 || (!isNew && loading)) return <Splash />
  if (!isNew && !expense) {
    return (
      <p className="py-10 text-center text-muted">
        This expense no longer exists.{' '}
        <Link to=".." relative="path" className="font-semibold text-lagoon">
          Back to Split bill
        </Link>
      </p>
    )
  }
  if (!EXPENSE_EDITABLE.has(trip.status) || expense?.source === 'booking') {
    return (
      <p className="py-10 text-center text-muted">
        This expense can't be changed right now.{' '}
        <Link to=".." relative="path" className="font-semibold text-lagoon">
          Back to Split bill
        </Link>
      </p>
    )
  }

  return (
    <ExpenseForm
      key={expenseId}
      tripId={trip.id}
      expenseId={isNew ? null : expenseId}
      members={members}
      initial={initialState(members, me.id, expense, receipt)}
      warnings={receipt?.warnings ?? []}
    />
  )
}

function ExpenseForm({
  tripId,
  expenseId,
  members,
  initial,
  warnings,
}: {
  tripId: string
  expenseId: string | null
  members: WithId<Member>[]
  initial: FormState
  warnings: string[]
}) {
  const navigate = useNavigate()
  const [state, setState] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const memberIds = members.map((member) => member.id)

  const update = (changes: Partial<FormState>) =>
    setState((current) => ({ ...current, ...changes }))
  const updateItem = (index: number, changes: Partial<ExpenseItem>) =>
    update({
      items: state.items.map((item, i) => (i === index ? { ...item, ...changes } : item)),
    })

  let preview: [number, Record<string, number>] | null = null
  let previewError: string | null = null
  try {
    preview = computeShares(splitInput(state, memberIds))
  } catch (err) {
    previewError = err instanceof SplitError ? err.message : 'Check the numbers.'
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    const input = splitInput(state, memberIds)
    setBusy(true)
    setError(null)
    try {
      await api(`/v1/trips/${tripId}/expenses${expenseId ? `/${expenseId}` : ''}`, {
        method: expenseId ? 'PATCH' : 'POST',
        body: {
          title: state.title,
          amountIdr: input.amount,
          paidBy: state.paidBy,
          split: {
            mode: state.mode,
            participants: input.participants,
            shares: state.mode === 'shares' ? state.shares : null,
            exact: state.mode === 'exact' ? input.exact : null,
          },
          items: state.mode === 'items' ? state.items : [],
          taxIdr: input.tax,
          serviceIdr: input.service,
          discountIdr: input.discount,
          receiptPath: state.receiptPath,
        },
      })
      navigate(`/trips/${tripId}/split`, { replace: true })
    } catch (err) {
      setError(errorMessage(err, "Couldn't save the expense. Please try again."))
      setBusy(false)
    }
  }

  async function remove() {
    if (!expenseId) return
    setBusy(true)
    try {
      await api(`/v1/trips/${tripId}/expenses/${expenseId}`, { method: 'DELETE' })
      navigate(`/trips/${tripId}/split`, { replace: true })
    } catch (err) {
      setError(errorMessage(err, "Couldn't delete the expense. Please try again."))
      setBusy(false)
    }
  }

  return (
    <form onSubmit={save} className="space-y-5 py-2">
      <PageHeading title={expenseId ? 'Edit expense' : 'Add expense'} />

      {warnings.length > 0 && (
        <div className="rounded-xl border border-sunset/60 bg-sunset/10 p-3 text-sm">
          <p className="font-semibold">Check the scan against the receipt:</p>
          <ul className="mt-1 list-disc pl-5">
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      <Field id="expense-title" label="What was it for?">
        <input
          id="expense-title"
          required
          maxLength={80}
          placeholder="Dinner at Gudeg Yu Djum"
          value={state.title}
          onChange={(event) => update({ title: event.target.value })}
          className={inputClass}
        />
      </Field>

      <Field id="expense-payer" label="Who paid?">
        <select
          id="expense-payer"
          value={state.paidBy}
          onChange={(event) => update({ paidBy: event.target.value })}
          className={inputClass}
        >
          {members.map((member) => (
            <option key={member.id} value={member.id}>
              {member.displayName}
            </option>
          ))}
        </select>
      </Field>

      <fieldset>
        <legend className="text-sm font-semibold">Split</legend>
        <div className="mt-2 grid grid-cols-4 gap-1 rounded-xl bg-line/50 p-1">
          {modes.map((mode) => (
            <button
              key={mode.value}
              type="button"
              aria-pressed={state.mode === mode.value}
              onClick={() => update({ mode: mode.value })}
              className={`min-h-10 rounded-lg text-sm font-semibold ${
                state.mode === mode.value ? 'bg-card shadow-sm' : 'text-muted'
              }`}
            >
              {mode.label}
            </button>
          ))}
        </div>
      </fieldset>

      {state.mode !== 'items' && (
        <Field id="expense-amount" label="Amount">
          <MoneyInput
            id="expense-amount"
            value={state.amount}
            onChange={(amount) => update({ amount })}
          />
        </Field>
      )}

      {state.mode === 'equal' && (
        <fieldset>
          <legend className="text-sm font-semibold">Who's in?</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {members.map((member) => {
              const selected = state.participants.includes(member.id)
              return (
                <button
                  key={member.id}
                  type="button"
                  aria-pressed={selected}
                  onClick={() =>
                    update({
                      participants: selected
                        ? state.participants.filter((uid) => uid !== member.id)
                        : [...state.participants, member.id],
                    })
                  }
                  className={chipClass(selected)}
                >
                  {firstName(member)}
                </button>
              )
            })}
          </div>
        </fieldset>
      )}

      {state.mode === 'shares' && (
        <fieldset className="space-y-2">
          <legend className="text-sm font-semibold">Shares each</legend>
          {members.map((member) => (
            <div key={member.id} className="flex items-center justify-between gap-3">
              <span>{firstName(member)}</span>
              <Stepper
                label={`Shares for ${firstName(member)}`}
                value={state.shares[member.id] ?? 0}
                onChange={(value) => update({ shares: { ...state.shares, [member.id]: value } })}
              />
            </div>
          ))}
        </fieldset>
      )}

      {state.mode === 'exact' && (
        <fieldset className="space-y-2">
          <legend className="text-sm font-semibold">Amount each</legend>
          {members.map((member) => (
            <div key={member.id} className="flex items-center gap-3">
              <label htmlFor={`exact-${member.id}`} className="w-24 shrink-0">
                {firstName(member)}
              </label>
              <MoneyInput
                id={`exact-${member.id}`}
                value={state.exact[member.id] ?? ''}
                onChange={(value) => update({ exact: { ...state.exact, [member.id]: value } })}
              />
            </div>
          ))}
        </fieldset>
      )}

      {state.mode === 'items' && (
        <section className="space-y-3">
          {state.items.map((item, index) => (
            <div key={index} className="space-y-3 surface-card p-3">
              <div className="flex gap-2">
                <label htmlFor={`item-name-${index}`} className="sr-only">
                  Item name
                </label>
                <input
                  id={`item-name-${index}`}
                  value={item.name}
                  placeholder="Item"
                  onChange={(event) => updateItem(index, { name: event.target.value })}
                  className={`${inputClass} min-w-0 flex-1`}
                />
                <button
                  type="button"
                  onClick={() => update({ items: state.items.filter((_, i) => i !== index) })}
                  className="px-2 text-sm font-semibold text-red-700"
                >
                  Remove
                </button>
              </div>
              <div className="grid grid-cols-[1fr_6rem] gap-2">
                <MoneyInput
                  id={`item-price-${index}`}
                  label="Price each"
                  value={item.unitPriceIdr ? String(item.unitPriceIdr) : ''}
                  onChange={(value) => updateItem(index, { unitPriceIdr: toNumber(value) })}
                />
                <div>
                  <label htmlFor={`item-qty-${index}`} className="sr-only">
                    Quantity
                  </label>
                  <input
                    id={`item-qty-${index}`}
                    inputMode="numeric"
                    value={String(item.qty)}
                    onChange={(event) =>
                      updateItem(index, { qty: Math.max(1, toNumber(digits(event.target.value))) })
                    }
                    className={`${inputClass} text-center tabular-nums`}
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-2">
                {members.map((member) => (
                  <div key={member.id} className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm">{firstName(member)}</span>
                    <Stepper
                      label={`Portions of ${item.name || 'this item'} for ${firstName(member)}`}
                      value={item.portions[member.id] ?? 0}
                      onChange={(value) =>
                        updateItem(index, { portions: { ...item.portions, [member.id]: value } })
                      }
                    />
                  </div>
                ))}
              </div>
            </div>
          ))}
          <button
            type="button"
            onClick={() =>
              update({
                items: [...state.items, { name: '', unitPriceIdr: 0, qty: 1, portions: {} }],
              })
            }
            className={`${buttonClass('outline')} w-full`}
          >
            Add item
          </button>
          <div className="grid grid-cols-3 gap-2">
            <MoneyInput
              id="expense-tax"
              label="Tax"
              value={state.tax}
              onChange={(tax) => update({ tax })}
            />
            <MoneyInput
              id="expense-service"
              label="Service"
              value={state.service}
              onChange={(service) => update({ service })}
            />
            <MoneyInput
              id="expense-discount"
              label="Discount"
              value={state.discount}
              onChange={(discount) => update({ discount })}
            />
          </div>
          <p className="text-xs text-muted">
            Tax, service, and discounts follow what each person ordered.
          </p>
        </section>
      )}

      <section aria-live="polite" className="rounded-2xl bg-lagoon/10 p-4">
        {preview ? (
          <>
            <p className="font-bold tabular-nums">Total {formatIdr(preview[0])}</p>
            <ul className="mt-2 space-y-1 text-sm tabular-nums">
              {members
                .filter((member) => preview[1][member.id])
                .map((member) => (
                  <li key={member.id} className="flex justify-between">
                    <span>{firstName(member)}</span>
                    <span>{formatIdr(preview[1][member.id])}</span>
                  </li>
                ))}
            </ul>
          </>
        ) : (
          <p className="text-sm text-muted">{previewError}</p>
        )}
      </section>

      <ErrorText>{error}</ErrorText>
      <button
        type="submit"
        disabled={busy || preview === null}
        className={`${buttonClass('primary')} w-full`}
      >
        {busy ? 'Saving…' : 'Save expense'}
      </button>
      {expenseId && (
        <button
          type="button"
          onClick={remove}
          disabled={busy}
          className="w-full text-sm font-semibold text-red-700"
        >
          Delete expense
        </button>
      )}
    </form>
  )
}

function MoneyInput({
  id,
  label,
  value,
  onChange,
}: {
  id: string
  label?: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <div className="min-w-0 flex-1">
      {label && (
        <label htmlFor={id} className="mb-1 block text-xs font-semibold text-muted">
          {label}
        </label>
      )}
      <div className="relative">
        <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-sm font-semibold text-muted">
          Rp
        </span>
        <input
          id={id}
          inputMode="numeric"
          autoComplete="off"
          placeholder="0"
          value={value}
          onChange={(event) => onChange(digits(event.target.value))}
          className={`${inputClass} pl-10 tabular-nums`}
        />
      </div>
    </div>
  )
}

function Stepper({
  label,
  value,
  onChange,
}: {
  label: string
  value: number
  onChange: (value: number) => void
}) {
  const button =
    'grid size-9 place-items-center rounded-full border border-line bg-paper text-lg font-bold disabled:opacity-40'
  return (
    <div role="group" aria-label={label} className="flex items-center gap-2">
      <button
        type="button"
        aria-label="Fewer"
        disabled={value === 0}
        onClick={() => onChange(Math.max(0, value - 1))}
        className={button}
      >
        −
      </button>
      <span className="w-5 text-center font-semibold tabular-nums">{value}</span>
      <button
        type="button"
        aria-label="More"
        onClick={() => onChange(value + 1)}
        className={button}
      >
        +
      </button>
    </div>
  )
}
