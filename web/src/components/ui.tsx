import {
  useEffect,
  useId,
  useRef,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type ReactNode,
} from 'react'
import { Link, type LinkProps } from 'react-router'
import { X } from 'lucide-react'
import { buttonClass, cardClass, iconButtonClass, type ButtonVariant } from './styles'

export function PageHeading({
  title,
  description,
  eyebrow,
  className = '',
}: {
  title: ReactNode
  description?: ReactNode
  eyebrow?: ReactNode
  className?: string
}) {
  return (
    <header className={`space-y-1 ${className}`}>
      {eyebrow && (
        <p className="text-xs font-bold tracking-[0.12em] text-lagoon uppercase">{eyebrow}</p>
      )}
      <h1 className="page-title">{title}</h1>
      {description && <p className="page-description">{description}</p>}
    </header>
  )
}

export function SectionHeading({
  title,
  action,
  className = '',
}: {
  title: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div className={`mb-3 flex items-center justify-between gap-3 ${className}`}>
      <h2 className="section-title">{title}</h2>
      {action}
    </div>
  )
}

export function SurfaceCard({ children, className = '', ...props }: HTMLAttributes<HTMLElement>) {
  return (
    <section className={`${cardClass} ${className}`} {...props}>
      {children}
    </section>
  )
}

export function StatusBadge({
  children,
  tone = 'neutral',
  className = '',
}: {
  children: ReactNode
  tone?: 'neutral' | 'brand' | 'warm' | 'success' | 'danger'
  className?: string
}) {
  const toneClass = {
    neutral: 'bg-paper text-muted',
    brand: 'bg-lagoon/10 text-lagoon-dark',
    warm: 'bg-sunset/25 text-ink',
    success: 'bg-lagoon/15 text-lagoon-dark',
    danger: 'bg-red-100 text-red-800',
  }[tone]

  return (
    <span
      className={`inline-flex min-h-7 items-center rounded-full px-3 py-1 text-xs font-bold ${toneClass} ${className}`}
    >
      {children}
    </span>
  )
}

export function ActionButton({
  variant = 'primary',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return <button className={`${buttonClass(variant)} ${className}`} {...props} />
}

export function ActionLink({
  variant = 'primary',
  className = '',
  ...props
}: LinkProps & { variant?: ButtonVariant; className?: string }) {
  return <Link className={`${buttonClass(variant)} ${className}`} {...props} />
}

export function IconButton({
  label,
  children,
  className = '',
  type = 'button',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; children: ReactNode }) {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      className={`${iconButtonClass} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}

export function IconLink({
  label,
  children,
  className = '',
  ...props
}: LinkProps & { label: string; children: ReactNode; className?: string }) {
  return (
    <Link aria-label={label} title={label} className={`${iconButtonClass} ${className}`} {...props}>
      {children}
    </Link>
  )
}

export function ListRow({
  to,
  title,
  subtitle,
  leading,
  trailing,
  className = '',
}: {
  to: string
  title: ReactNode
  subtitle?: ReactNode
  leading?: ReactNode
  trailing?: ReactNode
  className?: string
}) {
  return (
    <Link to={to} className={`list-row ${className}`}>
      {leading}
      <span className="min-w-0 flex-1">
        <span className="block truncate font-semibold text-ink">{title}</span>
        {subtitle && <span className="mt-0.5 block truncate text-sm text-muted">{subtitle}</span>}
      </span>
      {trailing}
    </Link>
  )
}

export function BottomSheet({
  open,
  title,
  description,
  onClose,
  children,
  className = '',
}: {
  open: boolean
  title: ReactNode
  description?: ReactNode
  onClose: () => void
  children: ReactNode
  className?: string
}) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const descriptionId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return

    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  if (!open) return null

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      className="bottom-sheet-dialog"
      onCancel={(event) => {
        event.preventDefault()
        onClose()
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <section className={`bottom-sheet ${className}`}>
        <div className="bottom-sheet-handle" aria-hidden="true" />
        <header className="mb-5 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 id={titleId} className="text-xl font-bold tracking-tight">
              {title}
            </h2>
            {description && (
              <p id={descriptionId} className="mt-2 text-sm leading-relaxed text-muted">
                {description}
              </p>
            )}
          </div>
          <IconButton label="Close" onClick={onClose} className="-mr-2 -mt-2">
            <X size={20} aria-hidden="true" />
          </IconButton>
        </header>
        {children}
      </section>
    </dialog>
  )
}
