import { collection, doc, onSnapshot } from 'firebase/firestore'
import { useEffect, useMemo, useState } from 'react'
import { db } from '../firebase'
import type { Member, Transfer, Trip, WithId } from '../types'

interface ActivitySnapshot {
  key: string
  members: Record<string, WithId<Member> | null | undefined>
  transfers: Record<string, WithId<Transfer>[] | undefined>
  errors: string[]
}

/** Live member and settlement data used to build the signed-in member's Home tasks. */
export function useHomeActivity(trips: WithId<Trip>[], uid: string | undefined) {
  const active = useMemo(() => trips.filter((trip) => trip.status !== 'settled'), [trips])
  const key = useMemo(
    () =>
      `${uid ?? ''}|${active
        .map((trip) => `${trip.id}:${trip.status}`)
        .sort()
        .join(',')}`,
    [active, uid],
  )
  const [snapshot, setSnapshot] = useState<ActivitySnapshot>({
    key: '',
    members: {},
    transfers: {},
    errors: [],
  })

  useEffect(() => {
    if (!uid) return
    const unsubscribers = active.map((trip) => {
      const memberRef = doc(db, 'trips', trip.id, 'members', uid)
      const stopMember = onSnapshot(
        memberRef,
        (memberSnapshot) => {
          setSnapshot((current) => {
            const base: ActivitySnapshot =
              current.key === key ? current : { key, members: {}, transfers: {}, errors: [] }
            return {
              ...base,
              members: {
                ...base.members,
                [trip.id]: memberSnapshot.exists()
                  ? ({ id: memberSnapshot.id, ...memberSnapshot.data() } as WithId<Member>)
                  : null,
              },
            }
          })
        },
        (error) =>
          setSnapshot((current) => {
            const base: ActivitySnapshot =
              current.key === key ? current : { key, members: {}, transfers: {}, errors: [] }
            return {
              ...base,
              members: { ...base.members, [trip.id]: null },
              errors: [...base.errors, error.code],
            }
          }),
      )

      if (trip.status !== 'settling') return stopMember
      const stopTransfers = onSnapshot(
        collection(db, 'trips', trip.id, 'transfers'),
        (transferSnapshot) =>
          setSnapshot((current) => {
            const base: ActivitySnapshot =
              current.key === key ? current : { key, members: {}, transfers: {}, errors: [] }
            return {
              ...base,
              transfers: {
                ...base.transfers,
                [trip.id]: transferSnapshot.docs.map(
                  (transfer) => ({ id: transfer.id, ...transfer.data() }) as WithId<Transfer>,
                ),
              },
            }
          }),
        (error) =>
          setSnapshot((current) => {
            const base: ActivitySnapshot =
              current.key === key ? current : { key, members: {}, transfers: {}, errors: [] }
            return {
              ...base,
              transfers: { ...base.transfers, [trip.id]: [] },
              errors: [...base.errors, error.code],
            }
          }),
      )
      return () => {
        stopMember()
        stopTransfers()
      }
    })

    return () => unsubscribers.forEach((unsubscribe) => unsubscribe())
  }, [active, key, uid])

  const ready =
    active.length === 0 ||
    (snapshot.key === key &&
      active.every(
        (trip) =>
          snapshot.members[trip.id] !== undefined &&
          (trip.status !== 'settling' || snapshot.transfers[trip.id] !== undefined),
      ))

  return {
    members: snapshot.key === key ? snapshot.members : {},
    transfers: snapshot.key === key ? snapshot.transfers : {},
    loading: Boolean(uid) && !ready,
    error: snapshot.key === key ? snapshot.errors[0] : undefined,
  }
}
