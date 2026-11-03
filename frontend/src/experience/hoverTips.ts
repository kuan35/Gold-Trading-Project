// One floating tooltip for the whole app: hover (or keyboard focus) shows what a control does.
// Sources, in order: data-tip, title (moved to data-tip so the slow native tooltip never shows),
// then aria-label on icon-only buttons.
const DELAY = 250;

function tipText(el: HTMLElement): string {
 if (el.title) { el.dataset.tip = el.title; el.removeAttribute('title'); }
 if (el.dataset.tip) return el.dataset.tip;
 const label = el.getAttribute('aria-label');
 return label && !el.textContent?.trim() ? label : '';
}

export function installHoverTips(): void {
 if (typeof document === 'undefined' || document.getElementById('gx-tip')) return;
 const tip = document.createElement('div');
 tip.id = 'gx-tip'; tip.className = 'gx-tip'; tip.setAttribute('role', 'tooltip');
 document.body.appendChild(tip);
 let timer = 0, current: HTMLElement | null = null;
 const hide = () => { window.clearTimeout(timer); current = null; tip.classList.remove('gx-tip-on'); };
 const place = (el: HTMLElement) => {
  const r = el.getBoundingClientRect(), t = tip.getBoundingClientRect(), side = el.dataset.tipSide;
  let x = r.left + r.width / 2 - t.width / 2, y = r.top - t.height - 10;
  if (side === 'right') { x = r.right + 12; y = r.top + r.height / 2 - t.height / 2; }
  else if (y < 8) y = r.bottom + 10;
  tip.style.left = `${Math.max(8, Math.min(x, innerWidth - t.width - 8))}px`;
  tip.style.top = `${Math.max(8, Math.min(y, innerHeight - t.height - 8))}px`;
  tip.dataset.side = side === 'right' ? 'right' : y > r.top ? 'bottom' : 'top';
 };
 const show = (el: HTMLElement) => {
  const text = tipText(el); if (!text) return;
  current = el; window.clearTimeout(timer);
  timer = window.setTimeout(() => { if (current !== el || !el.isConnected) return; tip.textContent = text; place(el); tip.classList.add('gx-tip-on'); }, DELAY);
 };
 const target = (e: Event) => (e.target as HTMLElement | null)?.closest?.('[data-tip],[title],button[aria-label],a[aria-label]') as HTMLElement | null;
 document.addEventListener('pointerover', e => { const el = target(e); if (el && el !== current) show(el); else if (!el) hide(); }, true);
 document.addEventListener('focusin', e => { const el = target(e); if (el && (e.target as HTMLElement).matches(':focus-visible')) show(el); }, true);
 document.addEventListener('focusout', hide, true);
 document.addEventListener('pointerdown', hide, true);
 document.addEventListener('scroll', hide, true);
 document.addEventListener('keydown', e => { if (e.key === 'Escape') hide(); }, true);
}
