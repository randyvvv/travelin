export type ButtonVariant = 'primary' | 'dark' | 'outline'

const buttonVariants: Record<ButtonVariant, string> = {
  primary: 'bg-lagoon text-white hover:bg-lagoon-dark',
  dark: 'bg-ink text-paper hover:bg-ink/90',
  outline: 'border border-line bg-card text-ink hover:border-lagoon',
}

/** Classes for a button, or a Link that should look like one. */
export function buttonClass(variant: ButtonVariant = 'primary'): string {
  return `inline-flex h-12 items-center justify-center gap-2 rounded-full px-5 font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lagoon disabled:cursor-not-allowed disabled:opacity-60 ${buttonVariants[variant]}`
}

export const inputClass =
  'h-12 w-full rounded-xl border border-line bg-card px-4 text-base text-ink placeholder:text-muted/70 focus:border-lagoon focus:outline-2 focus:outline-lagoon/30'

export function chipClass(selected: boolean): string {
  return `inline-flex min-h-10 items-center rounded-full border px-4 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-lagoon ${
    selected
      ? 'border-lagoon bg-lagoon text-white'
      : 'border-line bg-card text-ink hover:border-lagoon'
  }`
}
