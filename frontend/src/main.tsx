import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

console.info('main.tsx: attempting to mount root...');
const rootElement = document.getElementById('root');
if (!rootElement) {
  console.error('CRITICAL: #root element not found in DOM!');
} else {
  createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
  );
}
