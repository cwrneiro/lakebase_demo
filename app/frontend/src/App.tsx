import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Layout } from '@/components/Layout'
import { UserList } from '@/pages/UserList'
import { UserDetail } from '@/pages/UserDetail'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<UserList />} />
          <Route path="/users/:userId" element={<UserDetail />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

function NotFound() {
  return (
    <div className="py-24 text-center text-[var(--color-muted)]">
      <h2 className="text-lg font-semibold">Page not found</h2>
      <p className="mt-1 text-sm">Try the operator queue.</p>
    </div>
  )
}
