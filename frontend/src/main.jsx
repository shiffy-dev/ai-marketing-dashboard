import React from 'react'
import ReactDOM from 'react-dom/client'
import { SWRConfig } from 'swr'
import App from './App.jsx'
import { fetcher } from './api.js'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <SWRConfig value={{ fetcher, revalidateOnFocus: false, shouldRetryOnError: false }}>
      <App />
    </SWRConfig>
  </React.StrictMode>,
)
