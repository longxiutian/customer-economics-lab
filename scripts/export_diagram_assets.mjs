/** Export the native Archify SVG, not a screenshot of a replacement drawing. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
const modulePath = process.env.COHORT_PLAYWRIGHT_MODULE || path.join(root, 'tools/node_modules/playwright');
let chromium;
try {
  const pkg = require(path.join(modulePath, 'package.json'));
  if (pkg.version !== '1.62.1') throw new Error(`Expected Playwright 1.62.1, found ${pkg.version}`);
  ({chromium} = require(modulePath));
} catch (error) {
  throw new Error(`Pinned diagram renderer unavailable. Run npm ci --prefix tools, then npx --prefix tools playwright install chromium. ${error.message}`);
}
const inputs = process.argv.slice(2);
if (!inputs.length) throw new Error('Provide one or more native Archify HTML paths.');
const browser = await chromium.launch({headless: true});
if (inputs.length === 1 && inputs[0] === '--check') {
  await browser.close();
  process.stdout.write(JSON.stringify({ready: true, playwright: '1.62.1', browser: 'chromium'})+'\n');
  process.exit(0);
}
try {
  const page = await browser.newPage({viewport: {width: 2400, height: 1600}, deviceScaleFactor: 2,
    colorScheme: 'light', reducedMotion: 'reduce', locale: 'en-US', timezoneId: 'UTC'});
  for (const input of inputs) {
    const html = path.resolve(input);
    await page.goto(pathToFileURL(html).href, {waitUntil: 'load'});
    await page.evaluate(async () => {
      document.documentElement.setAttribute('data-theme', 'light');
      await document.fonts.ready;
      for (const el of document.querySelectorAll('*')) {
        el.style.animation = 'none'; el.style.transition = 'none';
      }
    });
    const asset = await page.evaluate(({reportOverview,journey,knowledge}) => {
      const source = [...document.querySelectorAll('svg')].find(el => el.hasAttribute('data-quality-profile'));
      if (!source) throw new Error('Native Archify diagram SVG is missing.');
      // The portrait edition preserves native nodes/edges, but omits the wide
      // reader swimlanes and legend. Their descriptions are in the report text.
      // Fixed, modest print typography fits the already-sized native boxes.
      if (reportOverview) {
        source.querySelectorAll('[data-node-id] text.t-primary').forEach(el=>el.style.fontSize='12px');
        source.querySelectorAll('[data-node-id] text.t-muted').forEach(el=>el.style.fontSize='9px');
      }
      if (journey || knowledge) {
        source.querySelectorAll('[data-node-id] text.t-primary').forEach(el=>el.style.fontSize=knowledge?'14px':'13px');
        source.querySelectorAll('[data-node-id] text.t-muted').forEach(el=>el.style.fontSize=knowledge?'13px':'11px');
      }
      const copy = source.cloneNode(true);
      const original = [source, ...source.querySelectorAll('*')];
      const cloned = [copy, ...copy.querySelectorAll('*')];
      const properties = ['fill','fill-opacity','stroke','stroke-width','stroke-opacity','stroke-dasharray',
        'stroke-dashoffset','stroke-linecap','stroke-linejoin','opacity','font-family','font-size','font-weight',
        'letter-spacing','text-anchor','dominant-baseline','visibility','display'];
      original.forEach((el, i) => {
        const computed = getComputedStyle(el);
        cloned[i].removeAttribute('style');
        for (const property of properties) cloned[i].style.setProperty(property, computed.getPropertyValue(property));
      });
      // Interactive legend hitboxes/badges are measured from screen coordinates
      // by the reader UI. Their subpixel bounds can vary between fresh browser
      // runs. Keep the authored legend labels, swatches, nodes and edges, but
      // omit these nonsemantic UI overlays from the frozen print asset.
      copy.querySelectorAll('script,style,animate,animateMotion,animateTransform,[data-legend-bridge-runtime]').forEach(el => el.remove());
      const vb = source.viewBox.baseVal;
      let x=vb.x,y=vb.y,width=vb.width,height=vb.height;
      if (journey) {
        // The native workflow reader reserves a broad swimlane canvas even
        // when this print layout uses only two columns. Trim that empty right
        // margin, retaining the authored stages, labels, arrows and legend.
        const boxes=[...source.querySelectorAll('[data-node-id]')].map(el=>el.getBBox());
        const right=Math.ceil(Math.max(...boxes.map(b=>b.x+b.width))+20);
        copy.querySelectorAll('[data-graph-role="structural-frame"]').forEach(el=>{
          el.setAttribute('width',String(right-10-Number(el.getAttribute('x'))));
        });
        x=10;y=32;width=right-x;
        const lastLabel=Math.max(...[...copy.querySelectorAll('text')].map(el=>Number(el.getAttribute('y')||0)));
        height=Math.ceil(lastLabel+20-y);
        copy.setAttribute('viewBox',`${x} ${y} ${width} ${height}`);
      }
      if (reportOverview) {
        for (const el of [...copy.children]) {
          if (['rect','text'].includes(el.tagName.toLowerCase()) || el.hasAttribute('data-legend')) el.remove();
        }
        const boxes=[...source.querySelectorAll('[data-node-id],path[data-edge-id]')].map(el=>el.getBBox());
        x=Math.floor(Math.min(...boxes.map(b=>b.x))-20); y=Math.floor(Math.min(...boxes.map(b=>b.y))-20);
        width=Math.ceil(Math.max(...boxes.map(b=>b.x+b.width))-x+20);
        height=Math.ceil(Math.max(...boxes.map(b=>b.y+b.height))-y+20);
        copy.setAttribute('viewBox',`${x} ${y} ${width} ${height}`);
      }
      copy.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
      copy.setAttribute('width', String(width)); copy.setAttribute('height', String(height));
      copy.style.display = 'block'; copy.style.background = '#ffffff';
      return {svg: new XMLSerializer().serializeToString(copy), width: Math.ceil(width), height: Math.ceil(height)};
    },{reportOverview:path.basename(html)==='source-systems-report.html',
       journey:['journey-save-time.html','journey-build-skill.html'].includes(path.basename(html)),
       knowledge:path.basename(html)==='knowledge-assets.html'});
    const stem = html.replace(/\.html$/i, '');
    await fs.writeFile(stem+'.svg', asset.svg+'\n', 'utf8');
    // A fresh page with the frozen SVG avoids controls, timers and responsive-fit drift.
    await page.setViewportSize({width: asset.width, height: asset.height});
    await page.setContent(`<html><body style="margin:0;background:white">${asset.svg}</body></html>`);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({path: stem+'.png', animations: 'disabled', clip:{x:0,y:0,width:asset.width,height:asset.height}});
    console.log(JSON.stringify({html:path.basename(html),svg:path.basename(stem+'.svg'),png:path.basename(stem+'.png'),width:asset.width,height:asset.height,playwright:'1.62.1'}));
  }
} finally { await browser.close(); }
