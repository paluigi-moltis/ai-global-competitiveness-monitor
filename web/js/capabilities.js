// Capabilities page: per-benchmark indicators, raw scores, contributing models.
import { registerTable, tableToJson, fetchJson, geoTraces, drawChart, initMeta, registerServiceWorker, GEO_COLORS } from './common.js';

registerTable('capability_components', 'capability_components.parquet');
registerTable('capability_detail', 'capability_detail.parquet');
registerTable('ranked_benchmarks', 'ranked_benchmarks.parquet');
registerTable('models_ref', 'models_ref.parquet');

const BENCH_NAMES = {
  'gpqa-diamond': 'GPQA Diamond',
  'math': 'MATH (Level 5)',
  'aime': 'AIME (OTIS Mock 24-25)',
  'swebench': 'SWE-bench Verified',
  'livebench': 'LiveBench',
};

let state = { bench: 'gpqa-diamond', scope: 'all', days: null };

function rangeFilter(days, col = 'date') {
  return days ? `AND ${col} >= CURRENT_DATE - INTERVAL '${Number(days)} days'` : '';
}

async function draw() {
  const { bench, scope, days } = state;

  const comps = await tableToJson(`
    SELECT date, geography, kind, value
    FROM capability_components
    WHERE component_id LIKE 'cap_${bench}_%${scope === 'open' ? '_open' : ''}'
      ${rangeFilter(days)}
    ORDER BY date
  `);

  const byKind = (k) => comps.filter((r) => r.kind === k);
  drawChart('chart-best', geoTraces(byKind('best')), { yTitle: 'percentile position' });
  drawChart('chart-topn', [
    ...geoTraces(byKind('top10')),
    ...geoTraces(byKind('top20')).map((t) => ({ ...t, line: { dash: 'dot', color: t.line.color }, name: t.name + ' (top20)' })),
  ], { yTitle: 'share of global top-N' });
  drawChart('chart-providers', [
    ...geoTraces(byKind('providers10')),
    ...geoTraces(byKind('providers20')).map((t) => ({ ...t, line: { dash: 'dot', color: t.line.color }, name: t.name + ' (top20)' })),
  ], { yTitle: 'distinct providers (count)' });

  // raw best score per date per geography (from ranked observations)
  const raw = await tableToJson(`
    SELECT date, geography, MAX(score) AS score
    FROM ranked_benchmarks
    WHERE benchmark = '${bench}' AND scope = 'all' ${rangeFilter(days)}
    GROUP BY date, geography ORDER BY date
  `);
  drawChart('chart-raw', geoTraces(raw, { valueKey: 'score' }), { yTitle: `raw score (0-1)` });

  // contributing models at the latest date within range
  const detail = await tableToJson(`
    SELECT * FROM capability_detail
    WHERE benchmark = '${bench}' AND scope = '${scope}'
    ORDER BY date
  `);
  if (detail.length) {
    const lastDate = detail[detail.length - 1].date;
    document.getElementById('detail-date').textContent = `(${lastDate})`;
    const latest = detail.filter((r) => r.date === lastDate && r.geography !== 'RoW');
    const rowsHtml = latest.map((r) => {
      const m10 = (r.models10 || []).join(', ');
      return `<tr>
        <td><span class="badge geo-${r.geography.toLowerCase()}">${r.geography}</span></td>
        <td>${r.best_model_id || '—'}</td>
        <td>${Number(r.cap_best).toFixed(2)}</td>
        <td>${Number(r.cap_top10).toFixed(2)}</td>
        <td>${r.cap_providers10}</td>
        <td>${m10 || '—'}</td>
        <td>${r.panel_size}</td>
      </tr>`;
    }).join('');
    document.getElementById('detail-table').innerHTML = `
      <table><thead><tr>
        <th>Geography</th><th>Best model</th><th>Best (pctile)</th>
        <th>Top-10 share</th><th>Providers in top-10</th>
        <th>Models in top-10</th><th>Panel size</th>
      </tr></thead><tbody>${rowsHtml}</tbody></table>`;
  }

  // component weights for this benchmark (from meta.json)
  const meta = await fetchJson('meta.json');
  const prefix = `cap_${bench}_`;
  const wrows = meta.weights.filter((w) => w.component_id.startsWith(prefix));
  document.getElementById('weights-table').innerHTML = `
    <table><thead><tr><th>Component</th><th>Weight</th><th>Notes</th></tr></thead><tbody>
    ${wrows.map((w) => `<tr><td>${w.component_id}</td><td>${w.weight}</td><td class="muted">${w.notes || ''}</td></tr>`).join('')}
    </tbody></table>`;
}

function initControls() {
  const benchSel = document.getElementById('bench-select');
  benchSel.innerHTML = Object.entries(BENCH_NAMES)
    .map(([id, name]) => `<option value="${id}">${name}</option>`).join('');
  benchSel.value = state.bench;
  benchSel.addEventListener('change', (e) => { state.bench = e.target.value; draw(); });
  document.getElementById('scope-select').addEventListener('change', (e) => { state.scope = e.target.value; draw(); });
  document.getElementById('range-select').addEventListener('change', (e) => { state.days = e.target.value || null; draw(); });
}

initControls();
initMeta();
registerServiceWorker();
draw();
