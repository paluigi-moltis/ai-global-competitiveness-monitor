// Adoption page: platform share charts + top contributing models.
import { registerTable, tableToJson, fetchJson, geoTraces, drawChart, initMeta, registerServiceWorker } from './common.js';

registerTable('adoption_components', 'adoption_components.parquet');
registerTable('ranked_benchmarks', 'ranked_benchmarks.parquet');
registerTable('models_ref', 'models_ref.parquet');

let days = 90;

function rangeFilter(col = 'date') {
  return days ? `AND ${col} >= CURRENT_DATE - INTERVAL '${Number(days)} days'` : '';
}

async function componentChart(componentId, divId) {
  const rows = await tableToJson(`
    SELECT date, geography, value FROM adoption_components
    WHERE component_id = '${componentId}' ${rangeFilter()}
    ORDER BY date
  `);
  if (!rows.length) {
    document.getElementById(divId).innerHTML =
      '<p class="muted">No data collected yet for this indicator.</p>';
    return;
  }
  const traces = geoTraces(rows);
  // few date points (e.g. download snapshots) render as epoch numbers on a
  // linear axis unless Plotly is told the axis is a date axis
  const layout = { xaxis: { type: 'date' } };
  drawChart(divId, traces, { yTitle: 'share (0-1)', layout });
}

async function topContributors(divId, subtitle, sql) {
  const rows = await tableToJson(sql);
  if (!rows.length) {
    document.getElementById(divId).innerHTML = '';
    return;
  }
  const byGeo = {};
  for (const r of rows) (byGeo[r.geography] ||= []).push(r);
  document.getElementById(divId).innerHTML = `
    <h6>${subtitle}</h6>
    ${Object.entries(byGeo).map(([geo, rs]) => `
      <p><span class="badge geo-${geo.toLowerCase()}">${geo}</span>
      ${rs.slice(0, 6).map((r) => `${r.model_name || r.model_id} (${(Number(r.share) * 100).toFixed(1)}%)`).join(' · ')}</p>
    `).join('')}`;
}

async function load() {
  await componentChart('vercel_gateway_tokens_share', 'chart-vg-tokens');
  await componentChart('vercel_gateway_spend_share', 'chart-vg-spend');
  await componentChart('hf_downloads_share', 'chart-hf');
  await componentChart('or_tokens_share', 'chart-openrouter');

  // top models: Vercel gateway token shares (latest day)
  const vgDay = await tableToJson(`
    SELECT MAX(date) AS d FROM ranked_benchmarks WHERE benchmark = '__none__'`); // placeholder no-op
  const vg = await tableToJson(`
    WITH latest AS (SELECT MAX(date) AS d FROM ranked_benchmarks)
    SELECT m.geography, r.model_id, r.score AS share
    FROM ranked_benchmarks r JOIN models_ref m USING (model_id)
    WHERE r.benchmark = 'livebench' AND r.scope = 'all'
      AND r.date = (SELECT MAX(date) FROM ranked_benchmarks WHERE benchmark = 'livebench')
    ORDER BY r.score DESC LIMIT 12
  `).catch(() => []);
  // The gateway top-model table needs per-model share data; approximate with
  // the latest gateway share rows joined via models_ref if usage_shares were
  // exported. For now show HF downloads leaders instead (always available).
  const hf = await tableToJson(`
    WITH latest AS (
      SELECT MAX(date) AS d FROM ranked_benchmarks WHERE benchmark = 'livebench'
    )
    SELECT m.geography, m.model_name, m.weights_status,
           r.score AS share, r.rank
    FROM ranked_benchmarks r JOIN models_ref m USING (model_id)
    WHERE r.benchmark = 'livebench' AND r.scope = 'all' AND r.rank <= 10
      AND r.date = (SELECT d FROM latest)
    ORDER BY r.rank
  `).catch(() => []);

  if (hf.length) {
    document.getElementById('contrib-date').textContent =
      `(latest ranked benchmark date: ${hf[0] ? '' : ''}global top-10)`;
    const byGeo = {};
    for (const r of hf) (byGeo[r.geography] ||= []).push(r);
    document.getElementById('contrib-vg').innerHTML = `
      <h6>Global top-10 (latest LiveBench release)</h6>
      ${Object.entries(byGeo).map(([geo, rs]) => `
        <p><span class="badge geo-${geo.toLowerCase()}">${geo}</span>
        ${rs.map((r) => `${r.model_name}${r.weights_status === 'open' ? ' 🔓' : ''}`).join(' · ')}</p>
      `).join('')}`;
  }
  document.getElementById('contrib-hf').innerHTML =
    '<h6>Platform leaders (Hugging Face)</h6><p class="muted">See chart — shares are computed within each platform.</p>';

  // weights table for adoption components
  const meta = await fetchJson('meta.json');
  const wrows = meta.weights.filter((w) => !w.component_id.startsWith('cap_'));
  document.getElementById('weights-table').innerHTML = `
    <table><thead><tr><th>Component</th><th>Weight</th><th>Notes</th></tr></thead><tbody>
    ${wrows.map((w) => `<tr><td>${w.component_id}</td><td>${w.weight}</td><td class="muted">${w.notes || ''}</td></tr>`).join('')}
    </tbody></table>`;
}

document.getElementById('range-select').addEventListener('change', (e) => {
  days = e.target.value ? Number(e.target.value) : null;
  load();
});

initMeta();
registerServiceWorker();
load();
