// Security rules tests. Run from the repo root:
//   npx firebase-tools emulators:exec --only firestore,storage --project demo-travelin \
//     "cd firebase && npm test"
import {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} from '@firebase/rules-unit-testing'
import { addDoc, collection, doc, getDoc, setDoc, updateDoc } from 'firebase/firestore'
import { ref, uploadBytes } from 'firebase/storage'
import { readFileSync } from 'node:fs'
import { after, before, beforeEach, describe, it } from 'node:test'

const TRIP = 'trip-1'
const video = new Uint8Array([0, 0, 0, 24, 102, 116, 121, 112])

let env

before(async () => {
  env = await initializeTestEnvironment({
    projectId: 'demo-travelin',
    firestore: { rules: readFileSync(new URL('../firestore.rules', import.meta.url), 'utf8') },
    storage: { rules: readFileSync(new URL('../storage.rules', import.meta.url), 'utf8') },
  })
})

after(() => env.cleanup())

beforeEach(async () => {
  await env.clearFirestore()
  await env.withSecurityRulesDisabled(async (context) => {
    const db = context.firestore()
    await setDoc(doc(db, 'trips', TRIP), {
      name: 'Jogja',
      hostUid: 'hana',
      memberUids: ['hana', 'raka'],
      status: 'gathering',
    })
    const member = { role: 'member', prefs: {}, prefsDone: false, votes: {}, votesSubmittedAt: null }
    await setDoc(doc(db, `trips/${TRIP}/members/hana`), { ...member, role: 'host' })
    await setDoc(doc(db, `trips/${TRIP}/members/raka`), member)
    await setDoc(doc(db, `trips/${TRIP}/places/p1`), { name: 'Taman Sari' })
    await setDoc(doc(db, 'users/raka/notifications/n1'), { text: 'Hi', read: false })
  })
})

const as = (uid) => env.authenticatedContext(uid).firestore()
const storageAs = (uid) => env.authenticatedContext(uid).storage()

describe('trips', () => {
  it('members can read their trip; others cannot', async () => {
    await assertSucceeds(getDoc(doc(as('raka'), 'trips', TRIP)))
    await assertFails(getDoc(doc(as('mallory'), 'trips', TRIP)))
    await assertFails(getDoc(doc(env.unauthenticatedContext().firestore(), 'trips', TRIP)))
  })

  it('clients cannot write trip documents', async () => {
    await assertFails(updateDoc(doc(as('hana'), 'trips', TRIP), { status: 'settled' }))
    await assertFails(
      updateDoc(doc(as('mallory'), 'trips', TRIP), { memberUids: ['hana', 'raka', 'mallory'] }),
    )
  })

  it('server-owned collections are read-only for members', async () => {
    await assertSucceeds(getDoc(doc(as('raka'), `trips/${TRIP}/places/p1`)))
    await assertFails(setDoc(doc(as('raka'), `trips/${TRIP}/places/p2`), { name: 'Fake' }))
    await assertFails(
      setDoc(doc(as('raka'), `trips/${TRIP}/transfers/t1`), { from: 'hana', amountIdr: 1 }),
    )
    await assertFails(getDoc(doc(as('mallory'), `trips/${TRIP}/places/p1`)))
  })
})

describe('members', () => {
  it('a member can save their own preferences', async () => {
    await assertSucceeds(
      updateDoc(doc(as('raka'), `trips/${TRIP}/members/raka`), {
        prefs: { budgetIdr: 2000000, interests: ['Nature'], dietary: ['Halal'], skip: [] },
        prefsDone: true,
      }),
    )
  })

  it("a member cannot edit someone else's doc or their own role", async () => {
    await assertFails(updateDoc(doc(as('raka'), `trips/${TRIP}/members/hana`), { prefsDone: true }))
    await assertFails(updateDoc(doc(as('raka'), `trips/${TRIP}/members/raka`), { role: 'host' }))
  })

  it('votes are editable until submitted', async () => {
    const raka = doc(as('raka'), `trips/${TRIP}/members/raka`)
    await assertSucceeds(updateDoc(raka, { votes: { p1: 'must' } }))
    await env.withSecurityRulesDisabled((context) =>
      updateDoc(doc(context.firestore(), `trips/${TRIP}/members/raka`), {
        votesSubmittedAt: new Date(),
      }),
    )
    await assertFails(updateDoc(raka, { votes: { p1: 'skip' } }))
    await assertSucceeds(updateDoc(raka, { prefsDone: true }))
  })
})

describe('reels', () => {
  const reels = (uid) => collection(as(uid), `trips/${TRIP}/reels`)

  it('a member can add a queued upload or a link-only reel as themselves', async () => {
    await assertSucceeds(
      addDoc(reels('raka'), { uploaderUid: 'raka', source: 'upload', status: 'queued' }),
    )
    await assertSucceeds(
      addDoc(reels('raka'), { uploaderUid: 'raka', source: 'link', status: 'link_only' }),
    )
  })

  it('rejects reels for someone else, with a server status, or from non-members', async () => {
    await assertFails(addDoc(reels('raka'), { uploaderUid: 'hana', status: 'queued' }))
    await assertFails(addDoc(reels('raka'), { uploaderUid: 'raka', status: 'done' }))
    await assertFails(addDoc(reels('mallory'), { uploaderUid: 'mallory', status: 'queued' }))
  })
})

describe('users and notifications', () => {
  it('users manage only their own profile', async () => {
    await assertSucceeds(setDoc(doc(as('raka'), 'users/raka'), { displayName: 'Raka' }))
    await assertFails(setDoc(doc(as('raka'), 'users/hana'), { displayName: 'Hana' }))
  })

  it('users can only mark their own notifications as read', async () => {
    const own = doc(as('raka'), 'users/raka/notifications/n1')
    await assertSucceeds(updateDoc(own, { read: true }))
    await assertFails(updateDoc(own, { text: 'Edited' }))
    await assertFails(getDoc(doc(as('hana'), 'users/raka/notifications/n1')))
    await assertFails(addDoc(collection(as('raka'), 'users/raka/notifications'), { text: 'x' }))
  })
})

describe('storage', () => {
  const upload = (uid, path, contentType) =>
    uploadBytes(ref(storageAs(uid), path), video, { contentType })

  it('members upload videos to their own reel folder', async () => {
    await assertSucceeds(upload('raka', `trips/${TRIP}/reels/raka/r1.mp4`, 'video/mp4'))
  })

  it('rejects other folders, non-members, and non-video files', async () => {
    await assertFails(upload('raka', `trips/${TRIP}/reels/hana/r1.mp4`, 'video/mp4'))
    await assertFails(upload('mallory', `trips/${TRIP}/reels/mallory/r1.mp4`, 'video/mp4'))
    await assertFails(upload('raka', `trips/${TRIP}/reels/raka/r1.png`, 'image/png'))
    await assertFails(upload('raka', 'samples/reels/r1.mp4', 'video/mp4'))
  })

  it('receipts must be images', async () => {
    await assertSucceeds(upload('raka', `trips/${TRIP}/receipts/raka/a.jpg`, 'image/jpeg'))
    await assertFails(upload('raka', `trips/${TRIP}/receipts/raka/a.mp4`, 'video/mp4'))
  })
})
