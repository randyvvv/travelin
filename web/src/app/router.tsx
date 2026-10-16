import { createBrowserRouter } from 'react-router'
import { CreateTrip } from '../screens/CreateTrip'
import { Home } from '../screens/Home'
import { Join } from '../screens/Join'
import { Login } from '../screens/Login'
import { NotFound } from '../screens/NotFound'
import { Notifications } from '../screens/Notifications'
import { Profile } from '../screens/Profile'
import { PlannedTrips, TripHistory } from '../screens/TripLists'
import { Booking } from '../screens/trip/Booking'
import { ExpenseEditor } from '../screens/trip/ExpenseEditor'
import { Itinerary } from '../screens/trip/Itinerary'
import { Pay } from '../screens/trip/Pay'
import { PlaceDetail } from '../screens/trip/PlaceDetail'
import { Places } from '../screens/trip/Places'
import { Preferences } from '../screens/trip/Preferences'
import { Reels } from '../screens/trip/Reels'
import { Split } from '../screens/trip/Split'
import { TripHub } from '../screens/trip/TripHub'
import { AppLayout } from './AppLayout'
import { RequireAuth } from './RequireAuth'
import { TripLayout } from './TripLayout'

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  {
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Home /> },
      { path: 'notifications', element: <Notifications /> },
      { path: 'profile', element: <Profile /> },
      { path: 'trips/history', element: <TripHistory /> },
      { path: 'trips', element: <PlannedTrips /> },
      { path: 'join/:inviteCode', element: <Join /> },
      { path: 'trips/new', element: <CreateTrip /> },
      {
        path: 'trips/:tripId',
        element: <TripLayout />,
        children: [
          { index: true, element: <TripHub /> },
          { path: 'reels', element: <Reels /> },
          { path: 'prefs', element: <Preferences /> },
          { path: 'places', element: <Places /> },
          { path: 'places/:placeId', element: <PlaceDetail /> },
          { path: 'itinerary', element: <Itinerary /> },
          { path: 'booking/:bookingId', element: <Booking /> },
          { path: 'split', element: <Split /> },
          { path: 'split/:expenseId', element: <ExpenseEditor /> },
          { path: 'pay', element: <Pay /> },
        ],
      },
    ],
  },
  { path: '*', element: <NotFound /> },
])
