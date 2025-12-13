'use client'
import { useSession, signIn, signOut } from "next-auth/react"
import { ShieldCheck, Music, Download } from "lucide-react"
import Dashboard from "./components/Dashboard"

export default function Home() {
    const { data: session } = useSession()

    if (session) {
        return (
            <main className="min-h-screen bg-neutral-900 text-white p-8">
                <div className="max-w-7xl mx-auto">
                    <div className="flex justify-between items-center mb-12">
                        <h1 className="text-3xl font-bold flex items-center gap-3">
                            <Music className="text-green-500" /> Offline<span className="text-green-500">ify</span>
                        </h1>
                        <div className="flex items-center gap-4">
                            <div className="text-neutral-400">Logged in as {session.user?.name}</div>
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
        <main className="min-h-screen bg-black text-white flex items-center justify-center">
            <div className="text-center space-y-8 max-w-lg p-8">
                <div className="flex justify-center mb-8">
                    <Music size={64} className="text-green-500" />
                </div>
                <h1 className="text-5xl font-bold tracking-tight">Offline<span className="text-green-500">ify</span></h1>
                <p className="text-neutral-400 text-lg">
                    Export your playlists from Spotify directly to your local storage in high-quality MP3 (320kbps).
                </p>

                <button
                    onClick={() => signIn("spotify")}
                    className="bg-green-500 text-black px-8 py-4 rounded-full font-bold text-xl hover:bg-green-400 transition transform hover:scale-105 flex items-center gap-3 mx-auto"
                >
                    Login with Spotify
                </button>

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
        </main>
    );
}
