import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { useSquad, useTrip } from '../../app/trip-context'
import { Avatar } from '../../components/Avatar'
import {
  ActionButton,
  FeaturedHighlight,
  ListRow,
  PageHeading,
  SectionHeading,
  StatusBadge,
  SurfaceCard,
} from '../../components/ui'
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
        <PageHeading
          eyebrow={trip.name}
          title={trip.destination.name}
          description={`${formatDateRange(trip.startDate, trip.endDate)} · from ${trip.origin}`}
        />
        <StatusBadge tone="brand">{tripStatusLabel[trip.status]}</StatusBadge>
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
        <TripSection
          title="Plan your trip"
          sections={inputs}
          highlightReels={trip.status === 'gathering'}
          infoDescription="Use Places & vote to add places and decide where to go, add preferences to guide the itinerary, and optionally save Reels. Your squad can contribute until voting starts."
        />
      )}

      <section>
        <SectionHeading title={`Squad · ${members.length}`} />
        <ul className="space-y-2">
          {members.map((member) => (
            <li key={member.id} className="flex items-center gap-3">
              <Avatar name={member.displayName} photoURL={member.photoURL} />
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold">
                  {member.displayName}
                  {member.role === 'host' && (
                    <StatusBadge tone="warm" className="ml-2 align-middle">
                      Host
                    </StatusBadge>
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
  infoDescription,
  highlightReels = false,
}: {
  title: string
  sections: { to: string; label: string; hint: string }[]
  infoDescription?: string
  highlightReels?: boolean
}) {
  return (
    <section>
      <SectionHeading
        title={title}
        infoDescription={infoDescription}
        infoLabel={`About ${title}`}
      />
      <ul className="list-surface divide-y divide-line overflow-hidden">
        {sections.map((section) => {
          const isReels = section.to === 'reels'
          const row = (
            <ListRow
              to={section.to}
              title={section.label}
              subtitle={section.hint}
              className={isReels && highlightReels ? 'trip-reels-highlight__row' : ''}
              trailing={
                <ChevronRight size={19} className="shrink-0 text-muted" aria-hidden="true" />
              }
            />
          )

          return (
            <li key={section.to} className={isReels ? 'trip-reels-item' : undefined}>
              {isReels && highlightReels ? (
                <FeaturedHighlight className="trip-reels-highlight">{row}</FeaturedHighlight>
              ) : (
                row
              )}
              {isReels && (
                <span className="trip-reels-featured rounded-full bg-sunset/20 px-2 py-0.5 text-[0.65rem] leading-4 font-bold text-ink">
                  Featured
                </span>
              )}
            </li>
          )
        })}
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
    <SurfaceCard className="p-4">
      <h2 className="font-bold">Invite your squad</h2>
      <p className="mt-1 text-sm text-muted">Anyone with this link can join until voting closes.</p>
      <p className="mt-3 rounded-xl bg-paper px-3 py-2 font-mono text-sm break-all select-all">
        {url}
      </p>
      <div className="mt-3 flex items-center gap-3">
        <ActionButton type="button" onClick={share} variant="dark">
          Share invite link
        </ActionButton>
        <span role="status" className="text-sm text-muted">
          {status}
        </span>
      </div>
    </SurfaceCard>
  )
}
