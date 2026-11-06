'use strict';

// Runs synchronously in the page. Do not introduce an await between finding the
// current menu item and activating it: WhatsApp replaces transient menu nodes.
// HTMLElement.click avoids Playwright's scroll/actionability round trips.
function dispatchVoiceClick({ groupId, token, openMenu = false }) {
  const prior = window.__botskyVoiceDispatch;
  if (prior?.token === token) return { state: 'dispatched' };
  if (window.__botskyAudio?.token !== token) return { state: 'owner_changed' };
  const chat = window.WPP?.chat.getActiveChat();
  if ((chat?.id?._serialized || chat?.id?.toString()) !== groupId) return { state: 'group_changed' };
  const collection = window.require('WAWebCallCollection');
  const call = collection.activeCall || collection.lastActiveCall;
  if (call && ![0, 'ENDED', 'FAILED', 'REJECTED', 'NOT_ANSWERED'].includes(call.getState?.())) return { state: 'call_busy' };
  const available = button => {
    const box = button.getBoundingClientRect();
    const style = getComputedStyle(button);
    return button.isConnected && !button.disabled && button.getAttribute('aria-disabled') !== 'true' &&
      style.visibility === 'visible' && style.display !== 'none' && style.pointerEvents !== 'none' &&
      box.width > 0 && box.height > 0 && box.top >= 0 && box.left >= 0 && box.bottom <= innerHeight && box.right <= innerWidth &&
      button.contains(document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2));
  };
  const items = Array.from(document.querySelectorAll('button[role="menuitem"][aria-label="Llamada"]'));
  const buttons = items.filter(available);
  if (buttons.length !== 1) {
    // Opening a menu cannot place the voice call. Keep this atomic too: the
    // header's Playwright click can time out after the menu already opened.
    if (openMenu && !items.some(item => item.getBoundingClientRect().width > 0)) {
      const headers = Array.from(document.querySelectorAll('#main header button[aria-label="Videollamada en grupo"]')).filter(available);
      if (headers.length === 1) { headers[0].click(); return { state: 'menu_opened' }; }
    }
    return { state: 'menu_unavailable' };
  }
  // Reserve before invoking the handler, including when it throws or the reply
  // to evaluate gets lost. Never activate this attempt a second time.
  window.__botskyVoiceDispatch = { token };
  buttons[0].click();
  return { state: 'dispatched' };
}

module.exports = { dispatchVoiceClick };
