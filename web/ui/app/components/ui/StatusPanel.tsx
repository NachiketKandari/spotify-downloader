import { CheckCircle, Download } from 'lucide-react'
import Button from './Button'

/**
 * The list of finished files shown during and after a job.
 * `onSaveUrl(file)` lets each screen control how download links are built.
 */
function CompletedFileList({
    files,
    saveUrl,
}: {
    files: { name: string, path: string }[]
    saveUrl: (file: { name: string, path: string }) => string
}) {
    if (!files || files.length === 0) return null

    return (
        <div className="mt-6 border-t border-line pt-4">
            <h4 className="text-content font-bold mb-3 flex items-center gap-2">
                <CheckCircle size={16} className="text-accent" />
                Ready to Download ({files.length})
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-64 overflow-y-auto">
                {files.map((file, i) => (
                    <div key={i} className="flex justify-between items-center bg-surface-overlay p-2 rounded-md border border-line/60">
                        <span className="text-content-muted truncate text-xs mr-2">{file.name}</span>
                        <a
                            href={saveUrl(file)}
                            target="_blank"
                            download
                            className="bg-accent-faint hover:bg-accent-muted text-accent hover:text-black text-xs font-bold px-3 py-1 rounded-full flex items-center gap-1 transition-colors shrink-0"
                        >
                            <Download size={12} /> Save
                        </a>
                    </div>
                ))}
            </div>
        </div>
    )
}

/**
 * The shared job progress panel: status line, current track, progress bar,
 * optional logs, completed files, and a ZIP button.
 */
export default function StatusPanel({
    status,
    onCancel,
    onZip,
    zipLabel = 'Download as ZIP',
    saveUrl,
    children,
}: {
    status: any
    onCancel: () => void
    onZip?: () => void
    zipLabel?: string
    saveUrl: (file: { name: string, path: string }) => string
    children?: React.ReactNode
}) {
    const done = status.completed || 0
    const total = status.total || 0
    const percent = total > 0 ? Math.round((done / total) * 100) : 0

    return (
        <div className="bg-surface-raised border border-line/70 rounded-card p-6 font-mono text-sm">
            <div className="flex justify-between items-center text-content-muted mb-4">
                <span>STATUS: {String(status.status || '').toUpperCase()}</span>
                <span>{done}/{total}</span>
            </div>

            {/* Progress bar */}
            <div className="h-1.5 bg-surface-overlay rounded-full overflow-hidden mb-5">
                <div className="h-full bg-accent transition-all duration-500" style={{ width: `${percent}%` }} />
            </div>

            {status.current_track && (
                <div className="text-accent animate-pulse mb-4 break-all">
                    &gt; Processing: {status.current_track}
                </div>
            )}

            {/* Job notes (playlist info, warnings, skipped tracks) */}
            {status.logs?.length > 0 && (
                <div className="mb-4 max-h-32 overflow-y-auto text-content-faint space-y-0.5">
                    {status.logs.slice(-12).map((log: string, i: number) => (
                        <div key={i} className="truncate">&middot; {log}</div>
                    ))}
                </div>
            )}

            {children}

            <div className="flex gap-3 mb-4">
                <Button
                    variant="danger"
                    size="md"
                    onClick={onCancel}
                    disabled={status.status === 'cancelled' || status.status === 'done' || status.status === 'error'}
                >
                    Stop Download
                </Button>
            </div>

            <CompletedFileList files={status.completed_files || []} saveUrl={saveUrl} />

            {onZip && (status.status === 'done' || status.status === 'cancelled') && status.completed_files?.length > 0 && (
                <div className="mt-4">
                    <Button variant="primary" size="lg" onClick={onZip} icon={<Download size={20} />} className="w-full">
                        {zipLabel}
                    </Button>
                </div>
            )}
        </div>
    )
}
