// Shared data layer: DuckDB-Wasm over same-origin Parquet files.
// All pages import from here. Parquet files are copied to web/data/ by
// process.py (export_dashboard_data).

const DATA_BASE = './data/';

let _dbPromise = null;

async function getDb() {
  if (_dbPromise) return _dbPromise;
  _dbPromise = (async () => {
    // Official ES module build (pinned); jsDelivr's "+esm" bundle 404s on
    // older versions, so we import dist/duckdb-browser.mjs directly.
    const duckdb = await import('https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/dist/duckdb-browser.mjs');
    const bundle = await duckdb.selectBundle(duckdb.getJsDelivrBundles());
    const worker = await duckdb.createWorker(bundle.mainWorker);
    const logger = new duckdb.ConsoleLogger();
    const db = new duckdb.AsyncDuckDB(logger, worker);
    await db.instantiate(bundle.mainModule);
    return db;
  })();
  return _dbPromise;
}

// Register parquet files once; queries against table names afterwards.
// One persistent connection; views created per table on first use.
// A failed query resets the instance so one bad statement cannot poison
// later ones (WebAssembly exceptions leave the connection unusable).
const _registered = new Map();  // table -> file name
const _createdViews = new Set();
let _conn = null;

async function getConn() {
  if (_conn) return _conn;
  const db = await getDb();
  _conn = await db.connect();
  return _conn;
}

async function resetDb() {
  try { if (_conn) await _conn.close(); } catch { /* ignore */ }
  _conn = null;
  _dbPromise = null;
  _createdViews.clear();
}

async function query(sql) {
  const conn = await getConn();
  try {
    for (const [table, file] of _registered) {
      if (_createdViews.has(table)) continue;
      const url = new URL(DATA_BASE + file, document.baseURI).href;
      await conn.query(
        `CREATE VIEW ${table} AS SELECT * FROM read_parquet('${url}')`);
      _createdViews.add(table);
    }
    return await conn.query(sql);
  } catch (err) {
    await resetDb();
    throw err;
  }
}

export async function ensureTables(tables) {
  for (const t of tables) {
    if (!_registered.has(t)) {
      throw new Error(`Table ${t} not declared; add it via registerTable()`);
    }
  }
}

export function registerTable(table, file) {
  _registered.set(table, file);
}

export async function fetchJson(file, { noStore = true } = {}) {
  const url = new URL(DATA_BASE + file, window.location.href).href;
  const opts = noStore ? { cache: 'no-store' } : {};
  const resp = await fetch(url, opts);
  if (!resp.ok) throw new Error(`fetch ${file}: ${resp.status}`);
  return resp.json();
}

export async function tableToJson(sql) {
  const result = await query(sql);
  return result.toArray().map((r) => {
    const o = {};
    for (const [k, v] of Object.entries(r)) {
      // DuckDB DATE columns can arrive as Date objects or epoch-millis
      // numbers depending on the arrow shim; normalise to ISO strings so
      // Plotly renders dates, not raw ns. BigInts -> Numbers for JSON/math.
      if (v instanceof Date) {
        o[k] = v.toISOString().slice(0, 10);
      } else if (/(^|_)date($|_)/.test(k) && (typeof v === 'number' || typeof v === 'bigint')) {
        o[k] = new Date(Number(v)).toISOString().slice(0, 10);
      } else if (typeof v === 'bigint') {
        o[k] = Number(v);
      } else {
        o[k] = v;
      }
    }
    return o;
  });
}

export const GEO_COLORS = {
  US: '#2563eb',      // blue
  China: '#dc2626',   // red
  EU: '#f59e0b',      // amber
  RoW: '#6b7280',     // gray
};

export function geoTraces(rows, { dateKey = 'date', valueKey = 'value' } = {}) {
  const byGeo = {};
  for (const r of rows) {
    (byGeo[r.geography] ||= []).push(r);
  }
  return Object.entries(byGeo).map(([geo, rs]) => ({
    x: rs.map((r) => r[dateKey]),
    y: rs.map((r) => r[valueKey]),
    name: geo,
    mode: 'lines',
    line: { color: GEO_COLORS[geo] || '#999', width: 2 },
    hovertemplate: `%{x|%Y-%m-%d}<br>%{y:.3f}<extra>${geo}</extra>`,
  }));
}

const LAYOUT_BASE = {
  margin: { l: 48, r: 16, t: 12, b: 36 },
  legend: { orientation: 'h', y: 1.12 },
  paper_bgcolor: 'transparent',
  plot_bgcolor: 'transparent',
  font: { size: 12 },
};

export function drawChart(div, traces, { yTitle = '', layout = {} } = {}) {
  Plotly.newPlot(div, traces, {
    ...LAYOUT_BASE,
    yaxis: { title: { text: yTitle }, tickformat: '.2f' },
    ...layout,
  }, { responsive: true, displayModeBar: false });
}

export function initMeta() {
  fetchJson('meta.json').then((meta) => {
    const lu = document.getElementById('last-update');
    const dt2 = document.getElementById('data-through');
    if (lu) lu.textContent = meta.generated;
    if (dt2) dt2.textContent = meta.last_data_date || 'n/a';
  }).catch(() => { /* meta optional */ });
}

export function registerServiceWorker() {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('./sw.js').then((registration) => {
        registration.addEventListener('updatefound', () => {
          const newWorker = registration.installing;
          newWorker?.addEventListener('statechange', () => {
            if (newWorker.state === 'activated' && navigator.serviceWorker.controller) {
              window.location.reload();
            }
          });
        });
        setInterval(() => registration.update(), 30 * 60 * 1000);
      }).catch(() => { /* SW optional (e.g. file:// access) */ });
    });
  }
}
