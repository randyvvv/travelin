import { useState } from 'react'
import { useAuth } from '../app/auth-context'
import { Avatar } from '../components/Avatar'
import { ErrorText } from '../components/ErrorText'
import { ActionButton, PageHeading, SurfaceCard } from '../components/ui'

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
      <PageHeading title="Profile" />

      <SurfaceCard className="flex items-center gap-3 p-4">
        <Avatar name={user?.displayName ?? 'Traveler'} photoURL={user?.photoURL ?? undefined} />
        <div className="min-w-0">
          <p className="truncate font-semibold">{user?.displayName || 'Traveler'}</p>
          {user?.email && <p className="truncate text-sm text-muted">{user.email}</p>}
        </div>
      </SurfaceCard>

      <section className="space-y-3">
        <ErrorText>{error}</ErrorText>
        <ActionButton
          type="button"
          onClick={logout}
          disabled={busy}
          variant="outline"
          className="w-full"
        >
          {busy ? 'Signing out…' : 'Sign out'}
        </ActionButton>
      </section>
    </div>
  )
}
