'use client'
import { useEffect, useRef, useState } from 'react'
import { Link2, Download, X, Loader2, CheckCircle, ListMusic, AlertTriangle } from 'lucide-react'
import { motion } from 'framer-motion'
import Button from './ui/Button'
import Card from './ui/Card'
import { Input, Field, Select } from './ui/Field'
import StatusPanel from './ui/StatusPanel'
import OutcomePanel from './ui/OutcomePanel'

interface PreviewTrack {
    index: number
    name: string
    artist: string
    duration_ms?: number
    explicit?: boolean
}

interface Preview {
    preview_token: string
    playlist_name: string
    tracks: PreviewTrack[]
    warning?: string | null
}

interface LinkDownloadProps {
    apiBase: string
    accessToken?: string
}

/** "4:32" from milliseconds. */
const formatDuration = (ms?: number) => {
    if (!ms) return ''
    const total = Math.round(ms / 1000)
    return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

export default function LinkDownload({ apiBase, accessToken }: LinkDownloadProps) {
    const [url, setUrl] = useState('')
    const [format, setFormat] = useState('m4a')
    const [userId] = useState(() => `link_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`)

    // Phase 1: preview; phase 2: selection + download; then job status.
    const [preview, setPreview] = useState<Preview | null>(null)
    const [selected, setSelected] = useState<Set<number>>(new Set())
    const [loadingPreview, setLoadingPreview] = useState(false)
    const [previewError, setPreviewError] = useState('')

    const [starting, setStarting] = useState(false)
    const [downloading, setDownloading] = useState(false)
    const [status, setStatus] = useState<any>(null)

    const loadPreview = async () => {
        if (!url.trim()) return
        setLoadingPreview(true)
        setPreviewError('')
        setPreview(null)

        try {
            const res = await fetch(`${apiBase}/api/link-preview`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url.trim(), spotify_user_token: accessToken || null })
            })
            const data = await res.json()
            if (!res.ok) {
                setPreviewError(data.detail || 'Could not read this playlist')
                return
            }
            setPreview(data)
            setSelected(new Set(data.tracks.map((t: PreviewTrack) => t.index)))
        } catch (e) {
            console.error('Preview error:', e)
            setPreviewError('Backend unreachable')
        } finally {
            setLoadingPreview(false)
        }
    }

    const toggleTrack = (index: number) => {
        setSelected(current => {
            const next = new Set(current)
            if (next.has(index)) next.delete(index)
            else next.add(index)
            return next
        })
    }

    const allSelected = preview ? selected.size === preview.tracks.length : false
    const toggleAll = () => {
        if (!preview) return
        setSelected(allSelected ? new Set() : new Set(preview.tracks.map(t => t.index)))
    }

    const startDownload = async () => {
        if (!preview || selected.size === 0) return
        setStarting(true)
        setDownloading(true)
        setStatus({ status: 'starting', logs: [] })

        try {
            const res = await fetch(`${apiBase}/api/link-download?user_id=${encodeURIComponent(userId)}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    preview_token: preview.preview_token,
                    selected_indexes: Array.from(selected).sort((a, b) => a - b),
                    format,
                })
            })
            const data = await res.json()
            if (!res.ok) {
                setStatus({ status: 'error', logs: [data.detail || 'Could not start download'] })
                setStarting(false)
                setDownloading(false)
                return
            }
            pollStatus()
        } catch (e) {
            console.error('Start error:', e)
            setStatus({ status: 'error', logs: ['Backend unreachable'] })
            setStarting(false)
            setDownloading(false)
        } finally {
            setStarting(false)
        }
    }

    // One poller at a time, and it dies with the component — switching tabs
    // used to leave status polling running forever.
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
    useEffect(() => () => {
        if (pollRef.current) clearInterval(pollRef.current)
    }, [])

    const pollStatus = () => {
        if (pollRef.current) clearInterval(pollRef.current)
        pollRef.current = setInterval(async () => {
            try {
                const res = await fetch(`${apiBase}/api/status?user_id=${encodeURIComponent(userId)}`)
                const data = await res.json()
                setStatus(data)

                if (data.status === 'done' || data.status === 'cancelled' || data.status === 'error') {
                    if (pollRef.current) clearInterval(pollRef.current)
                    pollRef.current = null
                    setDownloading(false)
                }
            } catch (e) {
                console.error('Status poll error:', e)
            }
        }, 1500)
    }

    const handleCancel = async () => {
        try {
            await fetch(`${apiBase}/api/cancel?user_id=${encodeURIComponent(userId)}`, { method: 'POST' })
        } catch (e) {
            console.error('Cancel error:', e)
        }
    }

    const reset = () => {
        if (pollRef.current) {
            clearInterval(pollRef.current)
            pollRef.current = null
        }
        setPreview(null)
        setStatus(null)
        setSelected(new Set())
        setUrl('')
        setPreviewError('')
    }

    const saveUrl = (file: { name: string, path: string }) =>
        `${apiBase}/api/file?path=${encodeURIComponent(file.path)}&user_id=${encodeURIComponent(userId)}`

    const zipUrl = () =>
        `${apiBase}/api/playlist-zip?user_id=${encodeURIComponent(userId)}&playlist=${encodeURIComponent(status?.playlist_dir || '')}`

    // ---- Render -----------------------------------------------------------

    // Job running / finished
    if (downloading && status) {
        return (
            <div className="w-full max-w-2xl mx-auto">
                <StatusPanel
                    status={status}
                    onCancel={handleCancel}
                    onZip={() => window.open(zipUrl(), '_blank')}
                    zipLabel="Download Playlist as ZIP"
                    saveUrl={saveUrl}
                />
            </div>
        )
    }

    if (status?.status === 'done' || status?.status === 'cancelled' || status?.status === 'error') {
        const zipAvailable = status.completed_files?.length > 0 && status.playlist_dir
        return (
            <div className="w-full max-w-2xl mx-auto">
                {status.status === 'done' && (
                    <OutcomePanel
                        tone="success"
                        title="Download Complete!"
                        body={`${status.completed_files?.length || 0} of ${status.total} tracks downloaded`}
                        actionLabel="Download Another"
                        onAction={reset}
                        zipUrl={zipAvailable ? zipUrl() : undefined}
                        zipLabel="Download Playlist as ZIP"
                    />
                )}
                {status.status === 'cancelled' && (
                    <OutcomePanel
                        tone="warning"
                        title="Download Stopped"
                        body={`Downloaded ${status.completed_files?.length || 0} of ${status.total} tracks before stopping`}
                        actionLabel="Start New"
                        onAction={reset}
                        zipUrl={zipAvailable ? zipUrl() : undefined}
                        zipLabel="Download Completed Files"
                    />
                )}
                {status.status === 'error' && (
                    <OutcomePanel
                        tone="danger"
                        title="Could Not Start"
                        body={status.logs?.[0] || 'Something went wrong'}
                        actionLabel="Try Again"
                        onAction={reset}
                    />
                )}
            </div>
        )
    }

    // Track selection
    if (preview) {
        return (
            <div className="w-full max-w-2xl mx-auto space-y-6">
                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                    <Card padding="none" className="overflow-hidden">
                        {/* Playlist header */}
                        <div className="p-5 border-b border-line/70 flex items-center gap-4">
                            <div className="w-12 h-12 rounded-md bg-surface-overlay flex items-center justify-center shrink-0">
                                <ListMusic className="text-accent" size={22} />
                            </div>
                            <div className="min-w-0">
                                <h3 className="font-bold text-content truncate">{preview.playlist_name}</h3>
                                <p className="text-content-muted text-sm">
                                    {selected.size} of {preview.tracks.length} selected
                                </p>
                            </div>
                            <button
                                onClick={reset}
                                className="ml-auto text-content-muted hover:text-content transition-colors shrink-0"
                                aria-label="Back"
                            >
                                <X size={20} />
                            </button>
                        </div>

                        {/* Limit / truncation note */}
                        {preview.warning && (
                            <div className="px-5 py-3 bg-warning-faint border-b border-line/70 text-warning text-xs flex items-center gap-2">
                                <AlertTriangle size={14} className="shrink-0" />
                                {preview.warning}
                            </div>
                        )}

                        {/* Track list */}
                        <div className="max-h-[26rem] overflow-y-auto">
                            {preview.tracks.map((track, i) => {
                                const isSelected = selected.has(track.index)
                                return (
                                    <button
                                        key={track.index}
                                        onClick={() => toggleTrack(track.index)}
                                        className={`w-full flex items-center gap-3 px-5 py-2.5 text-left transition-colors hover:bg-surface-overlay ${isSelected ? '' : 'opacity-50'}`}
                                    >
                                        <span className={`w-5 h-5 rounded-sm border flex items-center justify-center shrink-0 transition-colors ${isSelected ? 'bg-accent border-accent text-black' : 'border-content-faint'}`}>
                                            {isSelected && <CheckCircle size={13} />}
                                        </span>
                                        <span className="w-6 text-content-faint text-xs text-right shrink-0">{i + 1}</span>
                                        <span className="min-w-0 flex-1">
                                            <span className="block text-sm text-content truncate">
                                                {track.name}
                                                {track.explicit && <span className="ml-2 text-[10px] bg-surface-overlay text-content-faint px-1 py-0.5 rounded align-middle">E</span>}
                                            </span>
                                            <span className="block text-xs text-content-muted truncate">{track.artist}</span>
                                        </span>
                                        <span className="text-content-faint text-xs shrink-0">{formatDuration(track.duration_ms)}</span>
                                    </button>
                                )
                            })}
                        </div>

                        {/* Footer actions */}
                        <div className="p-4 border-t border-line/70 flex flex-wrap items-center gap-3">
                            <Button variant="secondary" size="sm" onClick={toggleAll}>
                                {allSelected ? 'Clear All' : 'Select All'}
                            </Button>
                            <Field label="Format:">
                                <Select value={format} onChange={(e) => setFormat(e.target.value)} className="w-auto">
                                    <option value="m4a">M4A — original quality (fast)</option>
                                    <option value="mp3">MP3 320 kbps (re-encoded)</option>
                                </Select>
                            </Field>
                            <Button
                                variant="primary"
                                size="md"
                                loading={starting}
                                icon={<Download size={16} />}
                                disabled={selected.size === 0}
                                onClick={startDownload}
                                className="ml-auto"
                            >
                                {starting ? 'Starting...' : `Download ${selected.size} Track${selected.size === 1 ? '' : 's'}`}
                            </Button>
                        </div>
                    </Card>
                </motion.div>
            </div>
        )
    }

    // URL input (first screen)
    return (
        <div className="w-full max-w-2xl mx-auto space-y-8">
            <Card padding="lg" className="border-dashed border-line-strong">
                <div className="text-center space-y-4">
                    <Link2 className="mx-auto text-content-faint" size={48} />
                    <div>
                        <h3 className="text-xl font-bold text-content mb-2">Paste a Playlist Link</h3>
                        <p className="text-content-muted text-sm">
                            Copy any public Spotify playlist link and inspect the tracks before downloading.
                            {!accessToken && ' Without login, Spotify shares the first 50 tracks.'}
                        </p>
                    </div>

                    <Input
                        type="text"
                        value={url}
                        onChange={(e) => setUrl(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') loadPreview() }}
                        placeholder="https://open.spotify.com/playlist/..."
                        disabled={loadingPreview}
                    />

                    {previewError && (
                        <p className="text-danger text-sm">{previewError}</p>
                    )}
                </div>
            </Card>

            {url.trim() && (
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="flex gap-4">
                    <Button
                        variant="primary"
                        size="lg"
                        onClick={loadPreview}
                        disabled={loadingPreview}
                        className="flex-1"
                    >
                        {loadingPreview ? (
                            <><Loader2 className="animate-spin" size={18} /> Reading playlist...</>
                        ) : (
                            <><ListMusic size={18} /> Preview Tracks</>
                        )}
                    </Button>
                    <Button variant="secondary" size="lg" onClick={() => { setUrl(''); setPreviewError('') }} icon={<X />} aria-label="Clear" />
                </motion.div>
            )}
        </div>
    )
}
