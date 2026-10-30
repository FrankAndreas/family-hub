import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development, forward API calls to the backend (port 8000, or API_PROXY for the browser tests); in Docker, nginx
// does this. Same origin either way, so the login cookie is the page's own.
const backend = process.env.API_PROXY || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': backend, '/.well-known': backend } },
})
