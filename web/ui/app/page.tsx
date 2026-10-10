'use client'
import { useEffect, useState } from 'react'
import { useSession, signIn, signOut } from "next-auth/react"
import { Home as HomeIcon, ListMusic, Link2, Upload, LogOut, Music, ShieldCheck, Download } from "lucide-react"
import Image from "next/image"
import Dashboard from "./components/Dashboard"
import CSVUpload from "./components/CSVUpload"
import LinkDownload from "./components/LinkDownload"

type View = 'home' | 'playlists' | 'link' | 'csv'

const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

export default function Home() {
    const { data: session } = useSession()
    const [view, setView] = useState<View>('home')

    // Logging in swaps the "Home" tab for "My Playlists"; logging out resets.
    useEffect(() => {
        if (session) setView(current => (current === 'home' ? 'playlists' : current))
        else setView(current => (current === 'playlists' ? 'home' : current))
    }, [session])

    const tabs: { id: View, label: string, icon: React.ReactNode }[] = [
        ...(session
            ? [{ id: 'playlists' as View, label: 'My Playlists', icon: <ListMusic size={16} /> }]
            : [{ id: 'home' as View, label: 'Home', icon: <HomeIcon size={16} /> }]),
        { id: 'link', label: 'Paste Link', icon: <Link2 size={16} /> },
        { id: 'csv', label: 'Upload CSV', icon: <Upload size={16} /> },
    ]

    const tabClass = (id: View) =>
        `flex items-center gap-2 px-3 md:px-4 py-2 rounded-full text-sm font-bold transition-all duration-150 whitespace-nowrap ${
            view === id
                ? 'bg-accent text-black'
                : 'text-content-muted hover:text-content'
        }`

    const tabLabel = (id: View, label: string) => {
        const short = id === 'link' ? 'Link' : id === 'csv' ? 'CSV' : id === 'home' ? '' : label
        return (
            <>
                <span className="hidden md:inline">{label}</span>
                <span className="md:hidden">{short}</span>
            </>
        )
    }

    return (
        <main className="min-h-screen bg-surface-base text-content">
            {/* Navigation */}
            <nav className="sticky top-0 z-40 bg-surface-base/95 backdrop-blur border-b border-line/70">
                <div className="max-w-page mx-auto px-4 md:px-8 h-16 flex items-center gap-4">
                    <button
                        onClick={() => setView(session ? 'playlists' : 'home')}
                        className="flex items-center gap-2 shrink-0"
                    >
                        <div className="relative w-8 h-8">
                            <Image src="/offlineify-logo.png" alt="Offlineify" fill className="object-contain" />
                        </div>
                        <span className="text-xl font-bold hidden sm:block">
                            Offline<span className="text-accent">ify</span>
                        </span>
                    </button>

                    <div className="flex items-center gap-1 md:gap-2 mx-auto">
                        {tabs.map(tab => (
                            <button key={tab.id} onClick={() => setView(tab.id)} className={tabClass(tab.id)}>
                                {tab.icon}
                                {tabLabel(tab.id, tab.label)}
                            </button>
                        ))}
                    </div>

                    <div className="flex items-center gap-3 shrink-0">
                        {session ? (
                            <>
                                <span className="text-content-muted text-sm hidden md:block max-w-[160px] truncate">
                                    {session.user?.name || session.user?.email || 'User'}
                                </span>
                                <button
                                    onClick={() => signOut()}
                                    className="flex items-center gap-2 px-3 py-2 rounded-full text-sm font-bold text-content-muted hover:text-content transition-colors"
                                >
                                    <LogOut size={16} />
                                    <span className="hidden md:inline">Logout</span>
                                </button>
                            </>
                        ) : (
                            <button
                                onClick={() => signIn("spotify")}
                                className="flex items-center gap-2 bg-white text-black px-4 py-2 rounded-full font-bold text-sm hover:scale-[1.03] transition-transform"
                            >
                                <Music size={16} />
                                Login
                            </button>
                        )}
                    </div>
                </div>
            </nav>

            {/* Content */}
            <div className="max-w-page mx-auto px-4 md:px-8 py-8 md:py-10">
                {view === 'home' && <HomeView />}

                {view === 'playlists' && session && (
                    <Dashboard
                        accessToken={session.accessToken as string}
                        userEmail={session.user?.email || 'unknown'}
                        authError={(session as any).error}
                    />
                )}

                {view === 'link' && <LinkView accessToken={session?.accessToken as string | undefined} />}

                {view === 'csv' && <CsvView />}
            </div>
        </main>
    )
}

function HomeView() {
    return (
        <div className="flex flex-col items-center justify-center text-center py-12 md:py-20 space-y-8">
            <div className="relative w-28 h-28">
                <Image src="/offlineify-logo.png" alt="Offlineify Logo" fill className="object-contain" priority />
            </div>

            <div className="space-y-4 max-w-2xl">
                <h1 className="text-4xl md:text-5xl font-bold tracking-tight">
                    Offline<span className="text-accent">ify</span>
                </h1>
                <p className="text-content-muted text-lg text-balance">
                    Export your Spotify playlists to your laptop as MP3s with cover art and tags.
                    Three ways in, pick whichever suits you.
                </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 w-full max-w-4xl pt-4">
                <MethodCard
                    title="Log in with Spotify"
                    description="See all your playlists, including Liked Songs and private ones. Pick tracks individually."
                />
                <MethodCard
                    title="Paste a link"
                    description="Have a playlist URL? Paste it and download the whole thing as a ZIP. No login needed."
                />
                <MethodCard
                    title="Upload a CSV"
                    description="Exported your playlist elsewhere? Drop the CSV in and download it."
                />
            </div>

            <div className="flex flex-wrap items-center justify-center gap-6 pt-6 text-sm text-content-faint">
                <span className="flex items-center gap-2"><ShieldCheck size={16} /> Runs on your machine</span>
                <span className="flex items-center gap-2"><Music size={16} /> MP3 with album art</span>
                <span className="flex items-center gap-2"><Download size={16} /> One-click ZIP</span>
            </div>
        </div>
    )
}

function MethodCard({ title, description }: { title: string, description: string }) {
    return (
        <div className="bg-surface-raised border border-line/70 rounded-card p-6 text-left space-y-2 transition-colors hover:bg-surface-overlay">
            <h3 className="font-bold text-content">{title}</h3>
            <p className="text-content-muted text-sm">{description}</p>
        </div>
    )
}

function LinkView({ accessToken }: { accessToken?: string }) {
    return (
        <div className="max-w-2xl mx-auto">
            <div className="text-center mb-10">
                <h2 className="text-3xl font-bold mb-3">Paste a Playlist Link</h2>
                <p className="text-content-muted">
                    Paste any public Spotify playlist link and download it as a ZIP.
                    {accessToken
                        ? ' Logged in: full playlists, including your own private ones.'
                        : ' Without login, Spotify shares the first 50 tracks; log in for full playlists.'}
                </p>
            </div>
            <LinkDownload apiBase={API_BASE} accessToken={accessToken} />
        </div>
    )
}

function CsvView() {
    return (
        <div className="max-w-2xl mx-auto">
            <div className="text-center mb-10">
                <h2 className="text-3xl font-bold mb-3">Upload a Spotify CSV</h2>
                <p className="text-content-muted">
                    Export your playlist as CSV (for example with the dashboard&apos;s Export CSV button) and upload it here.
                </p>
            </div>
            <CSVUpload apiBase={API_BASE} />
        </div>
    )
}
