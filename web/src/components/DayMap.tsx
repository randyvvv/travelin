import {
  AdvancedMarker,
  APIProvider,
  Map,
  Pin,
  useMap,
  useMapsLibrary,
} from '@vis.gl/react-google-maps'
import { Maximize2, Minimize2, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import type { LatLng } from '../lib/types'
import { IconButton } from './ui'

const apiKey = import.meta.env.VITE_MAPS_API_KEY
const mapId = import.meta.env.VITE_MAPS_MAP_ID
// Keeps a single stop from zooming in to street level.
const BOUNDS_PADDING_DEG = 0.01
const PIN_MS = 250
const SEGMENT_MS = 450
const CURVE_SAMPLES = 24
const CURVE_BEND = 0.2
const SINGLE_STOP_ZOOM = 16
const CAMERA_PADDING_INLINE = 48
const CAMERA_PADDING_FULL = 64

export interface MapPoint extends LatLng {
  key: string
  title: string
  subtitle?: string
  href?: string
}

/** One day's stops as numbered pins joined in visiting order. */
export function DayMap({ points }: { points: MapPoint[] }) {
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    if (!expanded) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setExpanded(false)
    }
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = previous
      window.removeEventListener('keydown', onKey)
    }
  }, [expanded])

  if (!apiKey || points.length === 0) return null

  return (
    <APIProvider apiKey={apiKey}>
      {expanded ? (
        <div className="day-map-overlay fixed inset-0 z-50 bg-card">
          <MapCanvas points={points} expanded onCollapse={() => setExpanded(false)} />
        </div>
      ) : (
        <MapCanvas points={points} onExpand={() => setExpanded(true)} />
      )}
    </APIProvider>
  )
}

function MapCanvas({
  points,
  expanded = false,
  onExpand,
  onCollapse,
}: {
  points: MapPoint[]
  expanded?: boolean
  onExpand?: () => void
  onCollapse?: () => void
}) {
  const pointKey = points.map((point) => point.key).join()
  const [activeKey, setActiveKey] = useState<string | null>(null)
  const [visibleCount, setVisibleCount] = useState(() =>
    prefersReducedMotion() ? points.length : 0,
  )
  const [seenPointKey, setSeenPointKey] = useState(pointKey)
  const ignoreMapClick = useRef(false)
  if (pointKey !== seenPointKey) {
    setSeenPointKey(pointKey)
    setActiveKey(null)
    setVisibleCount(prefersReducedMotion() ? points.length : 0)
  }
  const activeIndex = points.findIndex((point) => point.key === activeKey)
  const active = activeIndex >= 0 ? points[activeIndex] : undefined
  const [info, setInfo] = useState<{ point: MapPoint; index: number } | null>(null)
  const [infoOpen, setInfoOpen] = useState(false)
  const insetTop = expanded ? 'top-[max(env(safe-area-inset-top),0.75rem)]' : 'top-3'
  const cameraPadding = expanded ? CAMERA_PADDING_FULL : CAMERA_PADDING_INLINE

  useEffect(() => {
    if (active && activeIndex >= 0) {
      setInfo({ point: active, index: activeIndex })
      setInfoOpen(true)
      return
    }
    setInfoOpen(false)
  }, [active, activeIndex])

  function selectPoint(key: string) {
    ignoreMapClick.current = true
    setActiveKey(key)
  }

  return (
    <div className={expanded ? 'relative h-full w-full' : 'relative'}>
      <Map
        key={`${expanded ? 'full' : 'card'}-${points.map((point) => point.key).join()}`}
        defaultCenter={points[0]}
        defaultZoom={SINGLE_STOP_ZOOM}
        mapId={mapId || undefined}
        gestureHandling={expanded ? 'greedy' : 'cooperative'}
        disableDefaultUI
        clickableIcons={false}
        className={
          expanded ? 'h-full w-full' : 'h-64 w-full overflow-hidden rounded-2xl border border-line'
        }
        onClick={() => {
          if (ignoreMapClick.current) {
            ignoreMapClick.current = false
            return
          }
          setActiveKey(null)
        }}
      >
        <RouteAnimator points={points} padding={cameraPadding} onVisibleCount={setVisibleCount} />
        {points.map((point, index) =>
          index < visibleCount ? (
            <AdvancedMarker
              key={point.key}
              position={point}
              title={point.title}
              onClick={() => selectPoint(point.key)}
            >
              <div className="day-map-marker">
                <Pin
                  background="#0E7C74"
                  borderColor="#0A5E58"
                  glyphColor="#FFFFFF"
                  glyphText={String(index + 1)}
                />
              </div>
            </AdvancedMarker>
          ) : null,
        )}
      </Map>

      {expanded && onCollapse && (
        <IconButton
          label="Close map"
          onClick={onCollapse}
          className={`absolute left-3 z-10 ${insetTop} bg-card shadow-sm`}
        >
          <Minimize2 size={18} strokeWidth={2} aria-hidden="true" />
        </IconButton>
      )}

      {!expanded && onExpand && !info && (
        <IconButton
          label="Expand map"
          onClick={onExpand}
          className={`absolute right-3 z-10 ${insetTop} bg-card shadow-sm`}
        >
          <Maximize2 size={18} strokeWidth={2} aria-hidden="true" />
        </IconButton>
      )}

      {info && (
        <aside
          className={`day-map-info absolute right-3 z-10 max-w-[70%] p-3 ${insetTop} ${
            infoOpen ? 'day-map-info--in' : 'day-map-info--out'
          }`}
          onAnimationEnd={(event) => {
            if (event.target !== event.currentTarget || infoOpen) return
            setInfo(null)
          }}
        >
          <div className="flex items-start gap-2">
            <span
              aria-hidden
              className="grid size-7 shrink-0 place-items-center rounded-full bg-lagoon text-sm font-bold text-white"
            >
              {info.index + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-bold leading-tight">{info.point.title}</p>
              {info.point.subtitle && (
                <p className="mt-1 text-sm text-muted">{info.point.subtitle}</p>
              )}
              {info.point.href && (
                <Link
                  to={info.point.href}
                  relative="path"
                  className="mt-2 inline-block text-sm font-semibold text-lagoon"
                >
                  View place
                </Link>
              )}
            </div>
            <IconButton
              label="Close"
              onClick={() => setActiveKey(null)}
              className="-mr-1 -mt-1 size-8"
            >
              <X size={16} aria-hidden="true" />
            </IconButton>
          </div>
        </aside>
      )}
    </div>
  )
}

function RouteAnimator({
  points,
  padding,
  onVisibleCount,
}: {
  points: MapPoint[]
  padding: number
  onVisibleCount: (count: number) => void
}) {
  const map = useMap()
  const maps = useMapsLibrary('maps')

  useEffect(() => {
    if (!map || !maps || points.length === 0) return

    const mapInstance = map
    const mapsLib = maps
    const lines: google.maps.Polyline[] = []
    const listeners: google.maps.MapsEventListener[] = []
    let frame = 0
    let delay = 0
    let cancelled = false

    function frameTo(visible: MapPoint[], clampSingle = false) {
      const listener = fitVisible(mapInstance, visible, padding, clampSingle)
      if (listener) listeners.push(listener)
    }

    function drawLine(path: google.maps.LatLngLiteral[]) {
      const line = new mapsLib.Polyline({
        path,
        strokeColor: '#0E7C74',
        strokeOpacity: 0.85,
        strokeWeight: 3,
        icons: [
          {
            icon: {
              path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
              scale: 1.5,
              strokeColor: '#0E7C74',
              fillColor: '#0E7C74',
              fillOpacity: 1,
            },
            offset: '100%',
          },
        ],
        map: mapInstance,
      })
      lines.push(line)
      return line
    }

    const segments = points
      .slice(0, -1)
      .map((point, index) => curvePath(point, points[index + 1], index % 2 === 0 ? 1 : -1))

    if (prefersReducedMotion() || points.length === 1) {
      onVisibleCount(points.length)
      for (const path of segments) drawLine(path)
      frameTo(points, points.length === 1)
      return () => {
        listeners.forEach((listener) => listener.remove())
        lines.forEach((line) => line.setMap(null))
      }
    }

    onVisibleCount(1)
    frameTo(points.slice(0, 1), true)
    if (segments.length === 0) {
      return () => {
        listeners.forEach((listener) => listener.remove())
        lines.forEach((line) => line.setMap(null))
      }
    }

    let segment = 0
    let started = 0
    let current = drawLine([])

    function startHop() {
      frameTo(points.slice(0, segment + 2))
      frame = requestAnimationFrame(tick)
    }

    function tick(now: number) {
      if (cancelled) return
      if (!started) started = now
      const t = Math.min(1, (now - started) / SEGMENT_MS)
      const eased = 1 - (1 - t) ** 2
      const count = Math.max(1, Math.round(eased * segments[segment].length))
      current.setPath(segments[segment].slice(0, count))
      if (t < 1) {
        frame = requestAnimationFrame(tick)
        return
      }
      onVisibleCount(segment + 2)
      segment += 1
      if (segment >= segments.length) {
        frameTo(points)
        return
      }
      current = drawLine([])
      started = 0
      delay = window.setTimeout(startHop, PIN_MS)
    }

    delay = window.setTimeout(startHop, PIN_MS)

    return () => {
      cancelled = true
      window.clearTimeout(delay)
      cancelAnimationFrame(frame)
      listeners.forEach((listener) => listener.remove())
      lines.forEach((line) => line.setMap(null))
    }
  }, [map, maps, onVisibleCount, padding, points])

  return null
}

function mapBounds(points: MapPoint[]) {
  const lats = points.map((point) => point.lat)
  const lngs = points.map((point) => point.lng)
  return {
    north: Math.max(...lats) + BOUNDS_PADDING_DEG,
    south: Math.min(...lats) - BOUNDS_PADDING_DEG,
    east: Math.max(...lngs) + BOUNDS_PADDING_DEG,
    west: Math.min(...lngs) - BOUNDS_PADDING_DEG,
  }
}

function fitVisible(
  map: google.maps.Map,
  points: MapPoint[],
  padding: number,
  clampSingle = false,
) {
  if (points.length === 0) return
  const box = mapBounds(points)
  map.fitBounds({ north: box.north, south: box.south, east: box.east, west: box.west }, padding)
  if (!clampSingle || points.length !== 1) return
  const listener = map.addListener('idle', () => {
    listener.remove()
    const zoom = map.getZoom()
    if (zoom != null && zoom > SINGLE_STOP_ZOOM) map.setZoom(SINGLE_STOP_ZOOM)
  })
  return listener
}

/** Quadratic Bezier from a to b, bent sideways so the hop isn't a straight line. */
function curvePath(from: LatLng, to: LatLng, bend: number): google.maps.LatLngLiteral[] {
  const midLat = (from.lat + to.lat) / 2
  const midLng = (from.lng + to.lng) / 2
  const dLat = to.lat - from.lat
  const dLng = to.lng - from.lng
  const control = {
    lat: midLat + -dLng * CURVE_BEND * bend,
    lng: midLng + dLat * CURVE_BEND * bend,
  }
  const path: google.maps.LatLngLiteral[] = []
  for (let i = 0; i <= CURVE_SAMPLES; i++) {
    const t = i / CURVE_SAMPLES
    const u = 1 - t
    path.push({
      lat: u * u * from.lat + 2 * u * t * control.lat + t * t * to.lat,
      lng: u * u * from.lng + 2 * u * t * control.lng + t * t * to.lng,
    })
  }
  return path
}

function prefersReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}
