import { useEffect, useRef, useState } from 'react'
import { ArrowUpRight } from 'lucide-react'
import { api, type PlacePhoto } from '../lib/api'

/** Requests transient Google photo URLs only after this card enters the viewport. */
export function LazyPlacePhoto({ endpoint, label }: { endpoint: string; label: string }) {
  const container = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)
  const [photoState, setPhotoState] = useState<{
    endpoint: string
    photo: PlacePhoto | null
  } | null>(null)
  const [failedUri, setFailedUri] = useState<string | null>(null)

  useEffect(() => {
    const element = container.current
    if (!element) return
    if (!('IntersectionObserver' in window)) {
      const frame = requestAnimationFrame(() => setVisible(true))
      return () => cancelAnimationFrame(frame)
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true)
          observer.disconnect()
        }
      },
      { rootMargin: '0px' },
    )
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!visible) return
    let current = true
    void api<PlacePhoto | null>(endpoint, { cache: 'no-store' })
      .then((result) => {
        if (current) setPhotoState({ endpoint, photo: result })
      })
      .catch(() => {
        if (current) setPhotoState({ endpoint, photo: null })
      })
    return () => {
      current = false
    }
  }, [endpoint, visible])

  const photo = photoState?.endpoint === endpoint ? photoState.photo : null

  return (
    <div ref={container} className="dashboard-photo" role="group" aria-label={`${label} photo`}>
      {photo?.photoUri && failedUri !== photo.photoUri ? (
        <img
          src={photo.photoUri}
          alt=""
          loading="lazy"
          className="dashboard-photo__image"
          onError={() => setFailedUri(photo.photoUri)}
        />
      ) : (
        <div className="dashboard-photo__fallback" aria-hidden="true" />
      )}
      {photo && (
        <div className="dashboard-photo__credits">
          <span className="dashboard-photo__attribution">
            {photo.photoUri &&
              photo.authorAttributions.map((attribution, index) => (
                <span
                  key={`${attribution.displayName}-${index}`}
                  className="dashboard-photo__author"
                >
                  {attribution.photoUri && <img src={attribution.photoUri} alt="" loading="lazy" />}
                  {attribution.uri ? (
                    <a href={attribution.uri} target="_blank" rel="noreferrer">
                      {attribution.displayName}
                    </a>
                  ) : (
                    <span>{attribution.displayName}</span>
                  )}
                </span>
              ))}
          </span>
          {photo.googleMapsUri ? (
            <a
              href={photo.googleMapsUri}
              target="_blank"
              rel="noreferrer"
              className="dashboard-photo__maps"
              translate="no"
            >
              Google Maps <ArrowUpRight size={13} aria-hidden="true" />
            </a>
          ) : (
            photo.photoUri && (
              <span className="dashboard-photo__maps" translate="no">
                Google Maps
              </span>
            )
          )}
        </div>
      )}
    </div>
  )
}
