import {
  addDoc,
  collection,
  doc,
  orderBy,
  query,
  serverTimestamp,
  setDoc,
} from 'firebase/firestore'
import { getDownloadURL, ref, uploadBytesResumable } from 'firebase/storage'
import { useMemo, useState, type FormEvent } from 'react'
import { useAuth } from '../../app/auth-context'
import { useSquad, useTrip } from '../../app/trip-context'
import { ErrorText } from '../../components/ErrorText'
import { Field } from '../../components/Field'
import { buttonClass, inputClass } from '../../components/styles'
import { PageHeading, SectionHeading, StatusBadge } from '../../components/ui'
import { db, storage } from '../../lib/firebase'
import { useCollection } from '../../lib/hooks/useCollection'
import type { Reel, WithId } from '../../lib/types'

const MAX_VIDEO_BYTES = 100 * 1024 * 1024

function parseUrl(value: string): URL | null {
  try {
    const url = new URL(value.trim())
    return url.protocol === 'https:' || url.protocol === 'http:' ? url : null
  } catch {
    return null
  }
}

function detectPlatform(url: URL): Reel['platform'] {
  const host = url.hostname.replace(/^www\./, '')
  if (host.endsWith('instagram.com')) return 'instagram'
  if (host.endsWith('tiktok.com')) return 'tiktok'
  if (host === 'youtu.be' || host.endsWith('youtube.com')) return 'youtube'
  return 'other'
}

const platformLabel: Record<Reel['platform'], string> = {
  instagram: 'Instagram',
  tiktok: 'TikTok',
  youtube: 'YouTube',
  other: 'Video',
}

const statusLabel: Record<Reel['status'], string> = {
  queued: 'Waiting for AI',
  processing: 'AI is watching…',
  done: 'Read by AI',
  failed: "Couldn't read",
  link_only: 'Link only',
}

export function Reels() {
  const trip = useTrip()
  const reelsQuery = useMemo(
    () => query(collection(db, 'trips', trip.id, 'reels'), orderBy('createdAt', 'desc')),
    [trip.id],
  )
  const { data: reels, loading } = useCollection<Reel>(reelsQuery)

  return (
    <div className="space-y-6 py-2">
      <PageHeading
        title="Reels"
        description="Optional. Add the travel Reels your squad keeps sharing, and the AI watches each video for places. You can also search for places or ask for AI suggestions on the Places page."
      />

      {trip.status === 'gathering' ? (
        <>
          <UploadReel tripId={trip.id} />
          <LinkReel tripId={trip.id} />
        </>
      ) : (
        <p className="rounded-xl bg-line/50 p-3 text-sm text-muted">
          The squad has moved past collecting Reels, so new ones can't be added.
        </p>
      )}

      <section>
        <SectionHeading title={`Added · ${reels.length}`} />
        {loading ? (
          <div className="h-20 animate-pulse rounded-2xl bg-line/60" />
        ) : reels.length === 0 ? (
          <p className="text-muted">No Reels yet. Add the first one above.</p>
        ) : (
          <ul className="space-y-3">
            {reels.map((reel) => (
              <ReelCard key={reel.id} reel={reel} />
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

function UploadReel({ tripId }: { tripId: string }) {
  const { user } = useAuth()
  const [file, setFile] = useState<File | null>(null)
  const [link, setLink] = useState('')
  const [progress, setProgress] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [inputKey, setInputKey] = useState(0)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!user || !file) return
    if (!file.type.startsWith('video/')) return setError('Choose a video file, such as MP4 or MOV.')
    if (file.size > MAX_VIDEO_BYTES) {
      return setError('That video is over 100 MB. Trim it or pick a shorter one.')
    }
    const sourceUrl = link.trim() ? parseUrl(link) : null
    if (link.trim() && !sourceUrl) return setError('The original link should start with https://')

    setError(null)
    setProgress(0)
    const reelRef = doc(collection(db, 'trips', tripId, 'reels'))
    const extension = file.name.includes('.') ? file.name.split('.').pop()!.toLowerCase() : 'mp4'
    const storagePath = `trips/${tripId}/reels/${user.uid}/${reelRef.id}.${extension}`
    try {
      const task = uploadBytesResumable(ref(storage, storagePath), file, {
        contentType: file.type,
      })
      task.on('state_changed', (snapshot) =>
        setProgress(snapshot.bytesTransferred / snapshot.totalBytes),
      )
      await task
      await setDoc(reelRef, {
        uploaderUid: user.uid,
        source: 'upload',
        storagePath,
        fileName: file.name,
        platform: sourceUrl ? detectPlatform(sourceUrl) : 'other',
        ...(sourceUrl ? { sourceUrl: sourceUrl.href } : {}),
        status: 'queued',
        createdAt: serverTimestamp(),
      })
      setFile(null)
      setLink('')
      setInputKey((key) => key + 1)
    } catch {
      setError('Upload failed. Check your connection and try again.')
    } finally {
      setProgress(null)
    }
  }

  const uploading = progress !== null
  return (
    <form onSubmit={submit} className="space-y-4 surface-card p-4">
      <h2 className="font-bold">Upload a video</h2>
      <Field id="reel-file" label="Video file" hint="MP4 or MOV, up to 100 MB.">
        <input
          key={inputKey}
          id="reel-file"
          type="file"
          accept="video/*"
          required
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          className="block w-full text-sm file:mr-3 file:h-10 file:rounded-full file:border-0 file:bg-lagoon/10 file:px-4 file:font-semibold file:text-lagoon-dark"
        />
      </Field>
      <Field
        id="reel-source"
        label="Original link (optional)"
        hint="So the squad can open the Reel where it was posted."
      >
        <input
          id="reel-source"
          type="url"
          inputMode="url"
          placeholder="https://www.instagram.com/reel/…"
          value={link}
          onChange={(event) => setLink(event.target.value)}
          className={inputClass}
        />
      </Field>
      <ErrorText>{error}</ErrorText>
      {uploading && (
        <div
          role="progressbar"
          aria-label="Upload progress"
          aria-valuenow={Math.round(progress * 100)}
          aria-valuemin={0}
          aria-valuemax={100}
          className="h-2 overflow-hidden rounded-full bg-line"
        >
          <div
            className="h-full bg-lagoon transition-all"
            style={{ width: `${progress * 100}%` }}
          />
        </div>
      )}
      <button
        type="submit"
        disabled={!file || uploading}
        className={`${buttonClass('primary')} w-full`}
      >
        {uploading ? `Uploading… ${Math.round(progress * 100)}%` : 'Upload Reel'}
      </button>
    </form>
  )
}

function LinkReel({ tripId }: { tripId: string }) {
  const { user } = useAuth()
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!user) return
    const url = parseUrl(value)
    if (!url) return setError('Paste a full link that starts with https://')
    const platform = detectPlatform(url)
    setBusy(true)
    setError(null)
    try {
      await addDoc(collection(db, 'trips', tripId, 'reels'), {
        uploaderUid: user.uid,
        source: 'link',
        sourceUrl: url.href,
        platform,
        // Gemini can watch YouTube links directly; other platforms need the video file.
        status: platform === 'youtube' ? 'queued' : 'link_only',
        createdAt: serverTimestamp(),
      })
      setValue('')
    } catch {
      setError("Couldn't save the link. Check your connection and try again.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 surface-card p-4">
      <h2 className="font-bold">Only have a link?</h2>
      <p className="text-sm text-muted">
        YouTube links are read by the AI. Instagram and TikTok links are saved for reference; upload
        the video so the AI can read it.
      </p>
      <label htmlFor="reel-link" className="sr-only">
        Reel link
      </label>
      <div className="flex gap-2">
        <input
          id="reel-link"
          type="url"
          inputMode="url"
          required
          placeholder="https://…"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          className={`${inputClass} min-w-0 flex-1`}
        />
        <button type="submit" disabled={busy} className={buttonClass('dark')}>
          Add
        </button>
      </div>
      <ErrorText>{error}</ErrorText>
    </form>
  )
}

function ReelCard({ reel }: { reel: WithId<Reel> }) {
  const { byId } = useSquad()
  const [videoUrl, setVideoUrl] = useState<string | null>(null)
  const [loadingVideo, setLoadingVideo] = useState(false)
  const uploader = byId.get(reel.uploaderUid)?.displayName ?? 'Someone'
  const title =
    reel.fileName ?? (reel.sourceUrl ? new URL(reel.sourceUrl).hostname.replace(/^www\./, '') : '')

  async function play() {
    if (!reel.storagePath) return
    setLoadingVideo(true)
    try {
      setVideoUrl(await getDownloadURL(ref(storage, reel.storagePath)))
    } finally {
      setLoadingVideo(false)
    }
  }

  const statusText =
    reel.status === 'done' && reel.placesFound !== undefined
      ? `${reel.placesFound} ${reel.placesFound === 1 ? 'place' : 'places'} found`
      : statusLabel[reel.status]

  return (
    <li className="space-y-3 surface-card p-4">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold">{title}</p>
          <p className="text-sm text-muted">
            {platformLabel[reel.platform]} · added by {uploader}
          </p>
        </div>
        <StatusBadge
          tone={
            reel.status === 'failed' ? 'danger' : reel.status === 'done' ? 'success' : 'neutral'
          }
          className="shrink-0"
        >
          {statusText}
        </StatusBadge>
      </div>
      {videoUrl && (
        <video src={videoUrl} controls playsInline className="max-h-96 w-full rounded-xl bg-ink" />
      )}
      <div className="flex flex-wrap gap-4 text-sm font-semibold">
        {reel.storagePath && !videoUrl && (
          <button type="button" onClick={play} disabled={loadingVideo} className="text-lagoon">
            {loadingVideo ? 'Loading…' : 'Play video'}
          </button>
        )}
        {reel.sourceUrl && (
          <a href={reel.sourceUrl} target="_blank" rel="noreferrer" className="text-lagoon">
            Open original
          </a>
        )}
      </div>
    </li>
  )
}
