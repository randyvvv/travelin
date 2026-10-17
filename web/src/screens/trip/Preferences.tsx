import { doc, updateDoc } from 'firebase/firestore'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { useSquad, useTrip } from '../../app/trip-context'
import { ErrorText } from '../../components/ErrorText'
import { Field } from '../../components/Field'
import { Splash } from '../../components/Splash'
import { buttonClass, chipClass, inputClass } from '../../components/styles'
import { PageHeading } from '../../components/ui'
import { db } from '../../lib/firebase'
import { formatIdr } from '../../lib/format'
import type { Preferences as Prefs } from '../../lib/types'

const INTERESTS = [
  'Local food',
  'Cafés',
  'Nature',
  'Beaches',
  'Culture & history',
  'Temples',
  'Nightlife',
  'Shopping',
  'Photo spots',
  'Adventure',
  'Relaxing',
]
const DIETARY = ['Halal', 'Vegetarian', 'Vegan', 'No pork', 'No seafood', 'No alcohol']
const SKIPS = [
  'Hiking',
  'Early mornings',
  'Long drives',
  'Water activities',
  'Crowded places',
  'Nightlife',
  'Museums',
  'Shopping',
]
const BUDGET_PRESETS = [1_000_000, 2_000_000, 3_000_000, 5_000_000]

export function Preferences() {
  const trip = useTrip()
  const { me } = useSquad()
  if (!me) return <Splash />
  return <PreferencesForm key={me.id} tripId={trip.id} uid={me.id} initial={me.prefs} />
}

function PreferencesForm({
  tripId,
  uid,
  initial,
}: {
  tripId: string
  uid: string
  initial: Prefs
}) {
  const [budget, setBudget] = useState(initial.budgetIdr ? String(initial.budgetIdr) : '')
  const [interests, setInterests] = useState(initial.interests)
  const [dietary, setDietary] = useState(initial.dietary)
  const [skip, setSkip] = useState(initial.skip)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const budgetIdr = Number(budget)

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!Number.isInteger(budgetIdr) || budgetIdr <= 0) {
      return setError('Enter your budget per person in rupiah, for example 2000000.')
    }
    setSaving(true)
    setError(null)
    try {
      await updateDoc(doc(db, 'trips', tripId, 'members', uid), {
        prefs: { budgetIdr, interests, dietary, skip },
        prefsDone: true,
      })
      setSaved(true)
    } catch {
      setError("Couldn't save. Check your connection and try again.")
    } finally {
      setSaving(false)
    }
  }

  // Any change after saving needs another save.
  function edit<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value)
      setSaved(false)
    }
  }

  return (
    <form onSubmit={save} className="space-y-6 py-2">
      <PageHeading
        title="My preferences"
        description="The planner balances everyone's answers and explains what each person compromised on."
      />

      <Field
        id="pref-budget"
        label="Budget per person for the whole trip"
        hint={budgetIdr > 0 ? formatIdr(budgetIdr) : 'Stay, food, tickets, and local transport.'}
      >
        <div className="relative">
          <span className="pointer-events-none absolute inset-y-0 left-4 flex items-center font-semibold text-muted">
            Rp
          </span>
          <input
            id="pref-budget"
            inputMode="numeric"
            autoComplete="off"
            placeholder="2000000"
            value={budget}
            onChange={(event) => edit(setBudget)(event.target.value.replace(/\D/g, ''))}
            className={`${inputClass} pl-12 tabular-nums`}
          />
        </div>
        <div className="flex flex-wrap gap-2 pt-1">
          {BUDGET_PRESETS.map((preset) => (
            <button
              key={preset}
              type="button"
              aria-pressed={budgetIdr === preset}
              onClick={() => edit(setBudget)(String(preset))}
              className={chipClass(budgetIdr === preset)}
            >
              {formatIdr(preset)}
            </button>
          ))}
        </div>
      </Field>

      <ChipGroup
        legend="What are you into?"
        options={INTERESTS}
        value={interests}
        onChange={edit(setInterests)}
      />
      <ChipGroup
        legend="Food needs"
        options={DIETARY}
        value={dietary}
        onChange={edit(setDietary)}
      />
      <ChipGroup legend="Rather skip" options={SKIPS} value={skip} onChange={edit(setSkip)} />

      <ErrorText>{error}</ErrorText>
      <div className="space-y-3">
        <button type="submit" disabled={saving} className={`${buttonClass('primary')} w-full`}>
          {saving ? 'Saving…' : 'Save preferences'}
        </button>
        {saved && (
          <p role="status" className="text-center text-sm font-semibold text-lagoon-dark">
            Saved.{' '}
            <Link to={`/trips/${tripId}`} className="underline">
              Back to the trip
            </Link>
          </p>
        )}
      </div>
    </form>
  )
}

function ChipGroup({
  legend,
  options,
  value,
  onChange,
}: {
  legend: string
  options: string[]
  value: string[]
  onChange: (value: string[]) => void
}) {
  return (
    <fieldset>
      <legend className="text-sm font-semibold">{legend}</legend>
      <div className="mt-2 flex flex-wrap gap-2">
        {options.map((option) => {
          const selected = value.includes(option)
          return (
            <button
              key={option}
              type="button"
              aria-pressed={selected}
              onClick={() =>
                onChange(selected ? value.filter((item) => item !== option) : [...value, option])
              }
              className={chipClass(selected)}
            >
              {option}
            </button>
          )
        })}
      </div>
    </fieldset>
  )
}
