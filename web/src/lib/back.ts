const ROOTS = new Set(['/', '/trips', '/trips/history', '/profile'])

/** Where the back button on a sub-route should go. Null on the four tab roots. */
export function backHref(pathname: string): string | null {
  if (ROOTS.has(pathname)) return null

  const trip = pathname.match(/^\/trips\/([^/]+)(?:\/(.*))?$/)
  if (trip && trip[1] !== 'new' && trip[1] !== 'history') {
    const hub = `/trips/${trip[1]}`
    const rest = trip[2]
    if (!rest) return '/trips'
    const [section, child] = rest.split('/')
    if (child) {
      if (section === 'booking') return `${hub}/itinerary`
      if (section === 'places' || section === 'split') return `${hub}/${section}`
    }
    return hub
  }

  return '/'
}

/** Accessible name for the back control on this path. */
export function backLabel(pathname: string): string {
  const href = backHref(pathname)
  if (href === '/trips') return 'Back to planned trips'
  if (href?.endsWith('/places')) return 'Back to places'
  if (href?.endsWith('/split')) return 'Back to split bill'
  if (href?.endsWith('/itinerary')) return 'Back to itinerary'
  if (href?.match(/^\/trips\/[^/]+$/)) return 'Back to trip'
  return 'Back'
}
