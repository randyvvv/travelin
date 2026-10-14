import type { ReactNode } from 'react'

/** Placeholder for a screen that is not built yet. */
export function ScreenStub({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="py-4">
      <h1 className="text-2xl font-extrabold tracking-tight">{title}</h1>
      <p className="mt-2 text-muted">{children}</p>
    </section>
  )
}
