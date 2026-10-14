import { collection, query, where } from 'firebase/firestore'
import { useMemo } from 'react'
import { Link, Outlet } from 'react-router'
import { BellIcon } from '../components/icons'
import { db } from '../lib/firebase'
import { useCollection } from '../lib/hooks/useCollection'
import type { AppNotification } from '../lib/types'
import { useAuth } from './auth-context'

export function AppLayout() {
  const { user } = useAuth()
  const unreadQuery = useMemo(
    () =>
      user
        ? query(collection(db, 'users', user.uid, 'notifications'), where('read', '==', false))
        : null,
    [user],
  )
  const { data: unread } = useCollection<AppNotification>(unreadQuery)

  return (
    <div className="mx-auto flex min-h-dvh max-w-md flex-col">
      <header className="flex items-center justify-between px-4 pt-[max(env(safe-area-inset-top),1rem)] pb-3">
        <Link to="/" className="flex items-center gap-2 text-lg font-extrabold tracking-tight">
          <img src="/logo.svg" alt="" className="size-8" />
          Travelin
        </Link>
        <Link
          to="/notifications"
          aria-label={`Notifications, ${unread.length} unread`}
          className="relative grid size-11 place-items-center rounded-full hover:bg-line/60"
        >
          <BellIcon />
          {unread.length > 0 && (
            <span className="absolute top-1 right-1 min-w-5 rounded-full bg-sunset px-1 text-center text-xs font-bold text-ink">
              {unread.length}
            </span>
          )}
        </Link>
      </header>
      <main className="flex-1 px-4 pb-[max(env(safe-area-inset-bottom),1.5rem)]">
        <Outlet />
      </main>
    </div>
  )
}
