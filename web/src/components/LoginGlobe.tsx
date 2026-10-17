import createGlobe from 'cobe'
import { useEffect, useRef } from 'react'

const LAGOON: [number, number, number] = [0.055, 0.486, 0.455]
const PAPER: [number, number, number] = [0.984, 0.969, 0.949]
const INK: [number, number, number] = [0.106, 0.106, 0.122]

const CITIES = [
  { id: 'indonesia', name: 'Indonesia', location: [-6.2088, 106.8456] as [number, number] },
  { id: 'japan', name: 'Japan', location: [35.6762, 139.6503] as [number, number] },
  { id: 'australia', name: 'Australia', location: [-33.8688, 151.2093] as [number, number] },
  { id: 'uae', name: 'UAE', location: [25.2048, 55.2708] as [number, number] },
  { id: 'kenya', name: 'Kenya', location: [-1.2921, 36.8219] as [number, number] },
  { id: 'southafrica', name: 'South Africa', location: [-33.9249, 18.4241] as [number, number] },
  { id: 'france', name: 'France', location: [48.8566, 2.3522] as [number, number] },
  { id: 'usa', name: 'USA', location: [40.7128, -74.006] as [number, number] },
  { id: 'brazil', name: 'Brazil', location: [-23.5505, -46.6333] as [number, number] },
  { id: 'peru', name: 'Peru', location: [-12.0464, -77.0428] as [number, number] },
] as const

type CityId = (typeof CITIES)[number]['id']

const byId = Object.fromEntries(CITIES.map((city) => [city.id, city.location])) as Record<
  CityId,
  [number, number]
>

/** One long-haul line per country, each on a different continent. */
const ROUTES = [
  ['indonesia', 'france'],
  ['japan', 'southafrica'],
  ['australia', 'brazil'],
  ['uae', 'peru'],
  ['kenya', 'usa'],
] as const satisfies ReadonlyArray<[CityId, CityId]>

/** Start facing Southeast Asia. */
const START_PHI = 2.85
const START_THETA = 0.25
const SPIN_SPEED = 0.0007
const DRAG_SPEED = 0.005

export function LoginGlobe() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const labelRefs = useRef<Record<string, HTMLSpanElement | null>>({})

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const surface = canvas

    const size = Math.min(window.innerWidth * 1.4, 28 * 16)
    surface.style.width = `${size}px`
    surface.style.height = `${size}px`

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let phi = START_PHI
    let theta = START_THETA
    let dragging = false
    let lastX = 0
    let lastY = 0

    const globe = createGlobe(surface, {
      devicePixelRatio: 2,
      width: size * 2,
      height: size * 2,
      phi,
      theta,
      dark: 0,
      diffuse: 3,
      mapSamples: 31000,
      mapBrightness: 1.5,
      mapBaseBrightness: 0,
      scale: 1,
      baseColor: LAGOON,
      markerColor: INK,
      glowColor: PAPER,
      markers: CITIES.map((city) => ({
        id: city.id,
        location: [...city.location] as [number, number],
        size: 0.04,
        color: INK,
      })),
      arcs: ROUTES.map(([from, to]) => ({
        from: [...byId[from]] as [number, number],
        to: [...byId[to]] as [number, number],
        color: INK,
      })),
      arcColor: INK,
      arcWidth: 1.2,
      arcHeight: 0.5,
      markerElevation: 0.03,
    })

    function syncLabels() {
      const root = getComputedStyle(document.documentElement)
      for (const city of CITIES) {
        const label = labelRefs.current[city.id]
        if (!label) continue
        const visible = root.getPropertyValue(`--cobe-visible-${city.id}`).trim()
        label.dataset.visible = visible ? 'true' : 'false'
      }
    }

    let frame = 0
    function tick() {
      if (!dragging && !reduceMotion) phi += SPIN_SPEED
      globe.update({ phi, theta })
      syncLabels()
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)

    function onPointerDown(event: PointerEvent) {
      dragging = true
      lastX = event.clientX
      lastY = event.clientY
      surface.setPointerCapture(event.pointerId)
      surface.classList.add('login-globe--dragging')
    }

    function onPointerMove(event: PointerEvent) {
      if (!dragging) return
      phi += (event.clientX - lastX) * DRAG_SPEED
      theta = Math.min(0.8, Math.max(-0.6, theta + (event.clientY - lastY) * DRAG_SPEED))
      lastX = event.clientX
      lastY = event.clientY
    }

    function onPointerUp(event: PointerEvent) {
      dragging = false
      surface.releasePointerCapture(event.pointerId)
      surface.classList.remove('login-globe--dragging')
    }

    surface.addEventListener('pointerdown', onPointerDown)
    surface.addEventListener('pointermove', onPointerMove)
    surface.addEventListener('pointerup', onPointerUp)
    surface.addEventListener('pointercancel', onPointerUp)

    return () => {
      cancelAnimationFrame(frame)
      surface.removeEventListener('pointerdown', onPointerDown)
      surface.removeEventListener('pointermove', onPointerMove)
      surface.removeEventListener('pointerup', onPointerUp)
      surface.removeEventListener('pointercancel', onPointerUp)
      globe.destroy()
    }
  }, [])

  return (
    <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden" aria-hidden="true">
      <div className="login-globe-stage absolute -right-16 -bottom-24 size-[min(140vw,28rem)]">
        <canvas ref={canvasRef} className="login-globe pointer-events-auto size-full" />
        {CITIES.map((city) => (
          <span
            key={city.id}
            ref={(node) => {
              labelRefs.current[city.id] = node
            }}
            className="login-globe-label"
            style={{ positionAnchor: `--cobe-${city.id}` }}
            data-visible="false"
          >
            <span className="login-globe-label__name">{city.name}</span>
            <span className="login-globe-label__stem" />
          </span>
        ))}
      </div>
    </div>
  )
}
