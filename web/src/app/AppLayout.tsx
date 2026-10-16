import { collection, query, where } from 'firebase/firestore'
import { useMemo } from 'react'
import { Link, NavLink, Outlet } from 'react-router'
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
  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `flex min-h-11 items-center justify-center rounded-full px-4 text-sm font-semibold transition ${
      isActive ? 'bg-lagoon/10 text-lagoon-dark' : 'text-muted hover:bg-line/60 hover:text-ink'
    }`

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-md flex-col">
      <header className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-4 pt-[max(env(safe-area-inset-top),1rem)] pb-3">
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
      <main className="flex-1 px-4 pb-[calc(env(safe-area-inset-bottom)+5rem)]">
        <Outlet />
      </main>
      <nav
        aria-label="Main navigation"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-20 px-2"
      >
        <div className="pointer-events-auto mx-auto grid w-full max-w-md grid-cols-4 gap-1 rounded-t-2xl border border-b-0 border-line bg-paper/95 px-2 pt-2 pb-[max(env(safe-area-inset-bottom),0.5rem)] backdrop-blur">
          <NavLink to="/" end className={navLinkClass}>
            Home
          </NavLink>
          <NavLink to="/trips" end className={navLinkClass}>
            Planned
          </NavLink>
          <NavLink to="/trips/history" end className={navLinkClass}>
            History
          </NavLink>
          <NavLink to="/profile" end className={navLinkClass}>
            Profile
          </NavLink>
        </div>
      </nav>
    </div>
  )
}
