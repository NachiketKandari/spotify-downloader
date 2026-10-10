import type { ReactNode } from 'react'

type Tone = 'neutral' | 'accent' | 'danger' | 'warning'

const tones: Record<Tone, string> = {
    neutral: 'bg-surface-overlay text-content-muted border-line',
    accent: 'bg-accent-faint text-accent border-accent-muted',
    danger: 'bg-danger-faint text-danger border-danger',
    warning: 'bg-warning-faint text-warning border-warning',
}

export default function Badge({ tone = 'neutral', children }: { tone?: Tone, children: ReactNode }) {
    return (
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${tones[tone]}`}>
            {children}
        </span>
    )
}
