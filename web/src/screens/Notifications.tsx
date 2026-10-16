import { collection, doc, limit, orderBy, query, updateDoc, writeBatch } from 'firebase/firestore'
import { useMemo } from 'react'
import { useNavigate } from 'react-router'
import { useAuth } from '../app/auth-context'
import { db } from '../lib/firebase'
import { formatRelative } from '../lib/format'
import { useCollection } from '../lib/hooks/useCollection'
import type { AppNotification, WithId } from '../lib/types'

export function Notifications() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const notificationsQuery = useMemo(
    () =>
      user
        ? query(
            collection(db, 'users', user.uid, 'notifications'),
            orderBy('createdAt', 'desc'),
            limit(50),
          )
        : null,
    [user],
  )
  const { data: notifications, loading } = useCollection<AppNotification>(notificationsQuery)
  const unread = notifications.filter((notification) => !notification.read)

  function open(notification: WithId<AppNotification>) {
    if (user && !notification.read) {
      void updateDoc(doc(db, 'users', user.uid, 'notifications', notification.id), { read: true })
    }
    navigate(notification.link)
  }

  async function markAllRead() {
    if (!user) return
    const batch = writeBatch(db)
    for (const notification of unread) {
      batch.update(doc(db, 'users', user.uid, 'notifications', notification.id), { read: true })
    }
    await batch.commit()
  }

  return (
    <div className="space-y-4 py-2">
      <header className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-extrabold tracking-tight">Notifications</h1>
        {unread.length > 0 && (
          <button type="button" onClick={markAllRead} className="text-sm font-semibold text-lagoon">
            Mark all as read
          </button>
        )}
      </header>

      {loading ? (
        <div className="h-20 animate-pulse rounded-2xl bg-line/60" />
      ) : notifications.length === 0 ? (
        <p className="text-muted">
          Nothing yet. You'll hear here when friends join, voting closes, and bills come in.
        </p>
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-card">
          {notifications.map((notification) => (
            <li key={notification.id}>
              <button
                type="button"
                onClick={() => open(notification)}
                className="flex w-full items-start gap-3 p-4 text-left hover:bg-paper"
              >
                <span
                  aria-hidden
                  className={`mt-2 size-2 shrink-0 rounded-full ${notification.read ? 'bg-transparent' : 'bg-sunset'}`}
                />
                <span className="min-w-0 flex-1">
                  <span className={`block ${notification.read ? '' : 'font-semibold'}`}>
                    {notification.text}
                    {!notification.read && <span className="sr-only"> (unread)</span>}
                  </span>
                  {notification.createdAt && (
                    <span className="text-sm text-muted">
                      {formatRelative(notification.createdAt.toDate())}
                    </span>
                  )}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
