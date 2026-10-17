import { useState, type ChangeEvent, type FormEvent } from 'react'
import { Plus } from 'lucide-react'
import { useNavigate } from 'react-router'
import { ErrorText } from '../components/ErrorText'
import { Field } from '../components/Field'
import { inputClass } from '../components/styles'
import { ActionButton, PageHeading } from '../components/ui'
import { api, errorMessage, type CreateTripResponse } from '../lib/api'

const emptyForm = { name: '', destination: '', origin: '', startDate: '', endDate: '' }
type FormState = typeof emptyForm

export function CreateTrip() {
  const navigate = useNavigate()
  const [form, setForm] = useState<FormState>(emptyForm)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // en-CA formats as YYYY-MM-DD in the user's local time zone.
  const [today] = useState(() => new Date().toLocaleDateString('en-CA'))

  function update(key: keyof FormState) {
    return (event: ChangeEvent<HTMLInputElement>) =>
      setForm((current) => ({ ...current, [key]: event.target.value }))
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const { tripId } = await api<CreateTripResponse>('/v1/trips', { body: form })
      navigate(`/trips/${tripId}`, { replace: true })
    } catch (err) {
      setError(errorMessage(err, "Couldn't create the trip. Check your connection and try again."))
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5 py-2">
      <PageHeading
        title="Create a trip"
        description="Set the basics, then invite everyone to plan together."
      />

      <Field id="trip-name" label="Trip name">
        <input
          id="trip-name"
          required
          maxLength={80}
          placeholder="Jogja long weekend"
          value={form.name}
          onChange={update('name')}
          className={inputClass}
        />
      </Field>
      <Field id="trip-destination" label="Destination">
        <input
          id="trip-destination"
          required
          maxLength={120}
          placeholder="Yogyakarta"
          value={form.destination}
          onChange={update('destination')}
          className={inputClass}
        />
      </Field>
      <Field id="trip-origin" label="Leaving from">
        <input
          id="trip-origin"
          required
          maxLength={120}
          placeholder="Jakarta"
          value={form.origin}
          onChange={update('origin')}
          className={inputClass}
        />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field id="trip-start" label="First day">
          <input
            id="trip-start"
            type="date"
            required
            min={today}
            value={form.startDate}
            onChange={update('startDate')}
            className={inputClass}
          />
        </Field>
        <Field id="trip-end" label="Last day">
          <input
            id="trip-end"
            type="date"
            required
            min={form.startDate || today}
            value={form.endDate}
            onChange={update('endDate')}
            className={inputClass}
          />
        </Field>
      </div>

      <ErrorText>{error}</ErrorText>
      <ActionButton type="submit" disabled={busy} className="w-full">
        <Plus size={18} strokeWidth={2.1} aria-hidden="true" />
        {busy ? 'Creating…' : 'Create trip'}
      </ActionButton>
    </form>
  )
}
