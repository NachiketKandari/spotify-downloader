'use client'
import { useSession, signIn, signOut } from "next-auth/react"
import { ShieldCheck, Music, Download, Upload } from "lucide-react"
import Image from "next/image"
import Dashboard from "./components/Dashboard"
import CSVUpload from "./components/CSVUpload"

export default function Home() {
    const { data: session } = useSession()

    if (session) {
        return (
            <main className="min-h-screen bg-neutral-900 text-white p-8">
                <div className="max-w-7xl mx-auto">
                    <div className="flex justify-between items-center mb-12">
                        <h1 className="text-3xl font-bold flex items-center gap-3">
                            <div className="relative w-10 h-10">
                                <Image
                                    src="/offlineify-logo.png"
                                    alt="Offlineify"
                                    fill
                                    className="object-contain"
                                />
                            </div>
                            <span>Offline<span className="text-green-500">ify</span></span>
                        </h1>
                        <div className="flex items-center gap-4">
                            <div className="text-neutral-400">Logged in as {session.user?.name || session.user?.email || 'User'}</div>
                            <button
                                onClick={() => signOut()}
                                className="px-4 py-2 bg-neutral-800 rounded-full hover:bg-neutral-700 transition"
                            >
                                Logout
                            </button>
                        </div>
                    </div>

                    <Dashboard
                        accessToken={session.accessToken as string}
                        userEmail={session.user?.email || 'unknown'}
                    />
                </div>
            </main>
        )
    }

    return (
        <main className="min-h-screen bg-black text-white">
            {/* Landing Section - Full Screen */}
            <div className="min-h-screen flex items-center justify-center p-8">
                <div className="text-center space-y-8 max-w-2xl w-full">
                    <div className="flex justify-center mb-8">
                        <div className="relative w-32 h-32">
                            <Image
                                src="/offlineify-logo.png"
                                alt="Offlineify Logo"
                                fill
                                className="object-contain"
                                priority
                            />
                        </div>
                    </div>
                    <h1 className="text-5xl font-bold tracking-tight">Offline<span className="text-green-500">ify</span></h1>
                    <p className="text-neutral-400 text-lg">
                        Export your playlists from Spotify directly to your local storage in high-quality MP3 (320kbps).
                    </p>

                    {/* Mode Toggle */}
                    <div className="flex flex-col md:flex-row gap-4 justify-center items-center">
                        <button
                            onClick={() => signIn("spotify")}
                            className="w-full md:w-auto bg-green-500 text-black px-8 py-4 rounded-full font-bold text-lg hover:bg-green-400 transition transform hover:scale-105 flex items-center justify-center gap-3"
                        >
                            <Music />
                            Login with Spotify
                        </button>

                        <div className="text-neutral-500 flex items-center text-2xl font-bold">OR</div>

                        <button
                            onClick={() => {
                                // Scroll to CSV upload section
                                document.getElementById('csv-section')?.scrollIntoView({ behavior: 'smooth' })
                            }}
                            className="w-full md:w-auto bg-neutral-800 text-white px-8 py-4 rounded-full font-bold text-lg hover:bg-neutral-700 transition transform hover:scale-105 flex items-center justify-center gap-3 border border-neutral-700"
                        >
                            <Upload />
                            Upload Playlist
                        </button>
                    </div>

                    <div className="grid grid-cols-3 gap-4 pt-12 text-sm text-neutral-500">
                        <div className="flex flex-col items-center gap-2">
                            <ShieldCheck /> Local Privacy
                        </div>
                        <div className="flex flex-col items-center gap-2">
                            <Music /> 320kbps Audio
                        </div>
                        <div className="flex flex-col items-center gap-2">
                            <Download /> Smart Downloads
                        </div>
                    </div>
                </div>
            </div>

            {/* CSV Upload Section - Full Screen */}
            <div id="csv-section" className="min-h-screen flex items-center justify-center p-8 border-t border-neutral-800">
                <div className="w-full max-w-4xl">
                    <div className="text-center mb-12">
                        <h2 className="text-4xl font-bold mb-4">Upload Spotify CSV</h2>
                        <p className="text-neutral-400 text-lg">
                            Don&apos;t want to login? Export your playlist as CSV from Spotify and upload it here.
                        </p>
                    </div>
                    <CSVUpload apiBase={process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'} />
                </div>
            </div>
        </main>
    );
}
