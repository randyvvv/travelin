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
          <Link to="places" className={`${buttonClass('primary')} w-full`}>
            Vote on places
          </Link>
        </section>
      )
    }
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
