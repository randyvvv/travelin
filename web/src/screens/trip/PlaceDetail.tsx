import { collection, doc, query } from 'firebase/firestore'
import { Star } from 'lucide-react'
import { useMemo } from 'react'
import { Link, useParams } from 'react-router'
import { useSquad, useTrip } from '../../app/trip-context'
import { MapsSources } from '../../components/MapsSources'
import { Splash } from '../../components/Splash'
import { PageHeading } from '../../components/ui'
import { db } from '../../lib/firebase'
import { useCollection } from '../../lib/hooks/useCollection'
import { useDoc } from '../../lib/hooks/useDoc'
import { categoryLabel, formatSecond, priceLabel } from '../../lib/places'
import type { Place, Reel } from '../../lib/types'

export function PlaceDetail() {
  const trip = useTrip()
  const { byId } = useSquad()
  const { placeId } = useParams()
  const { data: place, loading } = useDoc<Place>(
    placeId ? doc(db, 'trips', trip.id, 'places', placeId) : null,
  )
  const reelsQuery = useMemo(() => query(collection(db, 'trips', trip.id, 'reels')), [trip.id])
  const { data: reels } = useCollection<Reel>(reelsQuery)
  const reelsById = new Map(reels.map((reel) => [reel.id, reel]))

  if (loading) return <Splash />
  if (!place) {
    return (
      <p className="py-10 text-center text-muted">
        This place isn't on the board.{' '}
        <Link to=".." relative="path" className="font-semibold text-lagoon">
          Back to places
        </Link>
      </p>
    )
  }

  const { summary } = place
  const facts = [
    { label: 'Best time to visit', value: summary.bestTime },
    { label: 'Prices', value: summary.priceNote },
    { label: 'Food options', value: summary.dietaryNote },
    { label: 'Crowds (estimate)', value: summary.crowdNote },
  ].filter((fact) => fact.value)

  return (
    <article className="space-y-6 py-2">
      <div className="space-y-1">
        <PageHeading
          eyebrow={categoryLabel[place.category] ?? 'Place'}
          title={place.name}
          description={place.address}
        />
        {place.suggestion && (
          <p className="text-sm">
            <span className="font-semibold">Suggested by AI:</span> {place.suggestion.reason}
          </p>
        )}
        <p className="text-sm tabular-nums">
          {place.rating != null && (
            <>
              <span className="inline-flex items-center gap-1 font-semibold">
                <Star size={15} fill="currentColor" aria-hidden="true" />
                {place.rating.toFixed(1)}
              </span>
              {place.userRatingCount != null && (
                <span className="text-muted">
                  {' '}
                  ({place.userRatingCount.toLocaleString('en')} reviews)
                </span>
              )}
            </>
          )}
          {place.priceLevel && priceLabel[place.priceLevel] && (
            <span className="text-muted"> · {priceLabel[place.priceLevel]}</span>
          )}
        </p>
      </div>

      {place.summaryPending && (
        <p role="status" className="text-muted">
          Writing a summary from Google Maps reviews…
        </p>
      )}

      {(summary.highlights.length > 0 || facts.length > 0) && (
        <section className="surface-card p-4">
          <h2 className="font-bold">What visitors say</h2>
          {summary.highlights.length > 0 && (
            <ul className="mt-2 list-disc space-y-1 pl-5">
              {summary.highlights.map((highlight) => (
                <li key={highlight}>{highlight}</li>
              ))}
            </ul>
          )}
          {facts.length > 0 && (
            <dl className="mt-4 space-y-3">
              {facts.map((fact) => (
                <div key={fact.label}>
                  <dt className="text-sm font-semibold text-muted">{fact.label}</dt>
                  <dd>{fact.value}</dd>
                </div>
              ))}
            </dl>
          )}
          <MapsSources sources={place.mapsSources} />
        </section>
      )}

      {place.openingHours?.weekdayDescriptions && (
        <section>
          <h2 className="mb-2 font-bold">Opening hours</h2>
          <ul className="space-y-0.5 text-sm tabular-nums">
            {place.openingHours.weekdayDescriptions.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>
      )}

      {place.mentions.length > 0 && (
        <section>
          <h2 className="mb-2 font-bold">Seen in your Reels</h2>
          <ul className="space-y-2 text-sm">
            {place.mentions.map((mention, index) => {
              const reel = reelsById.get(mention.reelId)
              const uploader = reel ? byId.get(reel.uploaderUid)?.displayName : undefined
              return (
                <li
                  key={`${mention.reelId}-${index}`}
                  className="flex flex-wrap items-baseline gap-x-2"
                >
                  <span>
                    {uploader ? `${uploader}'s Reel` : 'A Reel'} at{' '}
                    <span className="font-semibold tabular-nums">
                      {formatSecond(mention.atSec)}
                    </span>
                  </span>
                  {reel?.sourceUrl && (
                    <a
                      href={reel.sourceUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="font-semibold text-lagoon"
                    >
                      Open original
                    </a>
                  )}
                </li>
              )
            })}
          </ul>
        </section>
      )}

      {place.googleMapsUri && (
        <a
          href={place.googleMapsUri}
          target="_blank"
          rel="noreferrer"
          className="inline-block font-semibold text-lagoon"
        >
          Open in Google Maps
        </a>
      )}
    </article>
  )
}
