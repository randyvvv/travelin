import { Link } from 'react-router'

export function NotFound() {
  return (
    <main className="mx-auto grid min-h-dvh max-w-md place-items-center px-6 text-center">
      <div>
        <h1 className="text-2xl font-extrabold">Page not found</h1>
        <Link to="/" className="mt-4 inline-block font-semibold text-lagoon">
          Back to home
        </Link>
      </div>
    </main>
  )
}
