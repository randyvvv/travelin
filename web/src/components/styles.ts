export type ButtonVariant = 'primary' | 'dark' | 'outline' | 'tertiary'

const buttonVariants: Record<ButtonVariant, string> = {
  primary: 'border border-lagoon bg-lagoon text-white shadow-sm hover:bg-lagoon-dark',
  dark: 'border border-ink bg-ink text-paper shadow-sm hover:bg-ink/90',
  outline: 'border border-line bg-card text-ink hover:border-lagoon hover:bg-paper',
  tertiary: 'border border-transparent bg-transparent text-lagoon hover:bg-lagoon/10',
}

/** Classes for a button, or a Link that should look like one. */
export function buttonClass(variant: ButtonVariant = 'primary'): string {
  return `inline-flex min-h-13 items-center justify-center gap-2 rounded-xl px-5 text-sm font-semibold transition duration-150 active:translate-y-px focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lagoon disabled:cursor-not-allowed disabled:opacity-55 ${buttonVariants[variant]}`
}

export const inputClass =
  'h-13 w-full rounded-xl border border-line bg-card px-4 text-base text-ink shadow-sm shadow-ink/5 placeholder:text-muted/70 transition focus:border-lagoon focus:outline-2 focus:outline-lagoon/25'

export function chipClass(selected: boolean): string {
  return `inline-flex min-h-10 items-center rounded-full border px-4 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-lagoon ${
    selected
      ? 'border-lagoon bg-lagoon text-white'
      : 'border-line bg-card text-ink hover:border-lagoon hover:bg-paper'
  }`
}

export const iconButtonClass =
  'grid size-11 shrink-0 place-items-center rounded-full text-ink transition hover:bg-line/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lagoon'

export const cardClass = 'rounded-2xl border border-line bg-card shadow-sm shadow-ink/5'
