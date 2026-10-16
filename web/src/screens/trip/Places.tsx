import { collection, doc, query, updateDoc } from 'firebase/firestore'
import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { useSquad, useTrip } from '../../app/trip-context'
import { ErrorText } from '../../components/ErrorText'
import { DroppedPlaces, PipelineProgress } from '../../components/Pipeline'
import { buttonClass } from '../../components/styles'
import { api, errorMessage } from '../../lib/api'
import { db } from '../../lib/firebase'
import { useCollection } from '../../lib/hooks/useCollection'
import { categoryLabel, listNames, savedByNames, sortPlaces, voteOptions } from '../../lib/places'
import type { Place, Vote, WithId } from '../../lib/types'
import { VotingPanel } from './VotingPanel'

export function Places() {
  const trip = useTrip()
  const { me, members } = useSquad()
  const placesQuery = useMemo(() => query(collection(db, 'trips', trip.id, 'places')), [trip.id])
  const { data: places, loading } = useCollection<Place>(placesQuery)

  const voting = trip.status === 'voting'
  const submitted = me?.votesSubmittedAt != null
  const canVote = voting && !submitted
  const sorted = sortPlaces(places, !voting)

  if (trip.status === 'gathering' || trip.status === 'extracting') {
    return (
      <div className="space-y-4 py-2">
        <h1 className="text-2xl font-extrabold tracking-tight">Places & vote</h1>
        {trip.status === 'extracting' && trip.pipeline ? (
          <PipelineProgress pipeline={trip.pipeline} />
        ) : (
          <p className="text-muted">
            Places show up here once the host starts finding them from the squad's Reels.
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-5 pt-2 pb-40">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Places & vote</h1>
        <p className="mt-1 text-muted">
          Every place here was found in your Reels and checked on Google Maps.
          {voting && ' Vote on each one, then submit.'}
        </p>
      </header>

      {voting && <VotingPanel />}

      {trip.pipeline && <DroppedPlaces dropped={trip.pipeline.dropped} />}

      {loading ? (
        <div className="h-32 animate-pulse rounded-2xl bg-line/60" />
      ) : (
        <ul className="space-y-3">
          {sorted.map((place) => (
            <PlaceCard
              key={place.id}
              place={place}
              vote={me?.votes[place.id]}
              canVote={canVote}
              showTally={!voting}
            />
          ))}
        </ul>
      )}

      {voting && me && (
        <SubmitBar
          tripId={trip.id}
          submitted={submitted}
          votedCount={places.filter((place) => me.votes[place.id]).length}
          placeCount={places.length}
          waitingFor={members
            .filter((member) => member.votesSubmittedAt == null && member.id !== me.id)
            .map((member) => member.displayName.split(' ')[0])}
        />
      )}
    </div>
  )
}

function PlaceCard({
  place,
  vote,
  canVote,
  showTally,
}: {
  place: WithId<Place>
  vote: Vote | undefined
  canVote: boolean
  showTally: boolean
}) {
  const trip = useTrip()
  const { me, byId } = useSquad()

  function cast(value: Vote) {
    if (!me) return
    void updateDoc(doc(db, 'trips', trip.id, 'members', me.id), { [`votes.${place.id}`]: value })
  }

  return (
    <li className="space-y-3 rounded-2xl border border-line bg-card p-4">
      <Link to={place.id} className="block space-y-1">
        <div className="flex items-start justify-between gap-3">
          <h2 className="font-bold">{place.name}</h2>
          {place.rating != null && (
            <span className="shrink-0 text-sm font-semibold tabular-nums">
              ★ {place.rating.toFixed(1)}
            </span>
          )}
        </div>
        <p className="text-sm text-muted">
          {categoryLabel[place.category] ?? 'Place'} · saved by {savedByNames(place, byId)}
        </p>
        {place.summary.highlights[0] && <p className="text-sm">{place.summary.highlights[0]}</p>}
        <p className="text-sm font-semibold text-lagoon">Details</p>
      </Link>

      {showTally ? (
        <p className="text-sm text-muted tabular-nums">
          {place.tally.must} must go · {place.tally.maybe} maybe · {place.tally.skip} skip
        </p>
      ) : (
        <div
          role="radiogroup"
          aria-label={`Your vote for ${place.name}`}
          className="grid grid-cols-3 gap-2"
        >
          {voteOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={vote === option.value}
              disabled={!canVote}
              onClick={() => cast(option.value)}
              className={`min-h-11 rounded-xl border text-sm font-semibold transition disabled:cursor-not-allowed ${
                vote === option.value
                  ? 'border-lagoon bg-lagoon text-white'
                  : 'border-line bg-paper text-ink hover:border-lagoon disabled:hover:border-line'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </li>
  )
}

function SubmitBar({
  tripId,
  submitted,
  votedCount,
  placeCount,
  waitingFor,
}: {
  tripId: string
  submitted: boolean
  votedCount: number
  placeCount: number
  waitingFor: string[]
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      await api(`/v1/trips/${tripId}/votes:submit`, { method: 'POST' })
    } catch (err) {
      setError(errorMessage(err, "Couldn't submit your votes. Please try again."))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-x-0 bottom-0 border-t border-line bg-paper/95 px-4 pt-3 pb-[max(env(safe-area-inset-bottom),0.75rem)] backdrop-blur">
      <div className="mx-auto max-w-md space-y-2">
        {submitted ? (
          <p role="status" className="text-center text-sm">
            <span className="font-semibold">Votes submitted.</span>{' '}
            {waitingFor.length > 0
              ? `Waiting for ${listNames(waitingFor)}.`
              : 'Everyone has voted.'}
          </p>
        ) : (
          <>
            <ErrorText>{error}</ErrorText>
            <button
              type="button"
              onClick={submit}
              disabled={busy}
              className={`${buttonClass('primary')} w-full`}
            >
              {busy ? 'Submitting…' : `Submit my votes (${votedCount} of ${placeCount})`}
            </button>
            <p className="text-center text-xs text-muted">
              You can't change your votes after you submit.
            </p>
          </>
        )}
      </div>
    </div>
  )
}
