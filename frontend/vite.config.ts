import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import {PREVIEW_ORIGINS,trustedPreviewOrigin} from './previewProxy';
export default defineConfig(({mode})=>({
 base:mode==='pages'?'/Gold-Trading-Project/':'/',
 build:{outDir:mode==='pages'?'dist-pages':'dist'},
 plugins:[react(),{name:'gold-loopback-preview',configureServer(server){
  server.middlewares.use('/api',(request,response,next)=>{
   if(!['GET','HEAD','OPTIONS'].includes(request.method??'GET')&&!trustedPreviewOrigin(request.headers.origin)){
    response.statusCode=403;response.setHeader('Content-Type','application/json');response.end(JSON.stringify({detail:'僅允許指定本機預覽來源'}));return;
   }next();
  });
 }}],
 server:{host:'127.0.0.1',port:5173,strictPort:true,allowedHosts:['localhost','127.0.0.1'],cors:{origin:PREVIEW_ORIGINS},proxy:{'/api':{
  target:'http://127.0.0.1:8765',changeOrigin:true,
  configure(proxy){proxy.on('proxyReq',(outgoing,incoming)=>{const origin=trustedPreviewOrigin(incoming.headers.origin);if(origin)outgoing.setHeader('Origin',origin);});}
 }}},
}));
