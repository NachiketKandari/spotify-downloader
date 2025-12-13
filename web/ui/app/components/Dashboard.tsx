'use client'
import { useState, useEffect } from 'react'
import Image from 'next/image'
import { Download, CheckCircle, Loader2, Play, Music, FolderSearch } from 'lucide-react'
import { motion } from 'framer-motion'
import clsx from 'clsx'

interface DashboardProps {
    accessToken: string
}

interface Playlist {
    id: string
    name: string
    images: { url: string }[]
    tracks: { total: number, href: string }
    owner: { display_name: string }
}

interface Track {
    uri: string
    name: string
    artist: string
    album: string
    cover_url?: string
}

export default function Dashboard({ accessToken }: DashboardProps) {
    const [playlists, setPlaylists] = useState<Playlist[]>([])
    const [loading, setLoading] = useState(true)
    const [downloading, setDownloading] = useState(false)
    const [status, setStatus] = useState<any>(null)
    const [quality, setQuality] = useState('320')
    const [downloadPath, setDownloadPath] = useState('') // Default empty to force selection
    const [pickingFolder, setPickingFolder] = useState(false)
    const [showSuccess, setShowSuccess] = useState(false)

    // Fetch Playlists on Mount
    useEffect(() => {
        const fetchPlaylists = async () => {
            try {
                let all: Playlist[] = []
                let url = 'https://api.spotify.com/v1/me/playlists?limit=50'
                while (url) {
                    const res = await fetch(url, {
                        headers: { Authorization: `Bearer ${accessToken}` }
                    })
                    const data = await res.json()
                    all = [...all, ...data.items]
                    url = data.next
                }
                setPlaylists(all)
            } catch (e) {
                console.error(e)
            } finally {
                setLoading(false)
            }
        }
        fetchPlaylists()
    }, [accessToken])

    // Poll Status when downloading
    useEffect(() => {
        let interval: NodeJS.Timeout
        if (downloading) {
            interval = setInterval(async () => {
                try {
                    const res = await fetch('http://localhost:8000/api/status')
                    const data = await res.json()
                    setStatus(data)
                    if (data.status === 'done' || data.status === 'idle') {
                        if (data.status === 'done' && data.completed === data.total) {
                            setDownloading(false)
                            setShowSuccess(true)
                        }
                    }
                } catch (e) { }
            }, 1000)
        }
        return () => clearInterval(interval)
    }, [downloading])

    // Track Selection State
    // Map<PlaylistID, Set<TrackURI>>. If an entry exists, the playlist is "selected".
    // If the Set is empty but entry exists -> implied "ALL" (legacy behavior) OR we can be explicit.
    // Let's be explicit: 
    // State: selectedPlaylists: Map<string, { mode: 'ALL' | 'PARTIAL', selectedTracks: Set<string> }>
    interface SelectionState {
        mode: 'ALL' | 'PARTIAL'
        selectedTracks: Set<string> // URIs
    }
    const [selectionModel, setSelectionModel] = useState<Map<string, SelectionState>>(new Map())
    const [viewingPlaylist, setViewingPlaylist] = useState<Playlist | null>(null)
    const [tracksCache, setTracksCache] = useState<Map<string, Track[]>>(new Map())
    const [loadingTracks, setLoadingTracks] = useState(false)

    // Helper to get selection state for a playlist
    const getPlaylistSelection = (id: string) => selectionModel.get(id)

    // Toggle Playlist Selection (Main Grid Click)
    // Default behavior: Select ALL if not selected. Deselect if selected.
    const togglePlaylist = (id: string) => {
        const next = new Map(selectionModel)
        if (next.has(id)) {
            next.delete(id)
        } else {
            next.set(id, { mode: 'ALL', selectedTracks: new Set() })
        }
        setSelectionModel(next)
    }

    // Open Playlist Modal
    const openPlaylist = async (playlist: Playlist) => {
        setViewingPlaylist(playlist)
        if (!tracksCache.has(playlist.id)) {
            setLoadingTracks(true)
            try {
                // Fetch tracks
                const tracks: Track[] = []
                const uniqueUris = new Set<string>()
                let url = `https://api.spotify.com/v1/playlists/${playlist.id}/tracks?fields=items(track(name,uri,artists,album(name,images))),next&limit=100`

                while (url) {
                    const res = await fetch(url, { headers: { Authorization: `Bearer ${accessToken}` } })
                    const data = await res.json()
                    for (const item of data.items) {
                        if (item.track && !uniqueUris.has(item.track.uri)) {
                            uniqueUris.add(item.track.uri)
                            tracks.push({
                                uri: item.track.uri,
                                name: item.track.name,
                                artist: item.track.artists.map((a: any) => a.name).join(';'),
                                album: item.track.album.name,
                                cover_url: item.track.album.images?.[0]?.url
                            })
                        }
                    }
                    url = data.next
                }
                setTracksCache(prev => new Map(prev).set(playlist.id, tracks))
            } catch (e) {
                console.error(e)
            } finally {
                setLoadingTracks(false)
            }
        }
    }

    const startDownload = async () => {
        setDownloading(true)
        setStatus({ status: 'starting', logs: [] })

        interface PlaylistBatch {
            name: string
            tracks: Track[]
        }
        const batches: PlaylistBatch[] = []

        for (const [playlistId, selection] of Array.from(selectionModel.entries())) {
            const playlist = playlists.find(p => p.id === playlistId)
            if (!playlist) continue

            console.log(`Processing ${playlist.name}...`)

            let tracksToDownload: Track[] = []

            // If we have cached tracks, use them to filter/select
            if (tracksCache.has(playlistId)) {
                const cached = tracksCache.get(playlistId)!
                if (selection.mode === 'ALL') {
                    tracksToDownload = cached
                } else {
                    tracksToDownload = cached.filter(t => selection.selectedTracks.has(t.uri))
                }
            } else {
                // Not cached? Must be 'ALL' mode and never opened. Fetch now.
                // Re-implement fetch logic briefly for this case (or refactor fetch logic to be reusable)
                // reusing code is better. 
                // Ideally we should have a `fetchTracks(id)` function.
                // For now, inline fetch for 'ALL' case if not cached.

                const fetchedTracks: Track[] = []
                const uniqueUris = new Set<string>()
                let url = `https://api.spotify.com/v1/playlists/${playlistId}/tracks?fields=items(track(name,uri,artists,album(name,images))),next&limit=100`
                while (url) {
                    const res = await fetch(url, { headers: { Authorization: `Bearer ${accessToken}` } })
                    const data = await res.json()
                    for (const item of data.items) {
                        if (item.track && !uniqueUris.has(item.track.uri)) {
                            uniqueUris.add(item.track.uri)
                            fetchedTracks.push({
                                uri: item.track.uri,
                                name: item.track.name,
                                artist: item.track.artists.map((a: any) => a.name).join(';'),
                                album: item.track.album.name,
                                cover_url: item.track.album.images?.[0]?.url
                            })
                        }
                    }
                    url = data.next
                }

                // Update Cache? No, state update in loop is risky. Just use local var.
                if (selection.mode === 'ALL') {
                    tracksToDownload = fetchedTracks
                }
                // Partial without cache shouldn't happen logic-wise as opening modal creates cache.
            }

            if (tracksToDownload.length > 0) {
                batches.push({
                    name: playlist.name,
                    tracks: tracksToDownload
                })
            }
        }

        // 2. Send to Backend
        try {
            await fetch('http://localhost:8000/api/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ playlists: batches, quality, output_path: downloadPath })
            })
        } catch (e) {
            console.error("Backend Error", e)
            setDownloading(false)
        }
    }

    return (
        <div>
            {/* Control Bar */}
            <div className="bg-neutral-800 p-6 rounded-2xl mb-8 flex justify-between items-center sticky top-4 z-10 shadow-xl border border-neutral-700">
                <div className="flex items-center gap-6">
                    <div>
                        <div className="text-neutral-400 text-sm font-medium">Selected</div>
                        <div className="text-2xl font-bold text-white">{selectionModel.size} <span className="text-neutral-500 text-lg">playlists</span></div>
                    </div>
                    <div className="h-10 w-px bg-neutral-700"></div>
                    <div>
                        <div className="text-neutral-400 text-sm font-medium">Download Location</div>
                        <div className="flex items-center gap-2 mt-1">
                            <input
                                type="text"
                                value={downloadPath}
                                onChange={(e) => setDownloadPath(e.target.value)}
                                className="bg-neutral-900 text-white rounded-l px-2 py-1 border border-neutral-700 focus:border-green-500 outline-none w-48 text-sm"
                                placeholder="/path/to/folder"
                            />
                            <button
                                onClick={async () => {
                                    if (pickingFolder) return
                                    setPickingFolder(true)
                                    try {
                                        const res = await fetch('http://localhost:8000/api/choose-directory')
                                        const data = await res.json()
                                        if (data.path) setDownloadPath(data.path)
                                    } catch (e) { console.error(e) }
                                    finally { setPickingFolder(false) }
                                }}
                                disabled={pickingFolder}
                                className={clsx(
                                    "px-3 py-1 rounded-r border border-l-0 border-neutral-700 flex items-center transition",
                                    pickingFolder ? "bg-neutral-800 text-neutral-500 cursor-wait" : "bg-neutral-700 hover:bg-neutral-600 text-white"
                                )}
                                title="Browse Folder"
                            >
                                {pickingFolder ? <Loader2 size={16} className="animate-spin" /> : <FolderSearch size={16} />}
                            </button>
                        </div>
                    </div>
                    <div className="h-10 w-px bg-neutral-700"></div>
                    <div>
                        <div className="text-neutral-400 text-sm font-medium">Quality</div>
                        <select
                            value={quality}
                            onChange={(e) => setQuality(e.target.value)}
                            className="bg-neutral-900 text-white rounded px-2 py-1 mt-1 border border-neutral-700 focus:border-green-500 outline-none"
                        >
                            <option value="320">High (320kbps)</option>
                            <option value="192">Standard (192kbps)</option>
                        </select>
                    </div>
                </div>

                <div className="flex gap-3">
                    <button
                        onClick={() => {
                            if (selectionModel.size === playlists.length) setSelectionModel(new Map())
                            else {
                                const next = new Map()
                                playlists.forEach(p => next.set(p.id, { mode: 'ALL', selectedTracks: new Set() }))
                                setSelectionModel(next)
                            }
                        }}
                        className="px-4 py-3 bg-neutral-700 text-white rounded-xl font-medium hover:bg-neutral-600 transition"
                    >
                        {selectionModel.size === playlists.length ? 'Deselect All' : 'Select All'}
                    </button>
                    <button
                        onClick={startDownload}
                        disabled={selectionModel.size === 0 || downloading || !downloadPath}
                        className="px-8 py-3 bg-green-500 text-black rounded-xl font-bold hover:bg-green-400 transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                        {downloading ? <Loader2 className="animate-spin" /> : <Download size={20} />}
                        {downloading ? 'Processing...' : 'Download Selected'}
                    </button>
                </div>
            </div>

            {/* Progress Area */}
            {downloading && status && (
                <div className="bg-black border border-neutral-800 rounded-2xl p-6 mb-8 font-mono text-sm max-h-64 overflow-y-auto">
                    <div className="flex justify-between text-neutral-400 mb-4 border-b border-neutral-800 pb-2">
                        <span>STATUS: {status.status.toUpperCase()}</span>
                        <span>{status.completed}/{status.total}</span>
                    </div>
                    <div className="space-y-1">
                        {status.recent_logs?.map((log: string, i: number) => (
                            <div key={i} className="text-neutral-300 border-l-2 border-green-900 pl-2">{log}</div>
                        ))}
                        {status.current_track && (
                            <div className="text-green-500 animate-pulse">&gt; Processing: {status.current_track}</div>
                        )}
                    </div>
                </div>
            )}

            {/* Playlist Grid */}
            {loading ? (
                <div className="flex justify-center p-20"><Loader2 className="animate-spin text-green-500" size={48} /></div>
            ) : (
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6">
                    {playlists.map(playlist => {
                        const isSelected = selectionModel.has(playlist.id)
                        const selState = selectionModel.get(playlist.id)
                        return (
                            <motion.div
                                key={playlist.id}
                                initial={{ opacity: 0, y: 20 }}
                                animate={{ opacity: 1, y: 0 }}
                                className={clsx(
                                    "group relative bg-neutral-800/50 rounded-lg p-4 transition border-2",
                                    isSelected ? "border-green-500 bg-neutral-800" : "border-transparent"
                                )}
                            >
                                <div
                                    className="relative aspect-square w-full mb-4 shadow-lg rounded-md overflow-hidden cursor-pointer"
                                    onClick={() => openPlaylist(playlist)}
                                >
                                    {playlist.images?.[0] ? (
                                        <Image
                                            src={playlist.images[0].url}
                                            alt={playlist.name}
                                            fill
                                            className="object-cover group-hover:scale-105 transition duration-500"
                                        />
                                    ) : (
                                        <div className="w-full h-full bg-neutral-700 flex items-center justify-center">
                                            <Music className="text-neutral-500" />
                                        </div>
                                    )}
                                    {/* Overlay on Hover / Selected */}
                                    <div className={clsx(
                                        "absolute inset-0 bg-black/60 flex flex-col items-center justify-center transition opacity-0 group-hover:opacity-100 backdrop-blur-[2px]",
                                        isSelected && "opacity-100" // Always show if selected
                                    )}>
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation()
                                                togglePlaylist(playlist.id)
                                            }}
                                            className={clsx(
                                                "mb-3 transform transition hover:scale-110",
                                                isSelected ? "text-green-500" : "text-white"
                                            )}
                                        >
                                            <CheckCircle size={48} fill={isSelected ? "black" : "none"} />
                                        </button>

                                        <span className="text-white text-xs font-bold uppercase tracking-wider mb-2">
                                            {isSelected
                                                ? (selState?.mode === 'ALL' ? 'Selected All' : `${selState?.selectedTracks.size} Songs`)
                                                : 'Click image to inspect'}
                                        </span>
                                    </div>
                                </div>
                                <div className="flex justify-between items-start">
                                    <div>
                                        <h3 className="font-bold text-white truncate w-32">{playlist.name}</h3>
                                        <p className="text-sm text-neutral-400 truncate w-32">
                                            {playlist.tracks.total} tracks
                                        </p>
                                    </div>
                                </div>
                            </motion.div>
                        )
                    })}
                </div>
            )}

            {/* Playlist Detail Modal */}
            {viewingPlaylist && (
                <div className="fixed inset-0 bg-black/90 z-50 flex items-center justify-center backdrop-blur-md p-8" onClick={() => setViewingPlaylist(null)}>
                    <div className="bg-neutral-900 border border-neutral-800 w-full max-w-4xl h-[80vh] rounded-2xl flex flex-col overflow-hidden shadow-2xl" onClick={e => e.stopPropagation()}>

                        {/* Header */}
                        <div className="p-6 border-b border-neutral-800 flex items-center gap-6 bg-neutral-900 z-10">
                            <div className="relative w-32 h-32 shadow-2xl rounded-lg overflow-hidden shrink-0">
                                {viewingPlaylist.images?.[0] ? (
                                    <Image src={viewingPlaylist.images[0].url} fill className="object-cover" alt="" />
                                ) : <div className="w-full h-full bg-neutral-800" />}
                            </div>
                            <div>
                                <h2 className="text-3xl font-bold text-white mb-2">{viewingPlaylist.name}</h2>
                                <p className="text-neutral-400">By {viewingPlaylist.owner.display_name} • {viewingPlaylist.tracks.total} tracks</p>
                            </div>
                            <div className="ml-auto flex gap-3">
                                <button
                                    onClick={() => {
                                        // Select ALL
                                        const tracks = tracksCache.get(viewingPlaylist.id) || []
                                        const next = new Map(selectionModel)
                                        next.set(viewingPlaylist.id, { mode: 'ALL', selectedTracks: new Set() }) // Set empty = ALL by convention? Or just use mode
                                        setSelectionModel(next)
                                    }}
                                    className="px-4 py-2 bg-white text-black font-bold rounded-full hover:scale-105 transition"
                                >
                                    Select All
                                </button>
                                <button
                                    onClick={() => togglePlaylist(viewingPlaylist.id)}
                                    className="px-4 py-2 border border-neutral-600 text-white font-bold rounded-full hover:bg-neutral-800 transition"
                                >
                                    {selectionModel.has(viewingPlaylist.id) ? 'Deselect' : 'Select Playlist'}
                                </button>
                            </div>
                        </div>

                        {/* Track List */}
                        <div className="flex-1 overflow-y-auto p-2">
                            {loadingTracks ? (
                                <div className="flex h-full items-center justify-center flex-col gap-4 text-neutral-500">
                                    <Loader2 className="animate-spin" size={40} />
                                    <p>Loading tracks...</p>
                                </div>
                            ) : (
                                <table className="w-full text-left border-collapse">
                                    <thead className="text-neutral-500 text-sm sticky top-0 bg-neutral-900 border-b border-neutral-800">
                                        <tr>
                                            <th className="p-4 font-medium w-16">#</th>
                                            <th className="p-4 font-medium">Title</th>
                                            <th className="p-4 font-medium">Album</th>
                                            <th className="p-4 font-medium text-right"><CheckCircle size={16} /></th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {tracksCache.get(viewingPlaylist.id)?.map((track, i) => {
                                            const plSel = selectionModel.get(viewingPlaylist.id)
                                            const isSelected = plSel && (plSel.mode === 'ALL' || plSel.selectedTracks.has(track.uri))

                                            return (
                                                <tr
                                                    key={i}
                                                    className={clsx("hover:bg-neutral-800/50 group transition cursor-pointer", isSelected && "bg-neutral-800/30")}
                                                    onClick={() => {
                                                        // Toggle Track Logic
                                                        const next = new Map(selectionModel)
                                                        const currentSel = next.get(viewingPlaylist.id)

                                                        if (!currentSel || currentSel.mode === 'ALL') {
                                                            // If switching from ALL (or None) to Partial, initially select ALL except this one? 
                                                            // Or start with just this one? 
                                                            // Standard UX: Click logic usually toggles.
                                                            // If currently ALL, checking "off" one means Mode -> Partial, selected = All - 1.
                                                            // If currently None, checking "on" one means Mode -> Partial, selected = 1.

                                                            const allTracks = tracksCache.get(viewingPlaylist.id) || []

                                                            if (currentSel?.mode === 'ALL') {
                                                                // Was ALL, now user clicked one to DESELECT it (presumably?)
                                                                // Implementation: Switch to PARTIAL, add all EXCEPT this.
                                                                const newSet = new Set(allTracks.map(t => t.uri))
                                                                newSet.delete(track.uri)
                                                                next.set(viewingPlaylist.id, { mode: 'PARTIAL', selectedTracks: newSet })
                                                            } else {
                                                                // Was NONE, now user clicked one to SELECT it.
                                                                next.set(viewingPlaylist.id, { mode: 'PARTIAL', selectedTracks: new Set([track.uri]) })
                                                            }
                                                        } else {
                                                            // Already in PARTIAL mode
                                                            const newSet = new Set(currentSel.selectedTracks)
                                                            if (newSet.has(track.uri)) newSet.delete(track.uri)
                                                            else newSet.add(track.uri)

                                                            // If empty, removing playlist selection?
                                                            if (newSet.size === 0) next.delete(viewingPlaylist.id)
                                                            else next.set(viewingPlaylist.id, { mode: 'PARTIAL', selectedTracks: newSet })
                                                        }
                                                        setSelectionModel(next)
                                                    }}
                                                >
                                                    <td className="p-4 text-neutral-500 font-mono text-sm">{i + 1}</td>
                                                    <td className="p-4">
                                                        <div className="font-medium text-white">{track.name}</div>
                                                        <div className="text-sm text-neutral-400">{track.artist}</div>
                                                    </td>
                                                    <td className="p-4 text-neutral-400 text-sm">{track.album}</td>
                                                    <td className="p-4 text-right">
                                                        <div className={clsx(
                                                            "w-5 h-5 rounded-full border border-neutral-600 inline-flex items-center justify-center",
                                                            isSelected ? "bg-green-500 border-green-500" : "group-hover:border-white"
                                                        )}>
                                                            {isSelected && <div className="w-2 h-2 bg-black rounded-full" />}
                                                        </div>
                                                    </td>
                                                </tr>
                                            )
                                        })}
                                    </tbody>
                                </table>
                            )}
                        </div>
                    </div>
                </div>
            )}
            {/* Success Modal */}
            {showSuccess && (
                <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 backdrop-blur-sm">
                    <motion.div
                        initial={{ scale: 0.9, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        className="bg-neutral-900 border border-neutral-700 p-8 rounded-2xl max-w-md w-full text-center shadow-2xl"
                    >
                        <CheckCircle className="w-20 h-20 text-green-500 mx-auto mb-6" />
                        <h2 className="text-3xl font-bold text-white mb-2">All Done!</h2>
                        <p className="text-neutral-400 mb-8">
                            Your download is complete. You can enjoy your music now!
                        </p>
                        <div className="flex flex-col gap-3 w-full">
                            <button
                                onClick={() => {
                                    window.open('http://localhost:8000/api/zip', '_blank')
                                }}
                                className="bg-neutral-800 text-white font-bold py-3 px-8 rounded-full hover:bg-neutral-700 transition w-full text-lg border border-neutral-700 flex items-center justify-center gap-2"
                            >
                                <Download size={20} /> Download as ZIP
                            </button>
                            <button
                                onClick={() => setShowSuccess(false)}
                                className="bg-white text-black font-bold py-3 px-8 rounded-full hover:scale-105 transition w-full text-lg"
                            >
                                Awesome
                            </button>
                        </div>
                    </motion.div>
                </div>
            )}
        </div>
    )
}
