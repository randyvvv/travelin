import { useState, type FormEvent } from 'react'
import { useTrip } from '../../app/trip-context'
import { ErrorText } from '../../components/ErrorText'
import { buttonClass, inputClass } from '../../components/styles'
import { api, errorMessage, type PlaceHit } from '../../lib/api'
import { categoryLabel } from '../../lib/places'

const SUGGESTING = new Set(['starting', 'thinking', 'verifying', 'summarizing'])
const suggestStage: Record<string, string> = {
  starting: 'Getting started',
  thinking: "Looking for places that fit everyone's preferences",
  verifying: 'Checking each one on Google Maps',
  summarizing: 'Reading what visitors say',
}

/** The two ways to add places without Reels: search Google Maps, or ask the AI. */
export function CollectPlaces() {
  return (
    <div className="space-y-4">
      <SearchPlaces />
      <SuggestPlaces />
    </div>
  )
}

function SearchPlaces() {
  const trip = useTrip()
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<PlaceHit[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [adding, setAdding] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function search(event: FormEvent) {
    event.preventDefault()
    if (query.trim().length < 2) return
    setSearching(true)
    setError(null)
    try {
      setHits(
        await api<PlaceHit[]>(
          `/v1/trips/${trip.id}/places:search?q=${encodeURIComponent(query.trim())}`,
        ),
      )
    } catch (err) {
      setError(errorMessage(err, "Couldn't search right now. Please try again."))
    } finally {
      setSearching(false)
    }
  }

  async function add(hit: PlaceHit) {
    setAdding(hit.placeId)
    setError(null)
    try {
      await api(`/v1/trips/${trip.id}/places`, { body: { placeId: hit.placeId } })
      setHits(
        (current) =>
          current?.map((item) =>
            item.placeId === hit.placeId ? { ...item, onBoard: true } : item,
          ) ?? null,
      )
    } catch (err) {
      setError(errorMessage(err, "Couldn't add that place. Please try again."))
    } finally {
      setAdding(null)
    }
  }

  return (
    <section className="space-y-3 surface-card p-4">
      <h2 className="font-bold">Search for a place</h2>
      <form onSubmit={search} className="flex gap-2">
        <label htmlFor="place-search" className="sr-only">
          Place name
        </label>
        <input
          id="place-search"
          type="search"
          placeholder={`A café, beach, or sight in ${trip.destination.name}`}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className={`${inputClass} min-w-0 flex-1`}
        />
        <button type="submit" disabled={searching} className={buttonClass('dark')}>
          {searching ? '…' : 'Search'}
        </button>
      </form>
      <ErrorText>{error}</ErrorText>
      {hits && hits.length === 0 && (
        <p className="text-sm text-muted">Nothing found. Try another name.</p>
      )}
      {hits && hits.length > 0 && (
        <ul className="divide-y divide-line">
          {hits.map((hit) => (
            <li key={hit.placeId} className="flex items-center gap-3 py-2">
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold">{hit.name}</p>
                <p className="truncate text-sm text-muted">
                  {categoryLabel[hit.category] ?? 'Place'}
                  {hit.rating != null && ` · ★ ${hit.rating.toFixed(1)}`} · {hit.address}
                </p>
              </div>
              {hit.onBoard ? (
                <span className="shrink-0 text-sm font-semibold text-lagoon-dark">Added</span>
              ) : (
                <button
                  type="button"
                  onClick={() => add(hit)}
                  disabled={adding !== null}
                  className="shrink-0 rounded-full border border-lagoon px-4 py-2 text-sm font-semibold text-lagoon"
                >
                  {adding === hit.placeId ? 'Adding…' : 'Add'}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function SuggestPlaces() {
  const trip = useTrip()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const state = trip.suggesting
  const active = state !== undefined && SUGGESTING.has(state.stage)

  async function suggest() {
    setBusy(true)
    setError(null)
    try {
      await api(`/v1/trips/${trip.id}/places:suggest`, { method: 'POST' })
    } catch (err) {
      setError(errorMessage(err, "Couldn't ask for suggestions. Please try again."))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="space-y-3 surface-card p-4">
      <h2 className="font-bold">Not sure where to start?</h2>
      <p className="text-sm text-muted">
        The AI picks places in {trip.destination.name} that fit the squad's interests and food
        needs, then checks each one on Google Maps. It works best once everyone has set their
        preferences.
      </p>
      {active ? (
        <div role="status" className="space-y-2">
          <p className="text-sm font-semibold">
            {suggestStage[state.stage]}
            {state.total > 0 && (
              <span className="text-muted tabular-nums">
                {' '}
                · {state.done} of {state.total}
              </span>
            )}
          </p>
          <div className="h-2 animate-pulse rounded-full bg-lagoon/40" />
        </div>
      ) : (
        <>
          {state?.stage === 'done' && (
            <p role="status" className="text-sm font-semibold text-lagoon-dark">
              Added {state.added} {state.added === 1 ? 'suggestion' : 'suggestions'} below.
            </p>
          )}
          <ErrorText>
            {error ?? (state?.stage === 'failed' ? (state.error ?? null) : null)}
          </ErrorText>
          <button
            type="button"
            onClick={suggest}
            disabled={busy}
            className={`${buttonClass('outline')} w-full`}
          >
            {busy ? 'Asking…' : state?.stage === 'done' ? 'Suggest more places' : 'Suggest places'}
          </button>
        </>
      )}
    </section>
  )
}
