import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { ErrorText } from '../components/ErrorText'
import { Splash } from '../components/Splash'
import { buttonClass } from '../components/styles'
import { api, errorMessage, type InvitePreview } from '../lib/api'
import { formatDateRange } from '../lib/format'

export function Join() {
  const { inviteCode = '' } = useParams()
  const navigate = useNavigate()
  const [preview, setPreview] = useState<InvitePreview | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [joining, setJoining] = useState(false)
  const [joinError, setJoinError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    api<InvitePreview>(`/v1/join/${encodeURIComponent(inviteCode)}`)
      .then((result) => active && setPreview(result))
      .catch((err) => active && setLoadError(errorMessage(err, "Couldn't load this invite.")))
    return () => {
      active = false
    }
  }, [inviteCode])

  async function join() {
    setJoining(true)
    setJoinError(null)
    try {
      const { tripId } = await api<{ tripId: string }>(
        `/v1/join/${encodeURIComponent(inviteCode)}`,
        { method: 'POST' },
      )
      navigate(`/trips/${tripId}`, { replace: true })
    } catch (err) {
      setJoinError(errorMessage(err, "Couldn't join the trip. Please try again."))
      setJoining(false)
    }
  }

  if (loadError) {
    return (
      <section className="py-12 text-center">
        <h1 className="text-xl font-bold">Invite not found</h1>
        <p className="mt-2 text-muted">{loadError} Ask your friend to share the link again.</p>
        <Link to="/" className="mt-6 inline-block font-semibold text-lagoon">
          Back to home
        </Link>
      </section>
    )
  }
  if (!preview) return <Splash />

  return (
    <section className="space-y-6 py-4">
      <div className="rounded-2xl border border-line bg-card p-5">
        <p className="text-sm font-semibold text-lagoon">{preview.hostName} invited you</p>
        <h1 className="mt-1 text-2xl font-extrabold tracking-tight">{preview.name}</h1>
        <p className="mt-1 text-muted">
          {preview.destination} · {formatDateRange(preview.startDate, preview.endDate)}
        </p>
        <p className="mt-3 text-sm text-muted">
          {preview.memberCount} {preview.memberCount === 1 ? 'person' : 'people'} in the squad so
          far
        </p>
      </div>

      {preview.alreadyMember ? (
        <Link to={`/trips/${preview.tripId}`} className={`${buttonClass('primary')} w-full`}>
          You're already in. Open the trip
        </Link>
      ) : preview.joinable ? (
        <>
          <ErrorText>{joinError}</ErrorText>
          <button
            type="button"
            onClick={join}
            disabled={joining}
            className={`${buttonClass('primary')} w-full`}
          >
            {joining ? 'Joining…' : 'Join the squad'}
          </button>
        </>
      ) : (
        <p className="text-center text-muted">
          This trip isn't taking new members anymore. It's either full or already past voting.
        </p>
      )}
    </section>
  )
}
