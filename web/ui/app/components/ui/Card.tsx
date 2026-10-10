import type { ReactNode } from 'react'

/**
 * Standard surface. Spotify cards are slightly raised from the base with a
 * subtle border, not a hard outline.
 *
 * Use `padding="none"` for cards whose children manage their own spacing
 * (e.g. status panels with headers/footers).
 */
export default function Card({
    children,
    padding = 'md',
    className = '',
}: {
    children: ReactNode
    padding?: 'none' | 'sm' | 'md' | 'lg'
    className?: string
}) {
    const paddings = { none: '', sm: 'p-4', md: 'p-6', lg: 'p-8' }
    return (
        <div className={`bg-surface-raised border border-line/70 rounded-card ${paddings[padding]} ${className}`}>
            {children}
        </div>
    )
}
