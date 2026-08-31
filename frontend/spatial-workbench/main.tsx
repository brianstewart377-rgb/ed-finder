import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { SpatialWorkbench } from './workbench';
import './style.css';
createRoot(document.getElementById('root')!).render(<StrictMode><SpatialWorkbench /></StrictMode>);
