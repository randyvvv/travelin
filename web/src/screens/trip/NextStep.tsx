import { collection, query, where } from 'firebase/firestore'
import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '../../app/auth-context'
import { useSquad, useTrip } from '../../app/trip-context'
import { ErrorText } from '../../components/ErrorText'
import { DroppedPlaces, PipelineProgress } from '../../components/Pipeline'
import { buttonClass } from '../../components/styles'
import { api, errorMessage } from '../../lib/api'
import { db } from '../../lib/firebase'
import { useCollection } from '../../lib/hooks/useCollection'
import type { Reel } from '../../lib/types'

/** The one thing the squad should do next, based on the trip's stage. */
export function NextStep() {
  const trip = useTrip()
  const { members } = useSquad()

  switch (trip.status) {
    case 'gathering':
      return <FindPlaces />
    case 'extracting':
      return trip.pipeline ? <PipelineProgress pipeline={trip.pipeline} /> : null
    case 'voting': {
      const voted = members.filter((member) => member.votesSubmittedAt != null).length
      return (
        <section className="space-y-3 rounded-2xl border border-line bg-card p-4">
          <h2 className="font-bold">Voting is open</h2>
          <p className="text-sm text-muted tabular-nums">
            {voted} of {members.length} have submitted their votes.
          </p>
          {trip.planning?.stage === 'failed' && (
            <ErrorText>{trip.planning.error ?? null}</ErrorText>
          )}
          <Link to="places" className={`${buttonClass('primary')} w-full`}>
            Vote on places
          </Link>
        </section>
      )
    }
    case 'planning': {
      const revising = trip.planning?.stage === 'revising'
      return (
        <section role="status" className="space-y-3 rounded-2xl border border-line bg-card p-4">
          <h2 className="font-bold">Planning your days</h2>
          <p className="text-sm text-muted">
            {revising
              ? `Fixing conflicts in the draft (attempt ${trip.planning?.attempt} of 3).`
              : "Drafting a plan around everyone's votes, budgets, and food needs."}
          </p>
          <div className="h-2 animate-pulse rounded-full bg-lagoon/40" />
        </section>
      )
    }
    case 'planned':
      return (
        <section className="space-y-3 rounded-2xl border border-line bg-card p-4">
          <h2 className="font-bold">Your itinerary is ready</h2>
          <p className="text-sm text-muted">
            See the plan for each day. During the trip, log who paid for what in Split bill.
          </p>
          <div className="grid grid-cols-2 gap-3">
            <Link to="itinerary" className={buttonClass('primary')}>
              Itinerary
            </Link>
            <Link to="split" className={buttonClass('outline')}>
              Split bill
            </Link>
          </div>
        </section>
      )
    case 'splitting': {
      const approved = members.filter(
        (member) => member.splitApprovedVersion === trip.split.version,
      ).length
      return (
        <section className="space-y-3 rounded-2xl border border-line bg-card p-4">
          <h2 className="font-bold">Approve the split</h2>
          <p className="text-sm text-muted tabular-nums">
            {approved} of {members.length} have approved. Payments start once everyone agrees.
          </p>
          <Link to="split" className={`${buttonClass('primary')} w-full`}>
            Review the split
          </Link>
        </section>
      )
    }
    case 'settling':
      return (
        <section className="space-y-3 rounded-2xl border border-line bg-card p-4">
          <h2 className="font-bold">Settle up</h2>
          <p className="text-sm text-muted">
            Everyone approved. Pay the people you owe and confirm what you receive.
          </p>
          <Link to="pay" className={`${buttonClass('primary')} w-full`}>
            Go to payments
          </Link>
        </section>
      )
    case 'settled':
      return (
        <section className="rounded-2xl bg-lagoon/10 p-4">
          <h2 className="font-bold text-lagoon-dark">All settled</h2>
          <p className="text-sm">Every payment is confirmed. This trip is now in your history.</p>
        </section>
      )
    default:
      return null
  }
}

function FindPlaces() {
  const trip = useTrip()
  const { user } = useAuth()
  const { byId } = useSquad()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const reelsQuery = useMemo(
    () => query(collection(db, 'trips', trip.id, 'reels'), where('status', '!=', 'link_only')),
    [trip.id],
  )
  const { data: videos } = useCollection<Reel>(reelsQuery)
  const isHost = user?.uid === trip.hostUid
  const failed = trip.pipeline?.stage === 'failed' ? trip.pipeline : null

  async function start() {
    setBusy(true)
    setError(null)
    try {
      await api(`/v1/trips/${trip.id}/ingest`, { method: 'POST' })
    } catch (err) {
      setError(errorMessage(err, "Couldn't start. Please try again."))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="space-y-3 rounded-2xl border border-line bg-card p-4">
      <h2 className="font-bold">Collect Reels, then find places</h2>
      <p className="text-sm text-muted">
        Everyone adds their saved Reels and preferences. The AI then watches every video, checks
        each place on Google Maps, and sums up what visitors say.
      </p>
      <div className="flex gap-3 text-sm font-semibold">
        <Link to="reels" className="text-lagoon">
          Add Reels ({videos.length})
        </Link>
        <Link to="prefs" className="text-lagoon">
          My preferences
        </Link>
      </div>

      {failed && (
        <div className="space-y-2 rounded-xl bg-red-50 p-3">
          <p className="text-sm font-medium text-red-800">{failed.error}</p>
          <DroppedPlaces dropped={failed.dropped} />
        </div>
      )}

      {isHost ? (
        <>
          <ErrorText>{error}</ErrorText>
          <button
            type="button"
            onClick={start}
            disabled={busy || videos.length === 0}
            className={`${buttonClass('primary')} w-full`}
          >
            {busy ? 'Starting…' : failed ? 'Try again' : 'Find places'}
          </button>
          {videos.length === 0 && (
            <p className="text-center text-xs text-muted">Add at least one Reel video first.</p>
          )}
        </>
      ) : (
        <p className="text-sm text-muted">
          {byId.get(trip.hostUid)?.displayName.split(' ')[0] ?? 'The host'} starts finding places
          once the squad is ready.
        </p>
      )}
    </section>
  )
}
