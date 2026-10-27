import React from 'react';
import {createRoot} from 'react-dom/client';
import App from './App';
import './styles.css';
import './workspaceRefresh.css';
import './productDesk.css';
import './secondaryPages.css';
import './caseOutcomes.css';
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
