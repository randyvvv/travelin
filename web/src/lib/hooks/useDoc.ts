import { onSnapshot, type DocumentReference } from 'firebase/firestore'
import { useEffect, useState } from 'react'
import type { WithId } from '../types'

interface Snapshot<T> {
  path: string | null
  data: WithId<T> | null
  error: Error | null
}

/**
 * Live Firestore document. Pass `null` to wait. Re-subscribes only when the
 * document path changes, so callers can rebuild the ref on every render.
 */
export function useDoc<T>(ref: DocumentReference | null) {
  const path = ref?.path ?? null
  const [snapshot, setSnapshot] = useState<Snapshot<T>>({ path: null, data: null, error: null })

  useEffect(() => {
    if (!ref) return
    return onSnapshot(
      ref,
      (snap) =>
        setSnapshot({
          path: ref.path,
          data: snap.exists() ? { id: snap.id, ...(snap.data() as T) } : null,
          error: null,
        }),
      (error) => setSnapshot({ path: ref.path, data: null, error }),
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed by path on purpose
  }, [path])

  const loading = path !== null && snapshot.path !== path
  return {
    data: loading ? null : snapshot.data,
    error: loading ? null : snapshot.error,
    loading,
  }
}
