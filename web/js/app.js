// Overview page: Capability + Adoption index history.
import { registerTable, tableToJson, fetchJson, geoTraces, drawChart, initMeta, registerServiceWorker } from './common.js';

registerTable('index_daily', 'index_daily.parquet');
registerTable('index_components_daily', 'index_components_daily.parquet');

const DEFAULT_DAYS = 400;

function rangeFilter(days) {
  return days ? `AND date >= CURRENT_DATE - INTERVAL '${Number(days)} days'` : '';
}

async function drawIndex(category, divId, latestDivId, asofId, days) {
  const rows = await tableToJson(`
    SELECT date, geography, "index" AS idx, coverage
    FROM index_daily
    WHERE category = '${category}' ${rangeFilter(days)}
    ORDER BY date
  `);
  if (!rows.length) {
    document.getElementById(divId).innerHTML =
      '<p class="muted">No data yet — run collect.py + process.py.</p>';
    return;
  }
  drawChart(divId, geoTraces(rows, { valueKey: 'idx' }), {
    yTitle: 'index (0-1, availability-renormalised)',
  });
  // latest values with coverage
  const latestByGeo = {};
  for (const r of rows) latestByGeo[r.geography] = r;
  const el = document.getElementById(latestDivId);
  el.innerHTML = Object.entries(latestByGeo)
    .sort((a, b) => b[1].idx - a[1].idx)
    .map(([geo, r]) => `<span class="badge geo-${geo.toLowerCase()}">${geo} ${Number(r.idx).toFixed(3)}</span>
      <small class="muted">coverage ${(Number(r.coverage) * 100).toFixed(0)}%</small>`)
    .join(' &nbsp; ');
  const asof = document.getElementById(asofId);
  if (asof) asof.textContent = `(as of ${rows[rows.length - 1].date})`;

  // freshness: max obs_date per geography, latest date
  const fresh = await tableToJson(`
    SELECT geography, MAX(obs_date) AS obs FROM index_components_daily
    WHERE category = '${category}'
    GROUP BY geography ORDER BY geography
  `);
  const hint = document.getElementById('freshness-hint');
  if (hint) {
    hint.textContent = 'latest underlying observations: '
      + fresh.map((f) => `${f.geography} ${f.obs}`).join(', ');
  }
}

async function load(days) {
  await drawIndex('capability', 'cap-chart', 'cap-latest', 'cap-asof', days);
  await drawIndex('adoption', 'ado-chart', 'ado-latest', 'ado-asof', days);
}

document.getElementById('range-select').addEventListener('change', (e) => {
  load(e.target.value || null);
});

initMeta();
registerServiceWorker();
load(DEFAULT_DAYS);
