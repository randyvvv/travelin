import { ActionLink, PageHeading } from '../components/ui'

export function NotFound() {
  return (
    <main className="mx-auto grid min-h-dvh max-w-md place-items-center px-6 text-center">
      <div>
        <PageHeading title="Page not found" />
        <ActionLink to="/" className="mt-4 w-full">
          Back to home
        </ActionLink>
      </div>
    </main>
  )
}
