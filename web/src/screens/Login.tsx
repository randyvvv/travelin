import { FirebaseError } from 'firebase/app'
import { ArrowRight } from 'lucide-react'
import { useState } from 'react'
import { Navigate, useSearchParams } from 'react-router'
import { ActionButton } from '../components/ui'
import { useAuth } from '../app/auth-context'

/** Only same-origin paths; anything else falls back to Home. */
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
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-between px-6 pt-[max(env(safe-area-inset-top),2.5rem)] pb-[max(env(safe-area-inset-bottom),2.5rem)]">
      <div className="flex items-center gap-2 text-lg font-extrabold tracking-tight">
        <img src="/travelin%20icon.png" alt="" className="size-9" />
        Travelin
      </div>

      <div>
        <h1 className="text-4xl leading-tight font-extrabold tracking-tight">
          From saved Reels to a trip everyone agrees on.
        </h1>
        <p className="mt-4 text-lg text-muted">
          Drop in the Reels your group keeps sharing. Travelin finds the real places, lets everyone
          vote, plans the days, and splits the bill fairly.
        </p>
      </div>

      <div>
        <ActionButton
          type="button"
          onClick={handleSignIn}
          disabled={busy}
          variant="dark"
          className="w-full"
        >
          {busy ? 'Signing in…' : 'Continue with Google'}
          <ArrowRight size={18} strokeWidth={2} aria-hidden="true" />
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
