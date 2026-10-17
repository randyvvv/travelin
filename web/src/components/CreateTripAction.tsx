import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { Plane, Plus } from 'lucide-react'
import { useNavigate } from 'react-router'
import { ActionButton, ActionLink } from './ui'

export function CreateTripAction({
  className = '',
  label = 'Create a trip',
  showPlus = true,
  compact = false,
  onActivate,
}: {
  className?: string
  label?: string
  showPlus?: boolean
  compact?: boolean
  onActivate?: () => void
}) {
  const navigate = useNavigate()
  const [launching, setLaunching] = useState(false)
  const launchTimer = useRef<number | null>(null)
  const actionClass = `create-trip-cta${compact ? ' create-trip-cta--compact' : ''}${launching ? ' create-trip-cta--launching' : ''}`

  function handleClick(event: ReactMouseEvent<HTMLAnchorElement | HTMLButtonElement>) {
    const modifiedClick =
      event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    if (event.defaultPrevented || modifiedClick || (!onActivate && reduceMotion)) return

    event.preventDefault()
    if (launchTimer.current !== null) return

    if (reduceMotion) {
      onActivate?.()
      return
    }

    setLaunching(true)
    launchTimer.current = window.setTimeout(() => {
      launchTimer.current = null
      if (onActivate) onActivate()
      else navigate('/trips/new')
    }, 760)
  }

  useEffect(
    () => () => {
      if (launchTimer.current !== null) window.clearTimeout(launchTimer.current)
    },
    [],
  )

  const contents = (
    <>
      {showPlus && (
        <span className="create-trip-cta__icon" aria-hidden="true">
          <Plus size={21} strokeWidth={2.2} />
        </span>
      )}
      <span className="create-trip-cta__copy">
        <span className="create-trip-cta__label">{label}</span>
      </span>
      <Plane
        className="create-trip-cta__plane"
        fill="currentColor"
        strokeWidth={0}
        aria-hidden="true"
      />
    </>
  )

  return (
    <div className={`create-trip-cta-wrap ${className}`}>
      {onActivate ? (
        <ActionButton
          type="button"
          variant="outline"
          className={actionClass}
          aria-disabled={launching}
          onClick={handleClick}
        >
          {contents}
        </ActionButton>
      ) : (
        <ActionLink
          to="/trips/new"
          variant="outline"
          className={actionClass}
          aria-disabled={launching}
          onClick={handleClick}
        >
          {contents}
        </ActionLink>
      )}
    </div>
  )
}
