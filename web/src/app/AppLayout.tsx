import { collection, query, where } from 'firebase/firestore'
import { Bell, CalendarDays, Clock3, House, UserRound } from 'lucide-react'
import { useMemo } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router'
import { BackBar, IconLink } from '../components/ui'
import { backHref, backLabel } from '../lib/back'
import { db } from '../lib/firebase'
import { useCollection } from '../lib/hooks/useCollection'
import type { AppNotification } from '../lib/types'
import { useAuth } from './auth-context'

const HEADER_PATHS = new Set(['/', '/trips', '/trips/history', '/profile'])

export function AppLayout() {
  const { user } = useAuth()
  const { pathname } = useLocation()
  const unreadQuery = useMemo(
    () =>
      user
        ? query(collection(db, 'users', user.uid, 'notifications'), where('read', '==', false))
        : null,
    [user],
  )
  const { data: unread } = useCollection<AppNotification>(unreadQuery)
  const plannedActive =
    pathname === '/trips' ||
    pathname === '/trips/new' ||
    (pathname.startsWith('/trips/') && !pathname.startsWith('/trips/history'))
  const showHeader = HEADER_PATHS.has(pathname)
  const backTo = backHref(pathname)
  const tripShell = /^\/trips\/(?!history$|new$)[^/]+/.test(pathname)
  const navLinkClass = (isActive: boolean) =>
    `flex min-h-[4.25rem] flex-col items-center justify-center gap-1 rounded-2xl px-2 text-[0.6875rem] font-semibold transition focus-visible:outline-2 focus-visible:outline-lagoon ${
      isActive ? 'text-lagoon-dark' : 'text-muted hover:bg-paper hover:text-ink'
    }`

  return (
    <div className="relative isolate mx-auto flex min-h-dvh w-full max-w-md flex-col">
      {showHeader && (
        <header className="relative z-10 flex items-center justify-between gap-3 px-5 pt-[max(env(safe-area-inset-top),1rem)] pb-3">
          {pathname === '/' ? (
            <Link
              to="/"
              className="flex min-h-11 items-center gap-2.5 text-lg font-bold tracking-tight"
            >
              <img src="/travelin%20icon.png" alt="" className="size-9" />
              Travelin
            </Link>
          ) : (
            <Link
              to="/"
              className="flex min-h-11 items-center gap-2 text-base font-bold tracking-tight"
            >
              <img src="/travelin%20icon.png" alt="" className="size-8" />
              Travelin
            </Link>
          )}
          <IconLink
            to="/notifications"
            label={`Notifications, ${unread.length} unread`}
            className="relative"
          >
            <Bell size={21} strokeWidth={1.9} aria-hidden="true" />
            {unread.length > 0 && (
              <span className="absolute top-1 right-1 min-w-5 rounded-full bg-sunset px-1 text-center text-[0.6875rem] leading-5 font-bold text-ink ring-2 ring-paper">
                {unread.length}
              </span>
            )}
          </IconLink>
        </header>
      )}
      <main
        className={`relative z-10 flex-1 px-4 pb-[calc(var(--bottom-nav-height)+env(safe-area-inset-bottom)+1rem)] ${
          showHeader ? '' : 'pt-[max(env(safe-area-inset-top),1rem)]'
        }`}
      >
        {backTo && !tripShell && <BackBar to={backTo} label={backLabel(pathname)} />}
        <Outlet />
      </main>
      <nav
        aria-label="Main navigation"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-20"
      >
        <div className="pointer-events-auto mx-auto grid w-full max-w-md grid-cols-4 gap-1 border-t border-line bg-card/95 px-3 pt-1 pb-[max(env(safe-area-inset-bottom),0.25rem)] shadow-[0_-6px_24px_rgba(27,27,31,0.06)] backdrop-blur">
          <NavLink to="/" end className={({ isActive }) => navLinkClass(isActive)}>
            <House size={22} strokeWidth={1.9} aria-hidden="true" />
            <span>Home</span>
          </NavLink>
          <NavLink
            to="/trips"
            end
            className={({ isActive }) => navLinkClass(isActive || plannedActive)}
          >
            <CalendarDays size={21} strokeWidth={1.9} aria-hidden="true" />
            <span>Planned</span>
          </NavLink>
          <NavLink to="/trips/history" end className={({ isActive }) => navLinkClass(isActive)}>
            <Clock3 size={21} strokeWidth={1.9} aria-hidden="true" />
            <span>History</span>
          </NavLink>
          <NavLink to="/profile" end className={({ isActive }) => navLinkClass(isActive)}>
            <UserRound size={21} strokeWidth={1.9} aria-hidden="true" />
            <span>Profile</span>
          </NavLink>
        </div>
      </nav>
    </div>
  )
}
