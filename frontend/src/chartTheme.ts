// Shared display palette only; market values and retrieval features are unchanged.
export const chartTheme=(light:boolean)=>({
 background:light?'#ffffff':'#141a21',text:light?'#45515f':'#aeb8c7',grid:light?'#e6e9ec':'#29323e',
 crosshair:light?'#79521a':'#806637',up:light?'#087b58':'#59d8a7',down:light?'#b62d43':'#f58c93',
 volumeUp:light?'#087b5845':'#59d8a745',volumeDown:light?'#b62d4345':'#f58c9345',ma20:light?'#8a5c15':'#e4bd77',ma60:light?'#456a91':'#8eafcb',
});
