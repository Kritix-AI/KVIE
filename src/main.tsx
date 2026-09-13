import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import FloatingWindowApp from './FloatingWindowApp'
import './styles/global.css'

const isFloatingWindow = window.location.search.includes('window=floating') || window.location.hash === '#floating'

if (isFloatingWindow) {
  const doc = window.document || document
  doc.documentElement.classList.add('floating-window-mode')
  document.body.classList.add('floating-window-mode')
  doc.documentElement.style.background = 'transparent'
  document.body.style.background = 'transparent'
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {isFloatingWindow ? <FloatingWindowApp /> : <App />}
  </React.StrictMode>
)