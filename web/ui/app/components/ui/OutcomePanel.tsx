import { CheckCircle, X, Music } from 'lucide-react'
import { motion } from 'framer-motion'
import Button from './Button'

/**
 * End-of-job message card shared by the success, cancelled, and error states
 * of every download flow.
 */
export default function OutcomePanel({
    tone,
    title,
    body,
    actionLabel,
    onAction,
    zipUrl,
    zipLabel = 'Download as ZIP',
}: {
    tone: 'success' | 'danger' | 'warning'
    title: string
    body: string
    actionLabel: string
    onAction: () => void
    zipUrl?: string
    zipLabel?: string
}) {
    const tones = {
        success: { border: 'border-accent-muted', bg: 'bg-accent-faint', icon: <CheckCircle className="w-16 h-16 text-accent mx-auto mb-4" /> },
        danger: { border: 'border-danger', bg: 'bg-danger-faint', icon: <X className="w-16 h-16 text-danger mx-auto mb-4" /> },
        warning: { border: 'border-warning', bg: 'bg-warning-faint', icon: <Music className="w-16 h-16 text-warning mx-auto mb-4" /> },
    }

    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className={`${tones[tone].bg} border ${tones[tone].border} rounded-card p-6 text-center`}
        >
            {tones[tone].icon}
            <h3 className="text-2xl font-bold text-content mb-2">{title}</h3>
            <p className="text-content-muted mb-4">{body}</p>
            <div className="flex gap-3 justify-center">
                {zipUrl && (
                    <Button variant="primary" size="md" onClick={() => window.open(zipUrl, '_blank')}>
                        {zipLabel}
                    </Button>
                )}
                <Button variant="secondary" size="md" onClick={onAction}>
                    {actionLabel}
                </Button>
            </div>
            {zipUrl && (
                <p className="text-content-faint text-xs mt-3">
                    Built and streamed live — the server forgets these files once you have them.
                </p>
            )}
        </motion.div>
    )
}
