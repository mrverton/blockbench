import './config.js';

// Custom Blockbench menu action: send the selected skin texture as a lossless PNG.
(() => {
  const PLUGIN_ID = 'telegram_png_skin_export';
  let menu = null;
  let uploadAction = null;
  let busy = false;

  function notice(message) {
    window.Blockbench?.showQuickMessage?.(message, 4500);
    console.log('[Telegram PNG]', message);
  }

  async function sendSkin() {
    if (busy) return;

    const texture = window.Texture?.selected || window.Texture?.all?.[0];
    if (!window.Project || !texture) {
      notice('Сначала открой скин или создай текстуру');
      return;
    }

    const apiBase = String(window.BLOCKBENCH_TELEGRAM_API_URL || '')
      .replace(/\/$/, '');
    if (!/^https:\/\//.test(apiBase)) {
      notice('Не настроен адрес сервера в telegram/config.js');
      return;
    }

    const initData = window.Telegram?.WebApp?.initData;
    if (!initData) {
      notice('Открой Blockbench через ссылку Telegram Mini App');
      return;
    }

    busy = true;
    try {
      // Blockbench's getDataURL() returns an image/png;base64 Data URL.
      const imageData = texture.getDataURL();
      if (!imageData.startsWith('data:image/png;base64,')) {
        throw new Error('Не удалось получить PNG-текстуру');
      }

      const response = await fetch(`${apiBase}/api/skins`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          initData,
          filename: `${texture.name || 'skin'}.png`,
          imageData
        }),
      });

      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(result.detail || `Ошибка HTTP ${response.status}`);
      }
      notice('PNG-скин отправлен в Telegram!');
    } catch (error) {
      console.error(error);
      notice(`Ошибка отправки: ${error.message}`);
    } finally {
      busy = false;
    }
  }

  function register() {
    if (!window.Blockbench?.setup_successful || !window.Plugin ||
        !window.Plugins || !window.MenuBar || !window.BarMenu ||
        !window.Action || !window.Texture) return false;
    if (window.Plugins.registered[PLUGIN_ID]) return true;

    // Plugin.register requires a previously instantiated plugin scope.
    const instance = new window.Plugin(PLUGIN_ID, { installed: true });
    window.Plugins.registered[PLUGIN_ID] = instance;
    window.Plugin.register(PLUGIN_ID, {
      title: 'Telegram PNG Skins',
      author: 'Telegram Blockbench',
      description: 'Send selected PNG skin to the bot owner.',
      version: '1.0.0',
      variant: 'web',
      onload() {
        uploadAction = new window.Action('telegram_send_png', {
          name: 'Отправить PNG-скин в Telegram',
          icon: 'cloud_upload',
          click: sendSkin,
        });
        menu = new window.BarMenu('telegram_send_menu', [uploadAction], {
          name: 'Telegram',
          icon: 'send',
        });
        window.MenuBar.addMenu(menu, 'file');
      },
      onunload() {
        menu?.delete();
        window.MenuBar.update();
        uploadAction?.delete();
        menu = uploadAction = null;
      },
    });
    return true;
  }

  let attempts = 0;
  const poll = setInterval(() => {
    if (register() || ++attempts > 300) {
      clearInterval(poll);
      if (attempts > 300) console.error('PNG plugin failed to initialize');
    }
  }, 100);
})();
