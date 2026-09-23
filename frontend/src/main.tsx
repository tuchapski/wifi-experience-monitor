import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import AgentWorkspace from './AgentWorkspace.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AgentWorkspace />
  </StrictMode>,
)
