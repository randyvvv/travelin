import { collection, doc, limit, orderBy, query, updateDoc, writeBatch } from 'firebase/firestore'
import { useMemo } from 'react'
import { useNavigate } from 'react-router'
import { CheckCheck } from 'lucide-react'
import { ActionButton, PageHeading } from '../components/ui'
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
      <div className="flex items-end justify-between gap-3">
        <PageHeading title="Notifications" />
        {unread.length > 0 && (
          <ActionButton
            type="button"
            variant="tertiary"
            onClick={markAllRead}
            className="min-h-10 shrink-0 px-2 text-xs"
          >
            <CheckCheck size={16} aria-hidden="true" />
            Mark all as read
          </ActionButton>
        )}
      </div>

      {loading ? (
        <div className="h-20 animate-pulse rounded-2xl bg-line/60" />
      ) : notifications.length === 0 ? (
        <p className="text-muted">
          Nothing yet. You'll hear here when friends join, voting closes, and bills come in.
        </p>
      ) : (
        <ul className="list-surface divide-y divide-line overflow-hidden">
          {notifications.map((notification) => (
            <li key={notification.id}>
              <button
                type="button"
                onClick={() => open(notification)}
                className="list-row w-full items-start"
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
