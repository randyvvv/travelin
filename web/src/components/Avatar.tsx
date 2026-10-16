export function Avatar({ name, photoURL }: { name: string; photoURL?: string }) {
  if (photoURL) {
    return (
      <img
        src={photoURL}
        alt=""
        referrerPolicy="no-referrer"
        className="size-10 shrink-0 rounded-full bg-line object-cover"
      />
    )
  }
  const initials = name
    .split(/\s+/)
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
  return (
    <span
      aria-hidden
      className="grid size-10 shrink-0 place-items-center rounded-full bg-lagoon/15 text-sm font-bold text-lagoon-dark"
    >
      {initials}
    </span>
  )
}
