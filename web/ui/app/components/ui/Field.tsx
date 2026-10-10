import type { InputHTMLAttributes, SelectHTMLAttributes, ReactNode } from 'react'

const base =
    'w-full bg-surface-input text-content rounded-md px-4 py-3 border border-line-strong/40 hover:border-content-faint focus:border-white focus:outline-none placeholder:text-content-faint transition-colors'

export function Input({ className = '', ...rest }: InputHTMLAttributes<HTMLInputElement>) {
    return <input {...rest} className={`${base} ${className}`} />
}

export function Select({ className = '', children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
    return (
        <select {...rest} className={`${base} py-2 pr-8 cursor-pointer ${className}`}>
            {children}
        </select>
    )
}

/** Label + control pair used across the forms. */
export function Field({ label, children }: { label: string, children: ReactNode }) {
    return (
        <label className="flex items-center gap-2 text-sm text-content-muted">
            {label}
            {children}
        </label>
    )
}
