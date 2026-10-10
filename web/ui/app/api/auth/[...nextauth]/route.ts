import NextAuth from "next-auth"
import SpotifyProvider from "next-auth/providers/spotify"
import { JWT } from "next-auth/jwt"

async function refreshAccessToken(token: JWT) {
    try {
        const url = "https://accounts.spotify.com/api/token"
        const response = await fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
                Authorization: "Basic " + (Buffer.from(process.env.SPOTIFY_CLIENT_ID + ":" + process.env.SPOTIFY_CLIENT_SECRET).toString("base64")),
            },
            body: new URLSearchParams({
                grant_type: "refresh_token",
                refresh_token: token.refreshToken as string,
            }),
        })

        const refreshedTokens = await response.json()

        if (!response.ok) {
            throw refreshedTokens
        }

        return {
            ...token,
            accessToken: refreshedTokens.access_token,
            accessTokenExpires: Date.now() + refreshedTokens.expires_in * 1000,
            refreshToken: refreshedTokens.refresh_token ?? token.refreshToken, // Fall back to old refresh token
        }
    } catch (error) {
        console.log("RefreshAccessTokenError", error)
        return {
            ...token,
            error: "RefreshAccessTokenError",
        }
    }
}

const handler = NextAuth({
    providers: [
        SpotifyProvider({
            clientId: process.env.SPOTIFY_CLIENT_ID!,
            clientSecret: process.env.SPOTIFY_CLIENT_SECRET!,
            authorization: { params: { scope: "user-read-email playlist-read-private playlist-read-collaborative user-library-read" } },
        }),
    ],
    callbacks: {
        async jwt({ token, account, user }) {
            // Initial sign in
            if (account && user) {
                return {
                    accessToken: account.access_token,
                    // Spotify reports expiry as `expires_at`: an absolute Unix
                    // timestamp in seconds. Treating it as a duration made the
                    // token look valid until the year ~2083, so after the first
                    // hour a dead token was silently reused: the backend got a
                    // 401 and fell back to Spotify's 50-track embed page while
                    // the UI still said "logged in". Store real epoch ms.
                    accessTokenExpires: ((account.expires_at as number) ??
                        Math.floor(Date.now() / 1000) + (account.expires_in as number ?? 3600)) * 1000,
                    refreshToken: account.refresh_token,
                    user,
                }
            }

            // Return previous token if the access token has not expired yet
            // @ts-ignore
            if (Date.now() < token.accessTokenExpires) {
                return token
            }

            // Access token has expired, try to update it
            return refreshAccessToken(token)
        },
        async session({ session, token }) {
            // @ts-ignore
            session.accessToken = token.accessToken
            // @ts-ignore
            session.error = token.error
            return session
        },
    },
})

export { handler as GET, handler as POST }
