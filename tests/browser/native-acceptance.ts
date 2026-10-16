import { mkdir } from 'node:fs/promises';
import { basename, resolve } from 'node:path';

const [, , outputArgument, originArgument] = Bun.argv;
if (!outputArgument || !originArgument) throw new Error('OUTPUT_AND_ORIGIN_REQUIRED');
const origin = new URL(originArgument);
if (origin.protocol !== 'https:' || origin.hostname !== 'localhost' || origin.pathname !== '/' || origin.search || origin.hash) {
  throw new Error('OWNED_HTTPS_LOCALHOST_ORIGIN_REQUIRED');
}
const app = resolve(import.meta.dir, '../../frontend/app');
const output = resolve(outputArgument);
await mkdir(output, { recursive: true });
const result = await Bun.build({
  entrypoints: [resolve(app, 'src/index.tsx')],
  outdir: output,
  target: 'browser',
  minify: true,
  sourcemap: 'none',
  publicPath: '/',
  env: 'disable',
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
});
if (!result.success) throw new Error('PRODUCTION_WEB_BUILD_FAILED');
const entry = result.outputs.find(item => item.kind === 'entry-point' && item.path.endsWith('.js'));
if (!entry) throw new Error('PRODUCTION_WEB_ENTRY_MISSING');
const template = await Bun.file(resolve(app, 'index.html')).text();
if (!template.includes('src="./src/index.tsx"')) throw new Error('PRODUCTION_WEB_TEMPLATE_INVALID');
const config = `window.HINE_CONFIG=Object.freeze(${JSON.stringify({
  API_BASE_URL: `${origin.origin}/api/v1`, WS_URL: `wss://${origin.host}/ws/v1`, SYNC_RECONCILE_SECONDS: 10,
}).replace(/</g, '\\u003c')});\n`;
const css = result.outputs.filter(item => item.path.endsWith('.css')).map(item => `<link rel="stylesheet" href="/${basename(item.path)}">`).join('\n');
await Bun.write(resolve(output, 'index.html'), template.replace('src="./src/index.tsx"', `src="/${basename(entry.path)}"`).replace('</head>', `${css}\n</head>`));
await Bun.write(resolve(output, 'runtime-config.js'), config);
