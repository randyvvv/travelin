const idr = new Intl.NumberFormat('id-ID', {
  style: 'currency',
  currency: 'IDR',
  maximumFractionDigits: 0,
})

export function formatIdr(amount: number): string {
  return idr.format(amount)
}

const shortDate = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' })

/** "24 Oct – 26 Oct" from ISO dates (YYYY-MM-DD). */
export function formatDateRange(start: string, end: string): string {
  return `${shortDate.format(new Date(start))} – ${shortDate.format(new Date(end))}`
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
