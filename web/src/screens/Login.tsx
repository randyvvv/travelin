import { FirebaseError } from 'firebase/app'
import { useState } from 'react'
import { Navigate, useSearchParams } from 'react-router'
import { useAuth } from '../app/auth-context'
import { LoginGlobe } from '../components/LoginGlobe'
import { ActionButton } from '../components/ui'

/** Only same-origin paths; anything else falls back to Home. */
function GoogleMark() {
  return (
    <span className="grid size-6 place-items-center">
      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
        <path
          fill="#4285F4"
          d="M23.49 12.27c0-.79-.07-1.54-.2-2.27H12v4.3h6.46a5.52 5.52 0 0 1-2.4 3.62v3h3.88c2.27-2.09 3.55-5.17 3.55-8.65Z"
        />
        <path
          fill="#34A853"
          d="M12 24c3.24 0 5.96-1.07 7.95-2.91l-3.88-3c-1.08.72-2.47 1.14-4.07 1.14-3.13 0-5.78-2.11-6.73-4.96H1.27v3.09A12 12 0 0 0 12 24Z"
        />
        <path
          fill="#FBBC05"
          d="M5.27 14.27A7.2 7.2 0 0 1 4.9 12c0-.79.14-1.55.37-2.27V6.64H1.27A12 12 0 0 0 0 12c0 1.94.46 3.77 1.27 5.36l4-3.09Z"
        />
        <path
          fill="#EA4335"
          d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.44-3.44C17.95 1.14 15.24 0 12 0 7.31 0 3.26 2.69 1.27 6.64l4 3.09C6.22 6.86 8.87 4.75 12 4.75Z"
        />
      </svg>
    </span>
  )
}

function safeNext(value: string | null): string {
  return value && value.startsWith('/') && !value.startsWith('//') ? value : '/'
}

export function Login() {
  const { user, signIn } = useAuth()
  const [params] = useSearchParams()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (user) return <Navigate to={safeNext(params.get('next'))} replace />

  async function handleSignIn() {
    setBusy(true)
    setError(null)
    try {
      await signIn()
    } catch (err) {
      if (!(err instanceof FirebaseError && err.code === 'auth/popup-closed-by-user')) {
        setError("Couldn't sign you in. Please try again.")
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="relative isolate mx-auto flex h-dvh min-h-dvh max-w-md flex-col overflow-hidden px-6 pt-[max(env(safe-area-inset-top),2.5rem)] pb-[max(env(safe-area-inset-bottom),2.5rem)]">
      <LoginGlobe />

      <div className="relative z-10 flex items-center gap-2 text-lg font-extrabold tracking-tight">
        <img src="/travelin%20icon.png" alt="" className="size-9" />
        Travelin
      </div>

      <div className="relative z-10 mt-14">
        <h1 className="text-4xl leading-tight font-extrabold tracking-tight">
          Plan the trip your squad actually agrees on.
        </h1>
        <p className="mt-4 text-lg text-muted">
          Collect places from Reels or search, vote together, get a day-by-day itinerary, and split
          the bill — without the group-chat chaos.
        </p>
      </div>

      <div className="relative z-10 mt-auto">
        <ActionButton
          type="button"
          onClick={handleSignIn}
          disabled={busy}
          variant="dark"
          className="w-full"
        >
          <GoogleMark />
          {busy ? 'Signing in…' : 'Continue with Google'}
        </ActionButton>
        {error && (
          <p role="alert" className="mt-3 text-center text-sm text-red-700">
            {error}
          </p>
        )}
      </div>
    </main>
  )
}
