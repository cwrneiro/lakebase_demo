import { Link, Outlet } from 'react-router-dom'
import { Database } from 'lucide-react'
import { Toaster } from 'sonner'
import { RescoreButton } from './RescoreButton'

export function Layout() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-10 border-b border-[var(--color-border)] bg-[var(--color-card)]/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-3 px-6">
          <Link to="/" className="flex items-center gap-2 text-sm font-semibold">
            <Database className="h-5 w-5 text-[var(--color-accent)]" />
            <span>Lakebase Demo</span>
            <span className="ml-2 text-xs font-normal text-[var(--color-muted)]">
              operator queue
            </span>
          </Link>
          <RescoreButton />
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-8">
        <Outlet />
      </main>
      <Toaster position="top-right" />
    </div>
  )
}
