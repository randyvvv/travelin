import { onSnapshot, type Query } from 'firebase/firestore'
import { useEffect, useState } from 'react'
import type { WithId } from '../types'

interface Snapshot<T> {
  query: Query | null
  data: WithId<T>[]
  error: Error | null
}

/** Live Firestore query. Memoize `query` (useMemo); pass `null` to wait. */
export function useCollection<T>(query: Query | null) {
  const [snapshot, setSnapshot] = useState<Snapshot<T>>({ query: null, data: [], error: null })

  useEffect(() => {
    if (!query) return
    return onSnapshot(
      query,
      (snap) =>
        setSnapshot({
          query,
          data: snap.docs.map((doc) => ({ id: doc.id, ...(doc.data() as T) })),
          error: null,
        }),
      (error) => setSnapshot({ query, data: [], error }),
    )
  }, [query])

  const loading = query !== null && snapshot.query !== query
  return {
    data: loading ? [] : snapshot.data,
    error: loading ? null : snapshot.error,
    loading,
  }
}
