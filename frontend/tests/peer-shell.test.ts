import test from 'node:test';import assert from 'node:assert/strict';
import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import {readFileSync} from 'node:fs';import DeskRouteFrame from '../src/DeskRouteFrame';
import {trustedPreviewOrigin} from '../previewProxy';
test('all three routes use the peer rail and stable shell without a login gate',()=>{
 for(const view of ['assistant','live','replay'] as const){
  const html=renderToStaticMarkup(createElement(DeskRouteFrame,{view,market:null,light:false,publicMode:false,busy:false,onNavigate:()=>{},onSection:()=>{},onToggleTheme:()=>{},children:createElement('div',null,'retained child')}));
  assert.match(html,/ag-shell/);assert.match(html,/ag-rail/);assert.match(html,/retained child/);
  assert.doesNotMatch(html,/登入才能|已連線|48830|2357\.62/);
 }
});
test('preview forwards only exact trusted loopback origins, never arbitrary websites',()=>{
 for(const origin of ['http://127.0.0.1:8766','http://localhost:8766','http://127.0.0.1:5173'])assert.equal(trustedPreviewOrigin(origin),'http://127.0.0.1:8765');
 for(const origin of [undefined,'null','https://evil.example','http://127.0.0.1.evil.example:8766','http://localhost:9999'])assert.equal(trustedPreviewOrigin(origin),undefined);
});
test('peer preview is a strict 8766 frontend proxy and never a second broker backend',()=>{
 const config=JSON.parse(readFileSync(new URL('../package.json',import.meta.url),'utf8'));
 assert.match(config.scripts['dev:peer']??'',/--port 8766/);assert.match(config.scripts['dev:peer']??'',/--strictPort/);
 assert.match(readFileSync(new URL('../vite.config.ts',import.meta.url),'utf8'),/127\.0\.0\.1:8765/);
});
