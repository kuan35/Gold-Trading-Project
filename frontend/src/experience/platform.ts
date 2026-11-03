// Show shortcuts the way this keyboard labels them.
export const IS_MAC=typeof navigator!=='undefined'&&/Mac|iPhone|iPad/i.test(navigator.platform||navigator.userAgent);
export const SHORTCUT=IS_MAC?'⌘ K':'Ctrl K';
export const MOD_KEY=IS_MAC?'⌘':'Ctrl';
