/** Telegram host integration; safe to open in a normal browser too. */
(() => {
  const tg = window.Telegram?.WebApp;
  if (!tg) return;
  tg.ready();
  tg.expand();
  tg.disableVerticalSwipes?.();
  tg.enableClosingConfirmation?.();
})();
