/**
 * Client side of the optional shared-password guard.
 *
 * The backend operator sets OFFLINEIFY_PASSWORD; the browser asks for it once
 * and keeps the derived HTTP Basic token in localStorage. Fetches send it as
 * an Authorization header (apiFetch); download links opened via `<a href>` or
 * window.open() carry it as `?key=` (withAccessKey) because they cannot set
 * headers.
 */

const STORAGE_KEY = 'offlineify_access_token'

/** base64("offlineify:<password>"), UTF-8 safe. */
export const basicToken = (password: string): string => {
    const bytes = new TextEncoder().encode(`offlineify:${password}`)
    let binary = ''
    bytes.forEach(b => { binary += String.fromCharCode(b) })
    return btoa(binary)
}

export const getAccessToken = (): string | null => {
    if (typeof window === 'undefined') return null
    return window.localStorage.getItem(STORAGE_KEY)
}

export const setAccessPassword = (password: string) => {
    window.localStorage.setItem(STORAGE_KEY, basicToken(password))
}

export const clearAccess = () => {
    window.localStorage.removeItem(STORAGE_KEY)
}

/** fetch() with the stored access token attached. */
export const apiFetch = (input: string, init: RequestInit = {}): Promise<Response> => {
    const headers = new Headers(init.headers || {})
    const token = getAccessToken()
    if (token) headers.set('Authorization', `Basic ${token}`)
    return fetch(input, { ...init, headers })
}

/** Add ?key= to a URL that will be opened via <a href> or window.open(). */
export const withAccessKey = (url: string): string => {
    const token = getAccessToken()
    if (!token) return url
    return `${url}${url.includes('?') ? '&' : '?'}key=${encodeURIComponent(token)}`
}
