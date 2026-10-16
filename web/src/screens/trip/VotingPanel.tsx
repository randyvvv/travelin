import { useState, type FormEvent } from 'react'
import { useAuth } from '../../app/auth-context'
import { useSquad, useTrip } from '../../app/trip-context'
import { ErrorText } from '../../components/ErrorText'
import { buttonClass, inputClass } from '../../components/styles'
import { api, errorMessage } from '../../lib/api'
import { formatDateTime } from '../../lib/format'
import { useNow } from '../../lib/hooks/useNow'
import { listNames } from '../../lib/places'

/** "YYYY-MM-DDTHH:mm" in local time, the value format of <input type="datetime-local">. */
function toInputValue(date: Date): string {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}

/** Deadline and progress for everyone; deadline and "close voting" controls for the host. */
export function VotingPanel() {
  const trip = useTrip()
  const { user } = useAuth()
  const { members } = useSquad()
  const now = useNow()
  const deadline = trip.votingDeadline?.toDate() ?? null
  const closed = deadline !== null && deadline.getTime() <= now
  const submitted = members.filter((member) => member.votesSubmittedAt != null).length
  const notVoted = members
    .filter((member) => member.votesSubmittedAt == null)
    .map((member) => member.displayName.split(' ')[0])

  return (
    <section className="space-y-3 rounded-2xl border border-line bg-card p-4">
      <div>
        <p className="font-semibold">
          {deadline
            ? `Voting ${closed ? 'closed' : 'closes'} ${formatDateTime(deadline)}`
            : 'No voting deadline yet'}
        </p>
        <p className="text-sm text-muted tabular-nums">
          {submitted} of {members.length} have submitted their votes.
        </p>
      </div>
      {trip.planning?.stage === 'failed' && <ErrorText>{trip.planning.error ?? null}</ErrorText>}
      {user?.uid === trip.hostUid && (
        <HostControls tripId={trip.id} deadline={deadline} notVoted={notVoted} now={now} />
      )}
    </section>
  )
}

function HostControls({
  tripId,
  deadline,
  notVoted,
  now,
}: {
  tripId: string
  deadline: Date | null
  notVoted: string[]
  now: number
}) {
  const [value, setValue] = useState(deadline ? toInputValue(deadline) : '')
  const [busy, setBusy] = useState<'deadline' | 'plan' | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function saveDeadline(next: string | null) {
    setBusy('deadline')
    setError(null)
    try {
      await api(`/v1/trips/${tripId}/voting`, {
        method: 'PATCH',
        body: { deadline: next ? new Date(next).toISOString() : null },
      })
      if (next === null) setValue('')
    } catch (err) {
      setError(errorMessage(err, "Couldn't save the deadline. Please try again."))
    } finally {
      setBusy(null)
    }
  }

  async function plan() {
    setBusy('plan')
    setError(null)
    try {
      await api(`/v1/trips/${tripId}/plan`, { method: 'POST' })
    } catch (err) {
      setError(errorMessage(err, "Couldn't start planning. Please try again."))
      setBusy(null)
    }
  }

  function submitDeadline(event: FormEvent) {
    event.preventDefault()
    if (value) void saveDeadline(value)
  }

  return (
    <div className="space-y-3 border-t border-line pt-3">
      <form onSubmit={submitDeadline} className="space-y-2">
        <label htmlFor="voting-deadline" className="block text-sm font-semibold">
          Voting deadline
        </label>
        <div className="flex gap-2">
          <input
            id="voting-deadline"
            type="datetime-local"
            required
            min={toInputValue(new Date(now))}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            className={`${inputClass} min-w-0 flex-1`}
          />
          <button type="submit" disabled={busy !== null} className={buttonClass('dark')}>
            Set
          </button>
        </div>
        {deadline && (
          <button
            type="button"
            onClick={() => saveDeadline(null)}
            disabled={busy !== null}
            className="text-sm font-semibold text-lagoon"
          >
            Remove deadline
          </button>
        )}
      </form>

      <ErrorText>{error}</ErrorText>
      <button
        type="button"
        onClick={plan}
        disabled={busy !== null}
        className={`${buttonClass('primary')} w-full`}
      >
        {busy === 'plan' ? 'Starting…' : 'Close voting and plan the trip'}
      </button>
      {notVoted.length > 0 && (
        <p className="text-center text-xs text-muted">
          {listNames(notVoted)} {notVoted.length === 1 ? "hasn't" : "haven't"} submitted yet. Only
          submitted votes count.
        </p>
      )}
    </div>
  )
}
