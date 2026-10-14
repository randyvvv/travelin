import { FirebaseError } from 'firebase/app'
import {
  onAuthStateChanged,
  signInWithPopup,
  signInWithRedirect,
  signOut,
  type User,
} from 'firebase/auth'
import { doc, setDoc } from 'firebase/firestore'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { auth, db, googleProvider } from '../lib/firebase'
import { AuthContext, type AuthState } from './auth-context'

// Installed PWAs and some mobile browsers can't open popups.
const POPUP_UNAVAILABLE = ['auth/popup-blocked', 'auth/operation-not-supported-in-this-environment']

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(
    () =>
      onAuthStateChanged(auth, (next) => {
        setUser(next)
        setLoading(false)
        if (next) {
          void setDoc(
            doc(db, 'users', next.uid),
            {
              displayName: next.displayName ?? '',
              email: next.email ?? '',
              photoURL: next.photoURL ?? '',
            },
            { merge: true },
          )
        }
      }),
    [],
  )

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      signIn: async () => {
        try {
          await signInWithPopup(auth, googleProvider)
        } catch (error) {
          if (error instanceof FirebaseError && POPUP_UNAVAILABLE.includes(error.code)) {
            await signInWithRedirect(auth, googleProvider)
            return
          }
          throw error
        }
      },
      signOut: () => signOut(auth),
    }),
    [user, loading],
  )

  return <AuthContext value={value}>{children}</AuthContext>
}
