import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig(({mode})=>({base:mode==='pages'?'/Gold-Trading-Project/':'/',build:{outDir:mode==='pages'?'dist-pages':'dist'},plugins:[react()], server:{host:'127.0.0.1',port:5173,strictPort:true,proxy:{'/api':{target:'http://127.0.0.1:8765',changeOrigin:true}}}}));
