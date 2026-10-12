export const DEFAULT_WIDTH=336,MIN_WIDTH=288,MAX_WIDTH=440;
export const LAYOUT_KEY='gold-order-panel-width-v1';
export function panelWidth(value:string|null):number {
  const width=Number(value);
  return Number.isFinite(width)&&width>0?Math.max(MIN_WIDTH,Math.min(MAX_WIDTH,Math.round(width))):DEFAULT_WIDTH;
}
export function resizeWidth(start:number,delta:number):number {
  return Math.max(MIN_WIDTH,Math.min(MAX_WIDTH,Math.round(start-delta)));
}
