import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import './fonts.css';
import App from './App';
import './styles.css';
import './site.css';
import './typography.css';
import './components/button-motion.css';
import './components/workflow-motion.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><BrowserRouter><App /></BrowserRouter></React.StrictMode>,
);
