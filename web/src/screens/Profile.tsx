import { useState } from 'react'
import { useAuth } from '../app/auth-context'
import { Avatar } from '../components/Avatar'
import { ErrorText } from '../components/ErrorText'
import { buttonClass } from '../components/styles'

export function Profile() {
  const { user, signOut } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function logout() {
    setBusy(true)
    setError(null)
    try {
      await signOut()
    } catch {
      setError("Couldn't sign out. Please try again.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6 py-2">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Profile</h1>
      </header>

      <section className="flex items-center gap-3 rounded-2xl border border-line bg-card p-4">
        <Avatar name={user?.displayName ?? 'Traveler'} photoURL={user?.photoURL ?? undefined} />
        <div className="min-w-0">
          <p className="truncate font-semibold">{user?.displayName || 'Traveler'}</p>
          {user?.email && <p className="truncate text-sm text-muted">{user.email}</p>}
        </div>
      </section>

      <section className="space-y-3">
        <ErrorText>{error}</ErrorText>
        <button
          type="button"
          onClick={logout}
          disabled={busy}
          className={`${buttonClass('outline')} w-full`}
        >
          {busy ? 'Signing out…' : 'Sign out'}
        </button>
      </section>
    </div>
  )
}
