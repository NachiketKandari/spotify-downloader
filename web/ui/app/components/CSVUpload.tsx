'use client'
import { useState } from 'react'
import { Upload, Download, X } from 'lucide-react'
import { motion } from 'framer-motion'
import Button from './ui/Button'
import Card from './ui/Card'
import { Field, Select } from './ui/Field'
import StatusPanel from './ui/StatusPanel'
import OutcomePanel from './ui/OutcomePanel'

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

            if (!response.ok) {
                const data = await response.json().catch(() => ({}))
                setStatus({ status: 'error', logs: [data.detail || 'CSV upload failed'] })
                setUploading(false)
                setDownloading(false)
                return
            }

            pollStatus()
        } catch (e) {
            console.error('Upload error:', e)
            setStatus({ status: 'error', logs: ['Backend unreachable'] })
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

                if (data.status === 'done' || data.status === 'cancelled' || data.status === 'error') {
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

    const saveUrl = (f: { name: string, path: string }) =>
        `${apiBase}/api/file?path=${encodeURIComponent(f.path)}&user_id=${userId}`

    return (
        <div className="w-full max-w-2xl mx-auto space-y-8">
            {/* File picker */}
            <Card padding="lg" className="border-dashed border-line-strong">
                <div className="text-center space-y-4">
                    <Upload className="mx-auto text-content-faint" size={48} />
                    <div>
                        <h3 className="text-xl font-bold text-content mb-2">Upload Spotify CSV</h3>
                        <p className="text-content-muted text-sm">
                            Export your playlist as CSV and upload the file here
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
                        className="inline-block bg-surface-input hover:bg-surface-overlay text-content px-6 py-3 rounded-full font-bold cursor-pointer transition-colors"
                    >
                        {file ? file.name : 'Choose CSV File'}
                    </label>

                    {file && (
                        <div className="flex justify-center pt-2">
                            <Field label="Quality:">
                                <Select value={quality} onChange={(e) => setQuality(e.target.value)} disabled={downloading}>
                                    <option value="320">High (320kbps)</option>
                                    <option value="192">Standard (192kbps)</option>
                                </Select>
                            </Field>
                        </div>
                    )}
                </div>
            </Card>

            {/* Start / clear */}
            {file && !downloading && status?.status !== 'done' && status?.status !== 'cancelled' && status?.status !== 'error' && (
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="flex gap-4">
                    <Button
                        variant="primary"
                        size="lg"
                        loading={uploading}
                        icon={<Download />}
                        onClick={handleUpload}
                        className="flex-1"
                    >
                        {uploading ? 'Starting...' : 'Start Download'}
                    </Button>
                    <Button variant="secondary" size="lg" onClick={() => setFile(null)} icon={<X />} aria-label="Clear file" />
                </motion.div>
            )}

            {/* Progress */}
            {downloading && status && (
                <StatusPanel
                    status={status}
                    onCancel={handleCancel}
                    onZip={() => window.open(`${apiBase}/api/zip?user_id=${userId}`, '_blank')}
                    zipLabel="Download All as ZIP"
                    saveUrl={saveUrl}
                />
            )}

            {/* Error */}
            {status?.status === 'error' && !downloading && (
                <OutcomePanel
                    tone="danger"
                    title="Could Not Start"
                    body={status.logs?.[0] || 'Something went wrong'}
                    actionLabel="Try Again"
                    onAction={() => { setStatus(null); setFile(null) }}
                />
            )}

            {/* Success */}
            {status?.status === 'done' && !downloading && (
                <OutcomePanel
                    tone="success"
                    title="Download Complete!"
                    body={`${status.completed_files?.length || 0} of ${status.total} tracks downloaded`}
                    actionLabel="Upload Another CSV"
                    onAction={() => { setFile(null); setStatus(null) }}
                    zipUrl={status.completed_files?.length > 0 ? `${apiBase}/api/zip?user_id=${userId}` : undefined}
                />
            )}

            {/* Cancelled */}
            {status?.status === 'cancelled' && !downloading && (
                <OutcomePanel
                    tone="warning"
                    title="Download Stopped"
                    body={`Downloaded ${status.completed_files?.length || 0} of ${status.total} tracks before stopping`}
                    actionLabel="Start New"
                    onAction={() => { setFile(null); setStatus(null) }}
                    zipUrl={status.completed_files?.length > 0 ? `${apiBase}/api/zip?user_id=${userId}` : undefined}
                    zipLabel="Download Completed Files"
                />
            )}
        </div>
    )
}
