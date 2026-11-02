import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
const css=()=>readFileSync(new URL('../src/chartWorkspace.css',import.meta.url),'utf8');
const rule=(selector:string)=>css().match(new RegExp(selector.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'\\{([^}]+)\\}'))?.[1]??'';
test('chart canvas cannot contribute intrinsic height back to its auto-sized container',()=>{
 const plot=rule('.gd-chart-plot');assert.match(plot,/min-height:0/);assert.match(plot,/overflow:hidden/);
 const canvas=rule('.gd-chart-plot>.chart-canvas');assert.match(canvas,/position:absolute/);assert.match(canvas,/inset:0/);
 assert.match(rule('.gd-chart-plot>.cw-analysis-canvas'),/position:absolute/);
});
test('case comparison uses a viewport-bounded workspace rather than an indefinite percent height',()=>{
 assert.match(rule('.cw-comparison-grid .gd-chart-workspace'),/height:clamp\(\d+px,[^,]+,\d+px\)!important/);
 assert.match(rule('.gd-chart-tools'),/flex-shrink:0/);
});
test('fullscreen comparison overrides the normal bounded card height',()=>{
 assert.match(rule('.cw-comparison-grid .gd-chart-workspace:fullscreen'),/height:100dvh!important/);
});
