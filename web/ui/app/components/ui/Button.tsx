import { Loader2 } from 'lucide-react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'

/**
 * The one button in the app, styled Spotify-style: pill shape, bold label,
 * green for the primary action.
 *
 * Variants:
 *  - primary: green, the main action on a screen
 *  - secondary: outlined, alternative actions
 *  - danger: destructive actions (stop/cancel)
 *  - solid: white, peak emphasis (like Spotify's "Log in" button)
 *  - ghost: nav/icon buttons without a background
 */
type Variant = 'primary' | 'secondary' | 'danger' | 'solid' | 'ghost'
type Size = 'sm' | 'md' | 'lg'

const variantClasses: Record<Variant, string> = {
    primary: 'bg-accent text-black hover:bg-accent-hover active:bg-accent-pressed',
    secondary: 'border border-line-strong/60 text-content hover:border-white hover:bg-surface-overlay',
    danger: 'bg-danger text-white hover:bg-danger-hover',
    solid: 'bg-white text-black hover:scale-[1.03] active:scale-100',
    ghost: 'text-content-muted hover:text-content hover:bg-surface-overlay',
}

const sizeClasses: Record<Size, string> = {
    sm: 'px-3 py-1.5 text-xs',
    md: 'px-4 py-2 text-sm',
    lg: 'px-8 py-3.5 text-base',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: Variant
    size?: Size
    loading?: boolean
    icon?: ReactNode
}

export default function Button({
    variant = 'primary',
    size = 'md',
    loading = false,
    icon,
    children,
    className = '',
    disabled,
    ...rest
}: ButtonProps) {
    return (
        <button
            {...rest}
            disabled={disabled || loading}
            className={`inline-flex items-center justify-center gap-2 rounded-full font-bold tracking-tight transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
        >
            {loading ? <Loader2 size={16} className="animate-spin" /> : icon}
            {children}
        </button>
    )
}
