import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import AdminPage from './AdminPage.tsx'
import DevPage from './DevPage.tsx'

const path = window.location.pathname
const isDevRoute = /^\/dev(\/|$|\?)/.test(path)
const isAdminRoute = /^\/admin(\/|$|\?)/.test(path)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isDevRoute ? <DevPage /> : isAdminRoute ? <AdminPage /> : <App />}
  </StrictMode>,
)