import { Link } from 'react-router'
import { useTrip } from '../../app/trip-context'
import { ChevronRightIcon } from '../../components/icons'
import { formatDateRange } from '../../lib/format'
import { tripStatusLabel } from '../../lib/status'

const sections = [
  { to: 'reels', label: 'Reels', hint: 'The Reels your squad saved' },
  { to: 'prefs', label: 'My preferences', hint: 'Budget, interests, food, things to skip' },
  { to: 'places', label: 'Places & vote', hint: 'Verified places from your Reels' },
  { to: 'itinerary', label: 'Itinerary', hint: 'Day-by-day plan and why' },
  { to: 'split', label: 'Split bill', hint: 'Expenses and who owes whom' },
  { to: 'pay', label: 'Payments', hint: 'Pay and confirm transfers' },
]

export function TripHub() {
  const trip = useTrip()

  return (
    <div className="space-y-6 py-2">
      <section>
        <h1 className="text-2xl font-extrabold tracking-tight">{trip.destination.name}</h1>
        <p className="text-muted">
          {formatDateRange(trip.startDate, trip.endDate)} · from {trip.origin}
        </p>
        <span className="mt-3 inline-block rounded-full bg-lagoon/10 px-3 py-1 text-sm font-semibold text-lagoon-dark">
          {tripStatusLabel[trip.status]}
        </span>
      </section>

      <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-card">
        {sections.map((section) => (
          <li key={section.to}>
            <Link to={section.to} className="flex items-center gap-3 p-4 hover:bg-paper">
              <div className="flex-1">
                <p className="font-semibold">{section.label}</p>
                <p className="text-sm text-muted">{section.hint}</p>
              </div>
              <ChevronRightIcon className="text-muted" />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
