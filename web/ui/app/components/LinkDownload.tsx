'use client'
import { useState } from 'react'
import { Link2, Download, Loader2, CheckCircle, X, Music } from 'lucide-react'
import { motion } from 'framer-motion'

interface LinkDownloadProps {
    apiBase: string
    accessToken?: string
}

export default function LinkDownload({ apiBase, accessToken }: LinkDownloadProps) {
    const [url, setUrl] = useState('')
    const [quality, setQuality] = useState('320')
    const [starting, setStarting] = useState(false)
    const [downloading, setDownloading] = useState(false)
    const [status, setStatus] = useState<any>(null)
    // Unique session id: files land in downloads/<userId>/<playlist>/
    const [userId] = useState(() => `link_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`)

    const handleStart = async () => {
        if (!url.trim()) return

        setStarting(true)
        setDownloading(true)
        setStatus({ status: 'starting', logs: [] })

        try {
            const response = await fetch(`${apiBase}/api/link-download?user_id=${encodeURIComponent(userId)}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    url: url.trim(),
                    quality,
                    // When logged in, the backend uses this to read the full playlist list.
                    spotify_user_token: accessToken || null
                })
            })

            const data = await response.json()
            if (!response.ok) {
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

    const pollStatus = () => {
        const interval = setInterval(async () => {
            try {
                const res = await fetch(`${apiBase}/api/status?user_id=${encodeURIComponent(userId)}`)
                const data = await res.json()
                setStatus(data)

                if (data.status === 'done' || data.status === 'cancelled' || data.status === 'error') {
                    clearInterval(interval)
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

    return (
        <div className="w-full max-w-2xl mx-auto space-y-8">
            {/* Link Input Section */}
            <div className="bg-neutral-800 border-2 border-dashed border-neutral-600 rounded-2xl p-8">
                <div className="text-center space-y-4">
                    <Link2 className="mx-auto text-neutral-400" size={48} />
                    <div>
                        <h3 className="text-xl font-bold text-white mb-2">Paste a Playlist Link</h3>
                        <p className="text-neutral-400 text-sm">
                            Copy any public Spotify playlist link and paste it here. No login needed.
                            {!accessToken && ' Without login, Spotify shares the first 50 tracks; log in for full playlists.'}
                            {accessToken && ' Logged in: full playlists, including your own private ones.'}
                        </p>
                    </div>

                    <input
                        type="text"
                        value={url}
                        onChange={(e) => setUrl(e.target.value)}
                        placeholder="https://open.spotify.com/playlist/..."
                        disabled={downloading}
                        className="w-full bg-neutral-900 text-white rounded-lg px-4 py-3 border border-neutral-700 focus:border-green-500 outline-none placeholder:text-neutral-600"
                    />

                    <div className="flex items-center justify-center gap-4">
                        <div>
                            <label className="text-neutral-400 text-sm mr-2">Quality:</label>
                            <select
                                value={quality}
                                onChange={(e) => setQuality(e.target.value)}
                                className="bg-neutral-900 text-white rounded px-3 py-2 border border-neutral-700 focus:border-green-500 outline-none"
                                disabled={downloading}
                            >
                                <option value="320">High (320kbps)</option>
                                <option value="192">Standard (192kbps)</option>
                            </select>
                        </div>
                    </div>
                </div>
            </div>

            {/* Action Buttons */}
            {url.trim() && !downloading && (
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="flex gap-4"
                >
                    <button
                        onClick={handleStart}
                        disabled={starting || downloading}
                        className="flex-1 bg-green-500 text-black px-8 py-4 rounded-xl font-bold text-lg hover:bg-green-400 transition disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                        {starting ? <Loader2 className="animate-spin" /> : <Download />}
                        {starting ? 'Starting...' : 'Download Playlist'}
                    </button>
                    <button
                        onClick={() => setUrl('')}
                        className="px-6 py-4 bg-neutral-700 text-white rounded-xl font-medium hover:bg-neutral-600 transition"
                    >
                        <X />
                    </button>
                </motion.div>
            )}

            {/* Download Status */}
            {downloading && status && (
                <div className="bg-black border border-neutral-800 rounded-2xl p-6 font-mono text-sm">
                    <div className="flex justify-between items-center text-neutral-400 mb-4 border-b border-neutral-800 pb-2">
                        <span>STATUS: {status.status?.toUpperCase()}</span>
                        <span>{status.completed}/{status.total}</span>
                    </div>

                    {status.current_track && (
                        <div className="text-green-500 animate-pulse mb-4">
                            &gt; Processing: {status.current_track}
                        </div>
                    )}

                    <div className="flex gap-3 mb-4">
                        <button
                            onClick={handleCancel}
                            disabled={status.status === 'cancelled' || status.status === 'done'}
                            className="bg-red-600 hover:bg-red-500 text-white px-4 py-2 rounded font-bold disabled:opacity-50 disabled:cursor-not-allowed transition"
                        >
                            Stop Download
                        </button>
                    </div>

                    {/* Completed Files */}
                    {status.completed_files && status.completed_files.length > 0 && (
                        <div className="mt-6 border-t border-neutral-800 pt-4">
                            <h4 className="text-white font-bold mb-3 flex items-center gap-2">
                                <CheckCircle size={16} className="text-green-500" />
                                Ready to Download ({status.completed_files.length})
                            </h4>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-64 overflow-y-auto">
                                {status.completed_files.map((file: any, i: number) => (
                                    <div key={i} className="flex justify-between items-center bg-neutral-900 p-2 rounded border border-neutral-800">
                                        <span className="text-neutral-300 truncate text-xs mr-2">{file.name}</span>
                                        <a
                                            href={`${apiBase}/api/file?path=${encodeURIComponent(file.path)}&user_id=${encodeURIComponent(userId)}`}
                                            target="_blank"
                                            className="bg-green-600 hover:bg-green-500 text-white text-xs px-3 py-1 rounded flex items-center gap-1 transition"
                                            download
                                        >
                                            <Download size={12} /> Save
                                        </a>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Download Playlist as ZIP */}
                    {status.status === 'done' && status.completed_files?.length > 0 && status.playlist_dir && (
                        <div className="mt-4">
                            <button
                                onClick={() => window.open(`${apiBase}/api/playlist-zip?user_id=${encodeURIComponent(userId)}&playlist=${encodeURIComponent(status.playlist_dir)}`, '_blank')}
                                className="w-full bg-green-500 text-black font-bold py-3 px-6 rounded-xl hover:bg-green-400 transition flex items-center justify-center gap-2"
                            >
                                <Download size={20} /> Download Playlist as ZIP
                            </button>
                        </div>
                    )}
                </div>
            )}

            {/* Error State */}
            {status?.status === 'error' && !downloading && (
                <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="bg-red-900/20 border border-red-700 rounded-2xl p-6 text-center"
                >
                    <X className="w-16 h-16 text-red-500 mx-auto mb-4" />
                    <h3 className="text-2xl font-bold text-white mb-2">Could Not Start</h3>
                    <p className="text-neutral-400 mb-4">{status.logs?.[0] || 'Something went wrong'}</p>
                    <button
                        onClick={() => { setStatus(null); setDownloading(false) }}
                        className="bg-white text-black px-6 py-2 rounded-full font-bold hover:scale-105 transition"
                    >
                        Try Again
                    </button>
                </motion.div>
            )}

            {/* Success State */}
            {status?.status === 'done' && !downloading && (
                <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="bg-green-900/20 border border-green-700 rounded-2xl p-6 text-center"
                >
                    <CheckCircle className="w-16 h-16 text-green-500 mx-auto mb-4" />
                    <h3 className="text-2xl font-bold text-white mb-2">Download Complete!</h3>
                    <p className="text-neutral-400 mb-4">
                        {status.completed_files?.length || 0} of {status.total} tracks downloaded
                    </p>
                    <div className="flex gap-3 justify-center">
                        {status.completed_files?.length > 0 && status.playlist_dir && (
                            <button
                                onClick={() => window.open(`${apiBase}/api/playlist-zip?user_id=${encodeURIComponent(userId)}&playlist=${encodeURIComponent(status.playlist_dir)}`, '_blank')}
                                className="bg-green-500 text-black px-6 py-2 rounded-full font-bold hover:scale-105 transition"
                            >
                                Download as ZIP
                            </button>
                        )}
                        <button
                            onClick={() => { setStatus(null); setUrl('') }}
                            className="bg-neutral-700 text-white px-6 py-2 rounded-full font-bold hover:bg-neutral-600 transition"
                        >
                            Download Another
                        </button>
                    </div>
                </motion.div>
            )}

            {/* Cancelled State */}
            {status?.status === 'cancelled' && !downloading && (
                <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="bg-yellow-900/20 border border-yellow-700 rounded-2xl p-6 text-center"
                >
                    <Music className="w-16 h-16 text-yellow-500 mx-auto mb-4" />
                    <h3 className="text-2xl font-bold text-white mb-2">Download Stopped</h3>
                    <p className="text-neutral-400 mb-4">
                        Downloaded {status.completed_files?.length || 0} of {status.total} tracks before stopping
                    </p>
                    <div className="flex gap-3 justify-center">
                        {status.completed_files?.length > 0 && status.playlist_dir && (
                            <button
                                onClick={() => window.open(`${apiBase}/api/playlist-zip?user_id=${encodeURIComponent(userId)}&playlist=${encodeURIComponent(status.playlist_dir)}`, '_blank')}
                                className="bg-green-500 text-black px-6 py-2 rounded-full font-bold hover:scale-105 transition"
                            >
                                Download Completed Files
                            </button>
                        )}
                        <button
                            onClick={() => { setStatus(null); setUrl('') }}
                            className="bg-neutral-700 text-white px-6 py-2 rounded-full font-bold hover:bg-neutral-600 transition"
                        >
                            Start New
                        </button>
                    </div>
                </motion.div>
            )}
        </div>
    )
}
