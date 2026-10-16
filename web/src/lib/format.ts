const idr = new Intl.NumberFormat('id-ID', {
  style: 'currency',
  currency: 'IDR',
  maximumFractionDigits: 0,
})

export function formatIdr(amount: number): string {
  return idr.format(amount)
}

/** Reads YYYY-MM-DD as a local calendar date (plain `new Date(iso)` would use UTC). */
function localDate(isoDate: string): Date {
  return new Date(`${isoDate}T00:00:00`)
}

const shortDate = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' })

/** "24 Oct – 26 Oct" from ISO dates (YYYY-MM-DD). */
export function formatDateRange(start: string, end: string): string {
  return `${shortDate.format(localDate(start))} – ${shortDate.format(localDate(end))}`
}

const dayLabel = new Intl.DateTimeFormat('en-GB', {
  weekday: 'short',
  day: 'numeric',
  month: 'short',
})

/** "Sat 24 Oct" from an ISO date (YYYY-MM-DD). */
export function formatDay(isoDate: string): string {
  return dayLabel.format(localDate(isoDate)).replace(',', '')
}

const dateTime = new Intl.DateTimeFormat('en-GB', {
  weekday: 'short',
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

/** "Sat 24 Oct, 20:00" in the viewer's time zone. */
export function formatDateTime(date: Date): string {
  return dateTime.format(date)
}

const relative = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
const steps: [Intl.RelativeTimeFormatUnit, number][] = [
  ['second', 60],
  ['minute', 60],
  ['hour', 24],
  ['day', 7],
  ['week', 4.35],
  ['month', 12],
  ['year', Infinity],
]

/** "5 minutes ago", "yesterday". */
export function formatRelative(date: Date, now = new Date()): string {
  let value = (date.getTime() - now.getTime()) / 1000
  for (const [unit, size] of steps) {
    if (Math.abs(value) < size) return relative.format(Math.round(value), unit)
    value /= size
  }
  return relative.format(Math.round(value), 'year')
}
