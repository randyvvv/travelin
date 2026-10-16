import { useState } from 'react'
import { Link } from 'react-router'
import { useSquad, useTrip } from '../../app/trip-context'
import { Avatar } from '../../components/Avatar'
import { ChevronRightIcon } from '../../components/icons'
import { buttonClass } from '../../components/styles'
import { formatDateRange } from '../../lib/format'
import { tripStatusLabel } from '../../lib/status'
import { NextStep } from './NextStep'

const inputs = [
  {
    to: 'places',
    label: 'Places & vote',
    hint: 'Search, AI ideas, and Reels, all checked on Maps',
  },
  { to: 'prefs', label: 'My preferences', hint: 'Budget, interests, food, things to skip' },
  { to: 'reels', label: 'Reels', hint: 'Optional: videos the squad saved' },
]

const planOutputs = [
  { to: 'itinerary', label: 'Itinerary', hint: 'Day-by-day plan and why' },
  { to: 'split', label: 'Split bill', hint: 'Expenses and who owes whom' },
]

const INVITING = new Set(['gathering', 'extracting', 'voting'])
const PLAN_READY = new Set(['planned', 'splitting', 'settling', 'settled'])
const PROCESSING = new Set(['extracting', 'planning'])

export function TripHub() {
  const trip = useTrip()
  const { members } = useSquad()

  return (
    <div className="space-y-6 py-2">
      <section>
        <h1 className="text-2xl font-extrabold tracking-tight">{trip.destination.name}</h1>
        <p className="text-muted">
          {formatDateRange(trip.startDate, trip.endDate)} · from {trip.origin}
        </p>
        <span className="mt-3 inline-block rounded-full bg-lagoon/10 px-3 py-1 text-sm font-semibold text-lagoon-dark">
          {tripStatusLabel[trip.status]}
        </span>
      </section>

      <NextStep />

      {INVITING.has(trip.status) && <InviteCard name={trip.name} inviteCode={trip.inviteCode} />}

      {PROCESSING.has(trip.status) ? null : PLAN_READY.has(trip.status) ? (
        <>
          <TripSection
            title="Trip plan"
            sections={[
              ...planOutputs,
              ...(trip.status === 'settling' || trip.status === 'settled'
                ? [{ to: 'pay', label: 'Payments', hint: 'Pay and confirm transfers' }]
                : []),
            ]}
          />
          <TripSection title="Inputs" sections={inputs} />
        </>
      ) : (
        <TripSection title="Plan your trip" sections={inputs} />
      )}

      <section>
        <h2 className="mb-3 text-sm font-bold tracking-wide text-muted uppercase">
          Squad · {members.length}
        </h2>
        <ul className="space-y-2">
          {members.map((member) => (
            <li key={member.id} className="flex items-center gap-3">
              <Avatar name={member.displayName} photoURL={member.photoURL} />
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold">
                  {member.displayName}
                  {member.role === 'host' && (
                    <span className="ml-2 rounded-full bg-sunset/20 px-2 py-0.5 text-xs font-bold text-ink">
                      Host
                    </span>
                  )}
                </p>
                <p className="text-sm text-muted">
                  {member.prefsDone ? 'Preferences set' : 'No preferences yet'}
                </p>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

function TripSection({
  title,
  sections,
}: {
  title: string
  sections: { to: string; label: string; hint: string }[]
}) {
  return (
    <section>
      <h2 className="mb-3 text-sm font-bold tracking-wide text-muted uppercase">{title}</h2>
      <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-card">
        {sections.map((section) => (
          <li key={section.to}>
            <Link to={section.to} className="flex items-center gap-3 p-4 hover:bg-paper">
              <div className="flex-1">
                <p className="font-semibold">{section.label}</p>
                <p className="text-sm text-muted">{section.hint}</p>
              </div>
              <ChevronRightIcon className="text-muted" />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

function InviteCard({ name, inviteCode }: { name: string; inviteCode: string }) {
  const [status, setStatus] = useState<string | null>(null)
  const url = `${window.location.origin}/join/${inviteCode}`

  async function share() {
    if (navigator.share) {
      try {
        await navigator.share({ title: name, text: `Join our trip "${name}" on Travelin`, url })
        return
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return
      }
    }
    try {
      await navigator.clipboard.writeText(url)
      setStatus('Link copied')
    } catch {
      setStatus('Copy the link above')
    }
  }

  return (
    <section className="rounded-2xl border border-line bg-card p-4">
      <h2 className="font-bold">Invite your squad</h2>
      <p className="mt-1 text-sm text-muted">Anyone with this link can join until voting closes.</p>
      <p className="mt-3 rounded-xl bg-paper px-3 py-2 font-mono text-sm break-all select-all">
        {url}
      </p>
      <div className="mt-3 flex items-center gap-3">
        <button type="button" onClick={share} className={buttonClass('dark')}>
          Share invite link
        </button>
        <span role="status" className="text-sm text-muted">
          {status}
        </span>
      </div>
    </section>
  )
}
