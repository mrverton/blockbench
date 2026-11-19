/**
 * Build helper for a fork of JannisX11/blockbench.
 * Runs AFTER `npm run build-web` and prepares a Vercel static output.
 * Does not modify Blockbench's source files.
 */
import { cp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { resolve, join } from 'node:path';

const root = process.cwd();
const output = resolve(root, 'public');
const required = ['index.html', 'dist', 'css', 'assets', 'lib', 'lang', 'font'];
const staticItems = [
  'index.html', 'favicon.png', 'icon.png', 'icon_full.png',
  'icon_maskable.png', 'manifest.webmanifest', 'manifest-beta.webmanifest',
  'assets', 'content', 'css', 'font', 'icons', 'keymaps',
  'lang', 'lib', 'themes', 'dist', 'telegram'
];

for (const item of required) {
  if (!existsSync(join(root, item))) {
    throw new Error(`Missing ${item}. Run this in the official Blockbench fork and build it first.`);
  }
}
await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });
for (const item of staticItems) {
  const src = join(root, item);
  if (existsSync(src)) await cp(src, join(output, item), { recursive: true });
}

const htmlPath = join(output, 'index.html');
let html = await readFile(htmlPath, 'utf8');
if (!html.includes('</head>') || !html.includes('</body>')) {
  throw new Error('Unexpected Blockbench index.html structure');
}
// SDK must be available before our UI initializes.
html = html.replace('</head>', `  <!-- Telegram Mini App SDK -->
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <script src="/telegram/telegram-init.js" defer></script>
</head>`);
html = html.replace('</body>', `  <!-- Bundled custom Blockbench plugin -->
  <script type="module" src="/telegram/export-plugin.js"></script>
</body>`);
await writeFile(htmlPath, html);
console.log(`Telegram Blockbench ready: ${output}`);
