'use client'
import { useState } from 'react'
import { Upload, Download, Loader2, CheckCircle, X, Music } from 'lucide-react'
import { motion } from 'framer-motion'

interface CSVUploadProps {
    apiBase: string
}

export default function CSVUpload({ apiBase }: CSVUploadProps) {
    const [file, setFile] = useState<File | null>(null)
    const [uploading, setUploading] = useState(false)
    const [downloading, setDownloading] = useState(false)
    const [status, setStatus] = useState<any>(null)
    const [quality, setQuality] = useState('320')
    // Generate unique session ID for this upload instance
    const [userId] = useState(() => `csv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`)

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files[0]) {
            setFile(e.target.files[0])
        }
    }

    const handleUpload = async () => {
        if (!file) return

        setUploading(true)
        setDownloading(true)
        setStatus({ status: 'starting', logs: [] })

        try {
            const formData = new FormData()
            formData.append('file', file)
            formData.append('quality', quality)
            formData.append('user_id', userId)

            const response = await fetch(`${apiBase}/api/csv-download`, {
                method: 'POST',
                body: formData
            })

            const data = await response.json()
            console.log('Upload response:', data)

            // Start polling for status
            pollStatus()
        } catch (e) {
            console.error('Upload error:', e)
            setUploading(false)
            setDownloading(false)
        } finally {
            setUploading(false)
        }
    }

    const pollStatus = () => {
        const interval = setInterval(async () => {
            try {
                const res = await fetch(`${apiBase}/api/status?user_id=${userId}`)
                const data = await res.json()
                setStatus(data)

                if (data.status === 'done' || data.status === 'cancelled' || data.status === 'idle') {
                    clearInterval(interval)
                    setDownloading(false)
                }
            } catch (e) {
                console.error('Status poll error:', e)
            }
        }, 1000)
    }

    const handleCancel = async () => {
        try {
            await fetch(`${apiBase}/api/cancel?user_id=${userId}`, { method: 'POST' })
        } catch (e) {
            console.error('Cancel error:', e)
        }
    }

    return (
        <div className="w-full max-w-2xl mx-auto space-y-8">
            {/* File Upload Section */}
            <div className="bg-neutral-800 border-2 border-dashed border-neutral-600 rounded-2xl p-8">
                <div className="text-center space-y-4">
                    <Upload className="mx-auto text-neutral-400" size={48} />
                    <div>
                        <h3 className="text-xl font-bold text-white mb-2">Upload Spotify CSV</h3>
                        <p className="text-neutral-400 text-sm">
                            Export your playlist from Spotify and upload the CSV file here
                        </p>
                    </div>

                    <input
                        type="file"
                        accept=".csv"
                        onChange={handleFileChange}
                        className="hidden"
                        id="csv-upload"
                        disabled={downloading}
                    />

                    <label
                        htmlFor="csv-upload"
                        className="inline-block bg-neutral-700 hover:bg-neutral-600 text-white px-6 py-3 rounded-lg font-medium cursor-pointer transition disabled:opacity-50"
                    >
                        {file ? file.name : 'Choose CSV File'}
                    </label>

                    {file && (
                        <div className="flex items-center justify-center gap-4 pt-4">
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
                    )}
                </div>
            </div>

            {/* Action Buttons */}
            {file && !downloading && (
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="flex gap-4"
                >
                    <button
                        onClick={handleUpload}
                        disabled={uploading || downloading}
                        className="flex-1 bg-green-500 text-black px-8 py-4 rounded-xl font-bold text-lg hover:bg-green-400 transition disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                        {uploading ? <Loader2 className="animate-spin" /> : <Download />}
                        {uploading ? 'Starting...' : 'Start Download'}
                    </button>
                    <button
                        onClick={() => setFile(null)}
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
                                            href={`${apiBase}/api/file?path=${encodeURIComponent(file.path)}&user_id=${userId}`}
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

                    {/* Download All as ZIP */}
                    {status.status === 'done' && status.completed_files?.length > 0 && (
                        <div className="mt-4">
                            <button
                                onClick={() => window.open(`${apiBase}/api/zip?user_id=${userId}`, '_blank')}
                                className="w-full bg-green-500 text-black font-bold py-3 px-6 rounded-xl hover:bg-green-400 transition flex items-center justify-center gap-2"
                            >
                                <Download size={20} /> Download All as ZIP
                            </button>
                        </div>
                    )}
                </div>
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
                    <p className="text-neutral-400 mb-4">All {status.completed} tracks downloaded successfully</p>
                    <button
                        onClick={() => {
                            setFile(null)
                            setStatus(null)
                        }}
                        className="bg-white text-black px-6 py-2 rounded-full font-bold hover:scale-105 transition"
                    >
                        Upload Another CSV
                    </button>
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
                        Downloaded {status.completed} of {status.total} tracks before stopping
                    </p>
                    <div className="flex gap-3 justify-center">
                        <button
                            onClick={() => window.open(`${apiBase}/api/zip?user_id=${userId}`, '_blank')}
                            className="bg-green-500 text-black px-6 py-2 rounded-full font-bold hover:scale-105 transition"
                        >
                            Download Completed Files
                        </button>
                        <button
                            onClick={() => {
                                setFile(null)
                                setStatus(null)
                            }}
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
