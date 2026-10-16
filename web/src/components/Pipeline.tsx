import type { Trip } from '../lib/types'

type PipelineState = NonNullable<Trip['pipeline']>

const stageLabel: Record<string, string> = {
  starting: 'Getting started',
  extracting: 'Watching the Reels',
  verifying: 'Checking each place on Google Maps',
  summarizing: 'Reading what visitors say',
}

export function PipelineProgress({ pipeline }: { pipeline: PipelineState }) {
  const fraction = pipeline.total > 0 ? pipeline.done / pipeline.total : 0
  return (
    <div role="status" className="space-y-3 rounded-2xl border border-line bg-card p-4">
      <div className="flex items-baseline justify-between gap-3">
        <p className="font-semibold">{stageLabel[pipeline.stage] ?? 'Working…'}</p>
        {pipeline.total > 0 && (
          <p className="text-sm text-muted tabular-nums">
            {pipeline.done} of {pipeline.total}
          </p>
        )}
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-line">
        <div
          className="h-full rounded-full bg-lagoon transition-[width] duration-500"
          style={{ width: `${Math.max(fraction * 100, 6)}%` }}
        />
      </div>
      <p className="text-sm text-muted">This usually takes about a minute.</p>
    </div>
  )
}

export function DroppedPlaces({ dropped }: { dropped: PipelineState['dropped'] }) {
  if (dropped.length === 0) return null
  return (
    <details className="rounded-xl bg-line/40 px-3 py-2 text-sm">
      <summary className="cursor-pointer font-semibold">
        {dropped.length} {dropped.length === 1 ? 'place' : 'places'} left out after checking Google
        Maps
      </summary>
      <ul className="mt-2 space-y-1 text-muted">
        {dropped.map((place) => (
          <li key={place.name}>
            <span className="font-medium text-ink">{place.name}</span>: {place.reason}
          </li>
        ))}
      </ul>
    </details>
  )
}
