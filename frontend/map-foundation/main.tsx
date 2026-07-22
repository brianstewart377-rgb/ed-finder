import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { MapFoundationWorkbench } from './workbench';
import './style.css';

createRoot(document.getElementById('root')!).render(<StrictMode><MapFoundationWorkbench /></StrictMode>);
