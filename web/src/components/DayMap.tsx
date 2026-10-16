import {
  AdvancedMarker,
  APIProvider,
  Map,
  Pin,
  useMap,
  useMapsLibrary,
} from '@vis.gl/react-google-maps'
import { useEffect } from 'react'
import type { LatLng } from '../lib/types'

const apiKey = import.meta.env.VITE_MAPS_API_KEY
const mapId = import.meta.env.VITE_MAPS_MAP_ID
// Keeps a single stop from zooming in to street level.
const BOUNDS_PADDING_DEG = 0.01

export interface MapPoint extends LatLng {
  key: string
  title: string
}

/** One day's stops as numbered pins joined in visiting order. */
export function DayMap({ points }: { points: MapPoint[] }) {
  if (!apiKey || points.length === 0) return null
  const lats = points.map((point) => point.lat)
  const lngs = points.map((point) => point.lng)
  const bounds = {
    north: Math.max(...lats) + BOUNDS_PADDING_DEG,
    south: Math.min(...lats) - BOUNDS_PADDING_DEG,
    east: Math.max(...lngs) + BOUNDS_PADDING_DEG,
    west: Math.min(...lngs) - BOUNDS_PADDING_DEG,
  }

  return (
    <APIProvider apiKey={apiKey}>
      <Map
        key={points.map((point) => point.key).join()}
        defaultBounds={{ ...bounds, padding: 32 }}
        mapId={mapId || undefined}
        gestureHandling="cooperative"
        disableDefaultUI
        className="h-64 w-full overflow-hidden rounded-2xl border border-line"
      >
        <RouteLine points={points} />
        {points.map((point, index) => (
          <AdvancedMarker key={point.key} position={point} title={point.title}>
            <Pin
              background="#0E7C74"
              borderColor="#0A5E58"
              glyphColor="#FFFFFF"
              glyphText={String(index + 1)}
            />
          </AdvancedMarker>
        ))}
      </Map>
    </APIProvider>
  )
}

function RouteLine({ points }: { points: MapPoint[] }) {
  const map = useMap()
  const maps = useMapsLibrary('maps')

  useEffect(() => {
    if (!map || !maps || points.length < 2) return
    const line = new maps.Polyline({
      path: points.map(({ lat, lng }) => ({ lat, lng })),
      strokeColor: '#0E7C74',
      strokeOpacity: 0.7,
      strokeWeight: 3,
      map,
    })
    return () => line.setMap(null)
  }, [map, maps, points])

  return null
}
