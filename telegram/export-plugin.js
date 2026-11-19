import './config.js';

/** A small built-in Blockbench plugin. Loaded only by your fork. */
(() => {
  const PLUGIN_ID = 'telegram_model_export';
  let menu = null;
  let uploadAction = null;
  let busy = false;

  function notice(message) {
    window.Blockbench?.showQuickMessage?.(message, 4000);
    console.log('[Telegram Export]', message);
  }

  async function sendModel() {
    if (busy) return;
    if (!window.Project || !window.Codecs?.project) {
      notice('Сначала создай или открой модель');
      return;
    }
    const apiBase = String(window.BLOCKBENCH_TELEGRAM_API_URL || '').replace(/\/$/, '');
    if (!/^https:\/\//.test(apiBase)) {
      notice('Укажи HTTPS API в telegram/config.js');
      return;
    }
    const initData = window.Telegram?.WebApp?.initData;
    if (!initData) {
      notice('Для загрузки открой редактор через Telegram Mini App');
      return;
    }
    busy = true;
    try {
      // The Blockbench .bbmodel codec includes geometry, UV and embedded textures.
      const model = window.Codecs.project.compile({ raw: true, bitmaps: true });
      const response = await fetch(`${apiBase}/api/models`, {
        method: 'POST',
        mode: 'cors',
        headers: {
          'Content-Type': 'application/json',
          // Useful for ngrok's free browser warning; ignored by FastAPI.
          'ngrok-skip-browser-warning': 'true',
        },
        body: JSON.stringify({
          initData,
          filename: `${String(window.Project.name || 'model').slice(0, 80)}.bbmodel`,
          model,
        }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
      notice(`Модель сохранена! ID: ${result.id}`);
    } catch (error) {
      console.error('[Telegram Export]', error);
      notice(`Ошибка отправки: ${error.message}`);
    } finally {
      busy = false;
    }
  }

  function register() {
    if (!window.Blockbench?.setup_successful || !window.Plugin ||
        !window.Plugins || !window.MenuBar || !window.BarMenu ||
        !window.Action || !window.Codecs?.project) return false;
    if (window.Plugins.registered[PLUGIN_ID]) return true;

    // Blockbench's Plugin.register expects a registered instance. Since this
    // plugin is bundled into our own web build (not sideloaded), create one.
    const instance = new window.Plugin(PLUGIN_ID, { installed: true });
    window.Plugins.registered[PLUGIN_ID] = instance;

    window.Plugin.register(PLUGIN_ID, {
      title: 'Telegram Export',
      author: 'Telegram Blockbench Kit',
      description: 'Send the current .bbmodel to your HTTPS API.',
      version: '1.0.0',
      variant: 'web',
      onload() {
        uploadAction = new window.Action('telegram_send_model', {
          name: 'Отправить модель на сервер',
          icon: 'cloud_upload',
          click: sendModel,
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

  // Blockbench's module bundle initializes asynchronously. Wait until it
  // exposes its plugin and menu globals instead of racing bundle startup.
  let attempts = 0;
  const poll = setInterval(() => {
    if (register() || ++attempts > 300) {
      clearInterval(poll);
      if (attempts > 300) console.error('Telegram plugin could not initialize');
    }
  }, 100);
})();
