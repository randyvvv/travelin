import { useEffect, useMemo, useState } from 'react'
import {
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  MapPin,
  MapPinned,
  Plus,
  SlidersHorizontal,
  Sparkles,
  UsersRound,
  Vote,
} from 'lucide-react'
import { Link, useNavigate } from 'react-router'
import { useAuth } from '../app/auth-context'
import { ErrorText } from '../components/ErrorText'
import { LazyPlacePhoto } from '../components/LazyPlacePhoto'
import { TripList } from '../components/TripList'
import {
  ActionButton,
  ActionLink,
  BottomSheet,
  FeaturedHighlight,
  PageHeading,
  SectionHeading,
  StatusBadge,
  SurfaceCard,
} from '../components/ui'
import {
  api,
  errorMessage,
  type HomeIdea,
  type HomeIdeasResponse,
  type PlaceAdded,
} from '../lib/api'
import { formatDateRange, formatDateTime } from '../lib/format'
import { useHomeActivity } from '../lib/hooks/useHomeActivity'
import { useNow } from '../lib/hooks/useNow'
import { useTrips } from '../lib/hooks/useTrips'
import {
  deriveHomeTasks,
  localIsoDate,
  selectNextTrip,
  topHomeTasks,
  destinationFromAddress,
  type HomeTask,
} from '../lib/homeDashboard'
import type { Trip, WithId } from '../lib/types'

export function Home() {
  const { user } = useAuth()
  const { trips, loading, error, uid } = useTrips()
  const now = useNow(60_000)
  const today = localIsoDate(new Date(now))
  const activeTrips = useMemo(() => trips.filter((trip) => trip.status !== 'settled'), [trips])
  const nextTrip = useMemo(() => selectNextTrip(trips, today), [trips, today])
  const activity = useHomeActivity(trips, uid)
  const tasks = useMemo(
    () => (uid ? deriveHomeTasks(activeTrips, activity.members, activity.transfers, uid) : []),
    [activeTrips, activity.members, activity.transfers, uid],
  )
  return (
    <div className="space-y-7 py-2 pb-3">
      <section className="dashboard-welcome">
        <PageHeading
          eyebrow={`Hi ${user?.displayName?.split(' ')[0] ?? 'there'}`}
          title="Where's the squad going next?"
        />
        <FeaturedHighlight className="featured-highlight--action mt-5">
          <ActionLink to="/trips/new" className="w-full">
            <Plus size={19} strokeWidth={2.1} aria-hidden="true" />
            Create a trip
          </ActionLink>
        </FeaturedHighlight>
      </section>

      {nextTrip && <NextTripCard trip={nextTrip} today={today} />}

      <section>
        <SectionHeading title="What needs me" />
        {loading || activity.loading ? (
          <TaskLoading />
        ) : error ? (
          <p role="alert" className="dashboard-inline-error">
            {tripLoadError(error.code)}
          </p>
        ) : activity.error ? (
          <p role="alert" className="dashboard-inline-error">
            {activity.error === 'permission-denied'
              ? 'We could not read your trip updates. Check your trip access and try again.'
              : 'Your trip updates could not be loaded. Check your connection and try again.'}
          </p>
        ) : tasks.length === 0 ? (
          <AllCaughtUp />
        ) : (
          <ul className="list-surface divide-y divide-line">
            {topHomeTasks(tasks).map((task) => (
              <li key={`${task.tripId}-${task.kind}`}>
                <TaskRow task={task} />
              </li>
            ))}
          </ul>
        )}
        {!loading && !activity.loading && !error && !activity.error && tasks.length > 3 && (
          <Link to="/trips" className="dashboard-text-link mt-3">
            See all tasks <ArrowRight size={16} aria-hidden="true" />
          </Link>
        )}
      </section>

      <IdeasSection key={uid ?? 'anonymous'} uid={uid ?? null} trips={trips} />

      <TripList
        title="Your trips"
        trips={activeTrips.slice(0, 3)}
        uid={uid}
        loading={loading}
        error={error ? tripLoadError(error.code) : null}
        empty="Your next adventure starts here."
        action={
          <Link to="/trips" className="dashboard-text-link dashboard-text-link--small">
            Planned <ArrowRight size={14} aria-hidden="true" />
          </Link>
        }
      />
      <p className="text-center text-sm text-muted">
        <Link to="/trips/history" className="font-semibold text-lagoon">
          View trip history
        </Link>
      </p>
    </div>
  )
}

function NextTripCard({ trip, today }: { trip: WithId<Trip>; today: string }) {
  const isUnderway = trip.startDate <= today && trip.endDate >= today
  const days = Math.max(
    0,
    Math.round(
      (new Date(`${trip.startDate}T12:00:00`).getTime() - new Date(`${today}T12:00:00`).getTime()) /
        86_400_000,
    ),
  )
  const countdown = isUnderway
    ? 'Happening now'
    : days === 1
      ? 'Starts tomorrow'
      : `Starts in ${days} days`

  return (
    <section>
      <SectionHeading title="Next trip" />
      <FeaturedHighlight className="dashboard-next-trip">
        <div className="dashboard-next-trip__content">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="dashboard-overline">{trip.name}</p>
              <h2 className="mt-1 truncate text-2xl font-bold tracking-tight">
                {trip.destination.name}
              </h2>
            </div>
            <span className="dashboard-trip-icon" aria-hidden="true">
              <MapPin size={21} />
            </span>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted">
            <span className="inline-flex items-center gap-1.5">
              <CalendarDays size={16} aria-hidden="true" />
              {formatDateRange(trip.startDate, trip.endDate)}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <UsersRound size={16} aria-hidden="true" />
              {trip.memberUids.length} {trip.memberUids.length === 1 ? 'traveler' : 'travelers'}
            </span>
          </div>
          <div className="mt-4 flex items-center justify-between gap-3">
            <StatusBadge tone="warm" className="dashboard-countdown">
              <Clock3 size={14} aria-hidden="true" />
              {countdown}
            </StatusBadge>
            <ActionLink
              to={`/trips/${trip.id}`}
              variant="outline"
              className="dashboard-open-trip min-h-11 px-4"
            >
              Open trip <ArrowRight size={16} aria-hidden="true" />
            </ActionLink>
          </div>
        </div>
      </FeaturedHighlight>
    </section>
  )
}

function TaskLoading() {
  return (
    <div className="list-surface divide-y divide-line" aria-label="Loading trip actions">
      {[0, 1].map((row) => (
        <div key={row} className="flex min-h-[4.5rem] items-center gap-3 px-4 py-3">
          <span className="size-10 animate-pulse rounded-2xl bg-line/70" />
          <span className="flex-1 space-y-2">
            <span className="block h-3 w-2/5 animate-pulse rounded bg-line/70" />
            <span className="block h-3 w-4/5 animate-pulse rounded bg-line/60" />
          </span>
        </div>
      ))}
    </div>
  )
}

function AllCaughtUp() {
  return (
    <SurfaceCard className="dashboard-caught-up flex items-center gap-3 p-4">
      <span className="dashboard-caught-up__icon" aria-hidden="true">
        <CheckCircle2 size={21} />
      </span>
      <div>
        <p className="font-bold">You’re all caught up</p>
        <p className="mt-0.5 text-sm text-muted">Your squad has no open actions for you.</p>
      </div>
    </SurfaceCard>
  )
}

function TaskRow({ task }: { task: HomeTask }) {
  const Icon = {
    payment: CircleDollarSign,
    split: CircleDollarSign,
    vote: Vote,
    preferences: SlidersHorizontal,
  }[task.kind]
  return (
    <Link to={task.to} className="list-row dashboard-task-row">
      <span className={`dashboard-task-icon dashboard-task-icon--${task.kind}`}>
        <Icon size={19} aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-semibold text-ink">{task.title}</span>
        <span className="mt-0.5 block text-sm leading-snug text-muted">
          {task.deadline == null
            ? task.detail
            : `${task.detail} · closes ${formatDateTime(new Date(task.deadline))}`}
        </span>
      </span>
      <ChevronRight size={19} className="shrink-0 text-muted" aria-hidden="true" />
    </Link>
  )
}

function IdeasSection({ uid, trips }: { uid: string | null; trips: WithId<Trip>[] }) {
  const navigate = useNavigate()
  const [result, setResult] = useState<HomeIdeasResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [adding, setAdding] = useState<string | null>(null)
  const [addedToPlan, setAddedToPlan] = useState<Record<string, string>>({})
  const [pickerIdea, setPickerIdea] = useState<HomeIdea | null>(null)
  const [addError, setAddError] = useState<string | null>(null)
  const gatheringTrips = useMemo(() => trips.filter((trip) => trip.status === 'gathering'), [trips])

  useEffect(() => {
    if (!uid) return
    let cancelled = false
    let timer: number | undefined
    let attempts = 0
    const load = async () => {
      try {
        const next = await api<HomeIdeasResponse>('/v1/home/ideas', { cache: 'no-store' })
        if (cancelled) return
        setResult(next)
        if (next.state === 'generating' && attempts < 8) {
          attempts += 1
          timer = window.setTimeout(load, 1500)
        } else if (next.state === 'generating') {
          setError('Ideas are taking longer than usual. Reopen Home to check again.')
        } else if (next.state === 'failed') {
          setError('Ideas could not be loaded today. Please try again tomorrow.')
        }
      } catch (err) {
        if (!cancelled)
          setError(
            errorMessage(err, 'Ideas could not be loaded. Check your connection and try again.'),
          )
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [uid])

  async function addIdea(idea: HomeIdea, trip: WithId<Trip>) {
    setAdding(`${idea.placeId}:${trip.id}`)
    setAddError(null)
    try {
      await api<PlaceAdded>(`/v1/trips/${trip.id}/places`, {
        body: { placeId: idea.placeId },
      })
      setAddedToPlan((current) => ({ ...current, [idea.placeId]: trip.destination.name }))
      setPickerIdea(null)
    } catch (err) {
      setAddError(errorMessage(err, "Couldn't add this place. Please try again."))
    } finally {
      setAdding(null)
    }
  }

  function createNewPlan(idea: HomeIdea) {
    const destination = result?.destination || destinationFromAddress(idea.address, idea.name)
    navigate(`/trips/new?destination=${encodeURIComponent(destination)}`, {
      state: { homeIdeaToAdd: { placeId: idea.placeId } },
    })
    setPickerIdea(null)
  }

  const ideas = result?.ideas ?? []
  const sectionTitle = 'Ideas for your plan'

  return (
    <section>
      <SectionHeading
        title={sectionTitle}
        action={
          result?.tripId ? (
            <Link
              to={`/trips/${result.tripId}/places`}
              className="dashboard-text-link dashboard-text-link--small"
            >
              All places <ArrowRight size={14} aria-hidden="true" />
            </Link>
          ) : (
            <span className="dashboard-section-sparkle" aria-hidden="true">
              <Sparkles size={17} />
            </span>
          )
        }
      />
      {(loading && !result) || (result?.state === 'generating' && !error) ? (
        <CarouselLoading />
      ) : error ? (
        <p role="alert" className="dashboard-inline-error">
          {error}
        </p>
      ) : ideas.length === 0 ? (
        <SurfaceCard className="dashboard-ideas-empty flex items-start gap-3 p-4">
          <span className="dashboard-caught-up__icon" aria-hidden="true">
            <MapPinned size={20} />
          </span>
          <div>
            <p className="font-bold">No ideas found today</p>
            <p className="mt-1 text-sm text-muted">
              {result?.destination
                ? `We couldn't find new places near ${result.destination}. Check back tomorrow for a fresh set.`
                : 'Check back tomorrow for a fresh set of places to explore.'}
            </p>
          </div>
        </SurfaceCard>
      ) : (
        <>
          <p className="mb-2 text-xs text-muted">
            {result?.destination
              ? `Fresh ideas near ${result.destination} · updates daily`
              : 'Popular places across Southeast Asia · updates daily'}
          </p>
          <ul className="dashboard-carousel" aria-label={sectionTitle}>
            {ideas.map((idea) => {
              const addedDestination = addedToPlan[idea.placeId]
              const mapsUrl =
                idea.googleMapsUri ||
                `https://www.google.com/maps/search/?api=1&query_place_id=${encodeURIComponent(idea.placeId)}`
              return (
                <li
                  key={idea.placeId}
                  className="dashboard-carousel__item dashboard-carousel__item--place"
                >
                  <article className="dashboard-idea-card">
                    <LazyPlacePhoto
                      endpoint={`/v1/home/ideas/${encodeURIComponent(idea.placeId)}/photo`}
                      label={idea.name}
                    />
                    <div className="dashboard-idea-card__body">
                      <div className="flex items-center justify-between gap-2">
                        <span className="dashboard-overline">{idea.category || 'Place'}</span>
                        <span className="dashboard-idea-source">
                          {idea.source === 'personal'
                            ? 'Picked for your squad'
                            : result?.destination
                              ? 'Popular nearby'
                              : 'Popular in Southeast Asia'}
                        </span>
                      </div>
                      <a
                        href={mapsUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="dashboard-card-title"
                      >
                        {idea.name}
                      </a>
                      <p className="dashboard-idea-meta">
                        {idea.rating != null && `★ ${idea.rating.toFixed(1)}`}
                        {idea.rating != null && idea.userRatingCount != null && (
                          <span aria-hidden="true"> · </span>
                        )}
                        {idea.userRatingCount != null &&
                          `${idea.userRatingCount.toLocaleString()} Google reviews`}
                      </p>
                      <ActionButton
                        type="button"
                        variant="primary"
                        className="mt-4 min-h-11 w-full"
                        disabled={adding !== null}
                        onClick={() => {
                          setAddError(null)
                          setPickerIdea(idea)
                        }}
                      >
                        <Plus size={17} aria-hidden="true" /> Add to Plan
                      </ActionButton>
                      {addedDestination && (
                        <p role="status" className="mt-2 text-xs text-lagoon-dark">
                          Added to {addedDestination}
                        </p>
                      )}
                    </div>
                  </article>
                </li>
              )
            })}
          </ul>
        </>
      )}
      <p className="dashboard-carousel-hint">Swipe to explore</p>

      <BottomSheet
        open={pickerIdea !== null}
        title="Add to a plan"
        description={pickerIdea ? `Choose where to add ${pickerIdea.name}.` : undefined}
        onClose={() => {
          setPickerIdea(null)
          setAddError(null)
        }}
        className="home-plan-picker"
      >
        {gatheringTrips.length > 0 ? (
          <>
            <p className="mb-2 text-xs font-bold uppercase tracking-[0.1em] text-muted">
              Collecting Places
            </p>
            <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line">
              {gatheringTrips.map((trip) => (
                <li key={trip.id}>
                  <button
                    type="button"
                    className="list-row w-full border-0 bg-transparent text-left focus-visible:outline-2 focus-visible:outline-lagoon disabled:opacity-60"
                    disabled={adding !== null}
                    onClick={() => pickerIdea && void addIdea(pickerIdea, trip)}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-semibold text-ink">{trip.name}</span>
                      <span className="mt-0.5 block truncate text-sm text-muted">
                        {trip.destination.name} · {formatDateRange(trip.startDate, trip.endDate)}
                      </span>
                    </span>
                    <span className="shrink-0 text-sm font-semibold text-lagoon">
                      {adding === `${pickerIdea?.placeId}:${trip.id}` ? 'Adding…' : 'Add'}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="mb-3 rounded-2xl bg-paper p-3 text-sm text-muted">
            You don’t have a plan collecting places yet.
          </p>
        )}
        <ErrorText>{addError}</ErrorText>
        <ActionButton
          type="button"
          variant="outline"
          className="mt-3 w-full"
          onClick={() => pickerIdea && createNewPlan(pickerIdea)}
        >
          <Plus size={17} aria-hidden="true" /> Create a new plan
        </ActionButton>
      </BottomSheet>
    </section>
  )
}

function CarouselLoading() {
  return (
    <div className="dashboard-carousel" aria-label="Loading trip ideas">
      {[0, 1].map((index) => (
        <div key={index} className="dashboard-carousel__item dashboard-idea-card overflow-hidden">
          <div className="dashboard-photo__fallback h-40 animate-pulse" />
          <div className="space-y-2 p-4">
            <div className="h-3 w-1/3 animate-pulse rounded bg-line/70" />
            <div className="h-5 w-2/3 animate-pulse rounded bg-line/70" />
            <div className="h-3 w-full animate-pulse rounded bg-line/50" />
          </div>
        </div>
      ))}
    </div>
  )
}

function tripLoadError(code: string | undefined): string {
  if (code === 'permission-denied') {
    return 'Trip access was denied. Check that you are signed in and a member of the trip.'
  }
  return 'Trips could not be loaded. Check your connection and try again.'
}
