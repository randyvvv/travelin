export function ErrorText({ children }: { children: string | null }) {
  if (!children) return null
  return (
    <p role="alert" className="text-sm font-medium text-red-700">
      {children}
    </p>
  )
}
