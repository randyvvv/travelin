import type { MapsSource } from '../lib/types'

/**
 * Attribution required by Grounding with Google Maps: directly under the generated
 * text, "Google Maps" unmodified and untranslated, Roboto 12-16px, #5E5E5E.
 */
export function MapsSources({ sources }: { sources: MapsSource[] }) {
  if (sources.length === 0) return null
  return (
    <div
      className="mt-3 border-t border-line pt-3"
      style={{ fontFamily: 'Roboto, Arial, sans-serif' }}
    >
      <p className="text-[13px] text-[#5E5E5E]">
        Sources from{' '}
        <span translate="no" className="notranslate">
          Google Maps
        </span>
      </p>
      <ul className="mt-1 space-y-0.5">
        {sources.map((source) => (
          <li key={source.uri}>
            <a
              href={source.uri}
              target="_blank"
              rel="noreferrer"
              className="text-[13px] text-[#5E5E5E] underline underline-offset-2"
            >
              {source.title}
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
}
