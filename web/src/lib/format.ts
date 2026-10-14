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
