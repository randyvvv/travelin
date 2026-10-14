import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { Splash } from '../components/Splash'
import { useAuth } from './auth-context'

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return <Splash />
  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }
  return children
}
