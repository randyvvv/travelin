import { collection, query, where } from 'firebase/firestore'
import { useMemo } from 'react'
import { useAuth } from '../../app/auth-context'
import { db } from '../firebase'
import { useCollection } from './useCollection'
import type { Trip } from '../types'

/** Live trips visible to the signed-in member, newest first. */
export function useTrips() {
  const { user } = useAuth()
  const tripsQuery = useMemo(
    () =>
      user ? query(collection(db, 'trips'), where('memberUids', 'array-contains', user.uid)) : null,
    [user],
  )
  const { data, loading, error } = useCollection<Trip>(tripsQuery)
  const trips = useMemo(
    () => [...data].sort((a, b) => (b.createdAt?.toMillis() ?? 0) - (a.createdAt?.toMillis() ?? 0)),
    [data],
  )

  return { trips, loading, error, uid: user?.uid }
}
