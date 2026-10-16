import { useMemo } from 'react'
import { useOutletContext } from 'react-router'
import type { Member, Trip, WithId } from '../lib/types'
import { useAuth } from './auth-context'

export interface TripContext {
  trip: WithId<Trip>
  members: WithId<Member>[]
}

/** The live trip loaded by <TripLayout>. Only valid inside /trips/:tripId routes. */
export function useTrip(): WithId<Trip> {
  return useOutletContext<TripContext>().trip
}

/** Live squad of the current trip, plus the signed-in user's own member doc. */
export function useSquad() {
  const { members } = useOutletContext<TripContext>()
  const { user } = useAuth()
  return useMemo(
    () => ({
      members,
      byId: new Map(members.map((member) => [member.id, member])),
      me: members.find((member) => member.id === user?.uid) ?? null,
    }),
    [members, user],
  )
}
