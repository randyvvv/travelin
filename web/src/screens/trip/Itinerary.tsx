import { collection, doc, orderBy, query } from 'firebase/firestore'
import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { useSquad, useTrip } from '../../app/trip-context'
import { DayMap, type MapPoint } from '../../components/DayMap'
import { Splash } from '../../components/Splash'
import { db } from '../../lib/firebase'
import { formatDay, formatIdr } from '../../lib/format'
import { useCollection } from '../../lib/hooks/useCollection'
import { useDoc } from '../../lib/hooks/useDoc'
import { listNames } from '../../lib/places'
import type { ItineraryDay, Member, Place, Plan, Stop, WithId } from '../../lib/types'
import { StayCard } from './StayCard'

const PLANNED = new Set(['planned', 'splitting', 'settling', 'settled'])

export function Itinerary() {
  const trip = useTrip()
  if (!PLANNED.has(trip.status)) {
    return (
      <div className="space-y-2 py-2">
        <h1 className="text-2xl font-extrabold tracking-tight">Itinerary</h1>
        <p className="text-muted">
          {trip.status === 'planning'
            ? 'The planner is working on it. This page fills in as soon as it is done.'
            : 'The itinerary is planned once everyone has voted on places.'}
        </p>
      </div>
    )
  }
  return <PlannedItinerary tripId={trip.id} />
}

function PlannedItinerary({ tripId }: { tripId: string }) {
  const { members, me, byId } = useSquad()
  const daysQuery = useMemo(
    () => query(collection(db, 'trips', tripId, 'itinerary'), orderBy('date')),
    [tripId],
  )
  const placesQuery = useMemo(() => query(collection(db, 'trips', tripId, 'places')), [tripId])
  const { data: days, loading } = useCollection<ItineraryDay>(daysQuery)
  const { data: places } = useCollection<Place>(placesQuery)
  const { data: plan } = useDoc<Plan>(doc(db, 'trips', tripId, 'plan', 'current'))
  const [selected, setSelected] = useState(0)

  const placesById = useMemo(() => new Map(places.map((place) => [place.id, place])), [places])
  const day = days[Math.min(selected, days.length - 1)]
  const points = useMemo<MapPoint[]>(
    () =>
      (day?.stops ?? []).flatMap((stop) => {
        const place = placesById.get(stop.placeId)
        return place ? [{ key: stop.placeId, title: place.name, ...place.location }] : []
      }),
    [day, placesById],
  )

  if (loading) return <Splash />
  const myEstimate = plan?.estimates.find((estimate) => estimate.uid === me?.id)

  return (
    <div className="space-y-6 py-2">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Itinerary</h1>
        {myEstimate && (
          <p className="mt-1 text-muted tabular-nums">
            Your estimated spend: {formatIdr(myEstimate.amountIdr)}
            {me?.prefs.budgetIdr ? ` of your ${formatIdr(me.prefs.budgetIdr)} budget` : ''}
          </p>
        )}
      </header>

      <div role="tablist" aria-label="Trip days" className="flex gap-2 overflow-x-auto pb-1">
        {days.map((item, index) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={item === day}
            onClick={() => setSelected(index)}
            className={`shrink-0 rounded-full border px-4 py-2 text-sm font-semibold ${
              item === day ? 'border-ink bg-ink text-paper' : 'border-line bg-card'
            }`}
          >
            Day {index + 1} · {formatDay(item.date)}
          </button>
        ))}
      </div>

      {day && (
        <section role="tabpanel" aria-label={formatDay(day.date)} className="space-y-4">
          <h2 className="text-lg font-bold">{day.title}</h2>
          <DayMap points={points} />
          <ol className="space-y-3">
            {day.stops.map((stop, index) => (
              <StopItem
                key={`${stop.placeId}-${stop.start}`}
                number={index + 1}
                stop={stop}
                place={placesById.get(stop.placeId)}
                members={members}
                byId={byId}
              />
            ))}
          </ol>
        </section>
      )}

      {plan && <PlanNotes plan={plan} byId={byId} />}
    </div>
  )
}

function StopItem({
  number,
  stop,
  place,
  members,
  byId,
}: {
  number: number
  stop: Stop
  place: WithId<Place> | undefined
  members: WithId<Member>[]
  byId: Map<string, WithId<Member>>
}) {
  const firstName = (uid: string) => byId.get(uid)?.displayName.split(' ')[0] ?? 'Someone'
  const missing = members.filter((member) => !stop.attendees.includes(member.id))
  const who =
    missing.length === 0
      ? null
      : stop.attendees.length <= missing.length
        ? `Just ${listNames(stop.attendees.map(firstName))}`
        : `Without ${listNames(missing.map((member) => firstName(member.id)))}`

  return (
    <li className="flex gap-3 rounded-2xl border border-line bg-card p-4">
      <span
        aria-hidden
        className="grid size-7 shrink-0 place-items-center rounded-full bg-lagoon text-sm font-bold text-white"
      >
        {number}
      </span>
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-sm font-semibold text-muted tabular-nums">
          {stop.start}–{stop.end}
        </p>
        {place ? (
          <Link to={`../places/${place.id}`} relative="path" className="font-bold">
            {place.name}
          </Link>
        ) : (
          <p className="font-bold">A place</p>
        )}
        {stop.note && <p className="text-sm">{stop.note}</p>}
        <p className="text-sm text-muted tabular-nums">
          {stop.estCostPerPersonIdr > 0
            ? `About ${formatIdr(stop.estCostPerPersonIdr)} per person`
            : 'Free'}
          {who && ` · ${who}`}
        </p>
      </div>
    </li>
  )
}

function PlanNotes({ plan, byId }: { plan: Plan; byId: Map<string, WithId<Member>> }) {
  const name = (uid: string) => byId.get(uid)?.displayName.split(' ')[0] ?? 'Someone'
  return (
    <>
      <section className="rounded-2xl bg-lagoon/10 p-4">
        <h2 className="font-bold text-lagoon-dark">Why this plan</h2>
        <p className="mt-2">{plan.whyThisPlan}</p>
      </section>

      {plan.compromises.length > 0 && (
        <section>
          <h2 className="mb-2 font-bold">Who compromised on what</h2>
          <ul className="space-y-2">
            {plan.compromises.map((item, index) => (
              <li key={index} className="rounded-xl border border-line bg-card p-3 text-sm">
                <span className="font-semibold">{name(item.uid)}</span> gave up {item.gaveUp} and
                got {item.got}. <span className="text-muted">{item.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {plan.stay && <StayCard stay={plan.stay} />}

      {plan.warnings.length > 0 && (
        <section className="rounded-2xl border border-sunset/60 bg-sunset/10 p-4">
          <h2 className="font-bold">Heads-up</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {plan.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </section>
      )}
    </>
  )
}
