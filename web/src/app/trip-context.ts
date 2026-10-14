import { useOutletContext } from 'react-router'
import type { Trip, WithId } from '../lib/types'

export interface TripContext {
  trip: WithId<Trip>
}

/** The live trip loaded by <TripLayout>. Only valid inside /trips/:tripId routes. */
export function useTrip(): WithId<Trip> {
  return useOutletContext<TripContext>().trip
}
