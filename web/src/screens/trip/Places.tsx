import { collection, doc, query, updateDoc } from 'firebase/firestore'
import { useMemo, useState } from 'react'
import { Check, Star, Trash2 } from 'lucide-react'
import { Link } from 'react-router'
import { useSquad, useTrip } from '../../app/trip-context'
import { ErrorText } from '../../components/ErrorText'
import { DroppedPlaces, PipelineProgress } from '../../components/Pipeline'
import { buttonClass } from '../../components/styles'
import { ActionButton, BottomSheet, PageHeading, SectionHeading } from '../../components/ui'
import { api, errorMessage } from '../../lib/api'
import { db } from '../../lib/firebase'
import { useCollection } from '../../lib/hooks/useCollection'
import { categoryLabel, listNames, placeOrigin, sortPlaces, voteOptions } from '../../lib/places'
import type { Place, Vote, WithId } from '../../lib/types'
import { CollectPlaces } from './CollectPlaces'
import { VotingPanel } from './VotingPanel'

export function Places() {
  const trip = useTrip()
  const { me, members } = useSquad()
  const placesQuery = useMemo(() => query(collection(db, 'trips', trip.id, 'places')), [trip.id])
  const { data: places, loading } = useCollection<Place>(placesQuery)
  const [removeTarget, setRemoveTarget] = useState<WithId<Place> | null>(null)
  const [removeBusy, setRemoveBusy] = useState(false)
  const [removeError, setRemoveError] = useState<string | null>(null)

  const voting = trip.status === 'voting'
  const submitted = me?.votesSubmittedAt != null
  const canVote = voting && !submitted
  const sorted = sortPlaces(places, !voting)

  async function removePlace() {
    if (!removeTarget) return
    setRemoveBusy(true)
    setRemoveError(null)
    try {
      await api<void>(`/v1/trips/${trip.id}/places/${encodeURIComponent(removeTarget.id)}`, {
        method: 'DELETE',
      })
      setRemoveTarget(null)
    } catch (err) {
      setRemoveError(errorMessage(err, "Couldn't remove this place. Please try again."))
    } finally {
      setRemoveBusy(false)
    }
  }

  if (trip.status === 'gathering' || trip.status === 'extracting') {
    return (
      <div className="space-y-5 py-2">
        <PageHeading
          title="Places"
          description="Build the list together: search for places, ask the AI for ideas, or add the Reels you saved. Voting starts when the host is ready."
        />
        {trip.status === 'extracting' && trip.pipeline ? (
          <PipelineProgress pipeline={trip.pipeline} />
        ) : (
          <CollectPlaces places={places} />
        )}
        <section>
          <SectionHeading title={`On the list · ${places.length}`} />
          {places.length === 0 ? (
            <p className="text-muted">Nothing yet. Places you add show up here.</p>
          ) : (
            <ul className="space-y-3">
              {sorted.map((place) => (
                <PlaceCard
                  key={place.id}
                  place={place}
                  vote={undefined}
                  mode="collect"
                  onRemove={
                    trip.status === 'gathering'
                      ? () => {
                          setRemoveError(null)
                          setRemoveTarget(place)
                        }
                      : undefined
                  }
                />
              ))}
            </ul>
          )}
        </section>
        <BottomSheet
          open={removeTarget !== null}
          title="Remove this place?"
          description={
            removeTarget
              ? `Remove ${removeTarget.name} from the shared list? It can be added again later.`
              : undefined
          }
          onClose={() => {
            if (removeBusy) return
            setRemoveTarget(null)
            setRemoveError(null)
          }}
        >
          <ErrorText>{removeError}</ErrorText>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <ActionButton
              type="button"
              variant="outline"
              disabled={removeBusy}
              onClick={() => setRemoveTarget(null)}
            >
              Cancel
            </ActionButton>
            <ActionButton
              type="button"
              variant="outline"
              disabled={removeBusy}
              onClick={() => void removePlace()}
              className="border-red-200 text-red-700 hover:border-red-300 hover:bg-red-50"
            >
              <Trash2 size={16} aria-hidden="true" />
              {removeBusy ? 'Removing…' : 'Remove place'}
            </ActionButton>
          </div>
        </BottomSheet>
      </div>
    )
  }

  return (
    <div className="space-y-5 pt-2 pb-40">
      <PageHeading
        title="Places & vote"
        description={`Every place here is checked on Google Maps.${voting ? ' Vote on each one, then submit.' : ''}`}
      />

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
              mode={!voting ? 'results' : canVote ? 'vote' : 'voted'}
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
  mode,
  onRemove,
}: {
  place: WithId<Place>
  vote: Vote | undefined
  mode: 'collect' | 'vote' | 'voted' | 'results'
  onRemove?: () => void
}) {
  const trip = useTrip()
  const { me, byId } = useSquad()

  function cast(value: Vote) {
    if (!me) return
    void updateDoc(doc(db, 'trips', trip.id, 'members', me.id), { [`votes.${place.id}`]: value })
  }

  return (
    <li className="space-y-3 surface-card p-4">
      <Link to={place.id} className="block space-y-1">
        <div className="flex items-start justify-between gap-3">
          <h2 className="font-bold">{place.name}</h2>
          {place.rating != null && (
            <span className="flex shrink-0 items-center gap-1 text-sm font-semibold tabular-nums">
              <Star size={15} fill="currentColor" aria-hidden="true" />
              {place.rating.toFixed(1)}
            </span>
          )}
        </div>
        <p className="text-sm text-muted">
          {categoryLabel[place.category] ?? 'Place'} · {placeOrigin(place, byId)}
        </p>
        {place.summaryPending ? (
          <p className="text-sm text-muted">Writing a summary…</p>
        ) : (
          place.summary.highlights[0] && <p className="text-sm">{place.summary.highlights[0]}</p>
        )}
        {place.suggestion && mode === 'collect' && (
          <p className="text-sm text-muted">Why the AI picked it: {place.suggestion.reason}</p>
        )}
        <p className="text-sm font-semibold text-lagoon">Details</p>
      </Link>

      {mode === 'collect' ? (
        onRemove && (
          <ActionButton
            type="button"
            variant="outline"
            className="min-h-10 px-3 text-sm text-red-700"
            onClick={onRemove}
          >
            <Trash2 size={15} aria-hidden="true" /> Remove
          </ActionButton>
        )
      ) : mode === 'results' ? (
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
              disabled={mode !== 'vote'}
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
    <div className="fixed inset-x-0 bottom-[calc(var(--bottom-nav-height)+env(safe-area-inset-bottom))] z-10 border-t border-line bg-card/95 px-4 pt-3 pb-3 shadow-[0_-6px_24px_rgba(27,27,31,0.06)] backdrop-blur">
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
              {busy ? null : <Check size={17} aria-hidden="true" />}
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
