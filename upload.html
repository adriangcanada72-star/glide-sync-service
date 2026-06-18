<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BCLDB Catalog Sync — The Terpene Sommelier</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Playfair+Display:wght@700&display=swap" rel="stylesheet">
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family:'DM Sans',sans-serif; background:#1a1d23; color:#e0e0e0;
    min-height:100vh; display:flex; flex-direction:column; align-items:center;
    padding:40px 20px;
  }
  .container { max-width:640px; width:100%; }
  h1 {
    font-family:'Playfair Display',serif; font-size:28px; color:#31AA64;
    margin-bottom:8px;
  }
  .subtitle { color:#888; font-size:14px; margin-bottom:32px; }
  .status-bar {
    background:#2D3139; border-radius:8px; padding:14px 18px;
    margin-bottom:24px; display:flex; align-items:center; gap:10px;
    font-size:13px;
  }
  .status-dot {
    width:10px; height:10px; border-radius:50%; flex-shrink:0;
  }
  .status-dot.green { background:#31AA64; }
  .status-dot.yellow { background:#F5A623; }
  .status-dot.red { background:#E74C3C; }

  .upload-zone {
    border:2px dashed #444; border-radius:12px; padding:48px 24px;
    text-align:center; cursor:pointer; transition:all .2s;
    margin-bottom:24px;
  }
  .upload-zone:hover, .upload-zone.dragover {
    border-color:#31AA64; background:rgba(49,170,100,.05);
  }
  .upload-zone.has-file { border-color:#31AA64; border-style:solid; }
  .upload-icon { font-size:48px; margin-bottom:12px; }
  .upload-label { font-size:16px; font-weight:500; margin-bottom:6px; }
  .upload-hint { font-size:12px; color:#666; }
  .file-name { color:#31AA64; font-weight:700; font-size:16px; margin-top:8px; }
  input[type="file"] { display:none; }

  .actions { display:flex; gap:12px; margin-bottom:24px; }
  .btn {
    flex:1; padding:14px; border:none; border-radius:8px; font-size:15px;
    font-weight:700; cursor:pointer; font-family:'DM Sans',sans-serif;
    transition:all .2s;
  }
  .btn:disabled { opacity:.4; cursor:not-allowed; }
  .btn-preview { background:#2D3139; color:#e0e0e0; border:1px solid #444; }
  .btn-preview:hover:not(:disabled) { background:#363b44; }
  .btn-live { background:#31AA64; color:#fff; }
  .btn-live:hover:not(:disabled) { background:#28954f; }

  .results { display:none; }
  .results.visible { display:block; }
  .result-card {
    background:#2D3139; border-radius:8px; padding:18px;
    margin-bottom:12px;
  }
  .result-header {
    font-weight:700; font-size:15px; margin-bottom:12px;
    display:flex; align-items:center; gap:8px;
  }
  .stat-row {
    display:flex; justify-content:space-between; padding:6px 0;
    border-bottom:1px solid #3a3f48; font-size:14px;
  }
  .stat-row:last-child { border-bottom:none; }
  .stat-value { font-weight:700; }
  .stat-value.add { color:#31AA64; }
  .stat-value.update { color:#F5A623; }
  .stat-value.delete { color:#E74C3C; }
  .stat-value.unchanged { color:#888; }

  .detail-section { margin-top:12px; }
  .detail-section h3 {
    font-size:13px; color:#888; text-transform:uppercase;
    letter-spacing:.05em; margin-bottom:8px;
  }
  .detail-item {
    font-size:13px; padding:4px 0; color:#ccc;
  }
  .detail-item .sku { color:#888; margin-right:8px; }
  .change-detail {
    font-size:11px; color:#888; padding-left:16px;
  }

  .spinner {
    display:inline-block; width:18px; height:18px;
    border:2px solid #444; border-top-color:#31AA64;
    border-radius:50%; animation:spin .6s linear infinite;
  }
  @keyframes spin { to { transform:rotate(360deg); } }

  .progress { display:none; text-align:center; padding:24px; }
  .progress.visible { display:block; }
  .progress-text { margin-top:12px; font-size:14px; color:#888; }
</style>
</head>
<body>

<div class="container">
  <h1>🌿 BCLDB Catalog Sync</h1>
  <p class="subtitle">The Terpene Sommelier — Product Catalog Update Tool</p>

  <div class="status-bar">
    {% if api_configured %}
    <div class="status-dot green"></div>
    <span>Glide API connected — live sync available</span>
    {% else %}
    <div class="status-dot yellow"></div>
    <span>Preview mode — Glide API not configured (set environment variables to enable live sync)</span>
    {% endif %}
  </div>

  <div class="upload-zone" id="dropZone" onclick="document.getElementById('fileInput').click()">
    <div class="upload-icon">📄</div>
    <div class="upload-label">Drop BCLDB CSV extract here</div>
    <div class="upload-hint">or click to browse</div>
    <div class="file-name" id="fileName"></div>
  </div>
  <input type="file" id="fileInput" accept=".csv">

  <div class="actions">
    <button class="btn btn-preview" id="btnPreview" disabled onclick="runSync('preview')">
      Preview Changes
    </button>
    <button class="btn btn-live" id="btnLive" disabled onclick="runSync('live')">
      {% if api_configured %}Sync to Glide{% else %}API Not Configured{% endif %}
    </button>
  </div>

  <div class="progress" id="progress">
    <div class="spinner"></div>
    <div class="progress-text" id="progressText">Analyzing catalog...</div>
  </div>

  <div class="results" id="results"></div>
</div>

<script>
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const btnPreview = document.getElementById('btnPreview');
const btnLive = document.getElementById('btnLive');
let selectedFile = null;

// Drag and drop
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  if (e.dataTransfer.files[0]) selectFile(e.dataTransfer.files[0]);
});

fileInput.addEventListener('change', e => { if (e.target.files[0]) selectFile(e.target.files[0]); });

function selectFile(file) {
  if (!file.name.endsWith('.csv')) { alert('Please select a CSV file'); return; }
  selectedFile = file;
  document.getElementById('fileName').textContent = file.name;
  dropZone.classList.add('has-file');
  btnPreview.disabled = false;
  btnLive.disabled = !{{ 'true' if api_configured else 'false' }};
}

async function runSync(mode) {
  if (!selectedFile) return;

  const progress = document.getElementById('progress');
  const results = document.getElementById('results');
  const progressText = document.getElementById('progressText');

  progress.classList.add('visible');
  results.classList.remove('visible');
  btnPreview.disabled = true;
  btnLive.disabled = true;

  progressText.textContent = mode === 'live'
    ? 'Syncing to Glide... this may take a minute'
    : 'Analyzing catalog changes...';

  const formData = new FormData();
  formData.append('file', selectedFile);
  formData.append('mode', mode);

  try {
    const response = await fetch('/sync?mode=' + mode, {
      method: 'POST',
      body: formData,
    });
    const data = await response.json();
    showResults(data);
  } catch (err) {
    results.innerHTML = `<div class="result-card"><div class="result-header">❌ Error</div>${err.message}</div>`;
    results.classList.add('visible');
  }

  progress.classList.remove('visible');
  btnPreview.disabled = false;
  btnLive.disabled = !{{ 'true' if api_configured else 'false' }};
}

function showResults(data) {
  const s = data.summary;
  const results = document.getElementById('results');

  let statusIcon = data.status === 'completed' ? '✅' : data.status === 'error' ? '❌' : '📋';
  let statusText = data.status === 'completed' ? 'Sync Complete' :
                    data.status === 'no_changes' ? 'No Changes' :
                    data.status === 'error' ? 'Error' : 'Preview Report';

  let html = `
    <div class="result-card">
      <div class="result-header">${statusIcon} ${statusText}</div>
      <div class="stat-row"><span>Products in new extract</span><span class="stat-value">${s.new_total}</span></div>
      <div class="stat-row"><span>Products in current catalog</span><span class="stat-value">${s.current_total || 'N/A (API not connected)'}</span></div>
      <div class="stat-row"><span>Unchanged</span><span class="stat-value unchanged">${s.unchanged}</span></div>
      <div class="stat-row"><span>New products to add</span><span class="stat-value add">+${s.add}</span></div>
      <div class="stat-row"><span>Products to update</span><span class="stat-value update">${s.update}</span></div>
      <div class="stat-row"><span>Products to remove</span><span class="stat-value delete">-${s.delete}</span></div>
    </div>`;

  if (data.details) {
    const d = data.details;

    if (d.new_products && d.new_products.length > 0) {
      html += `<div class="result-card"><div class="detail-section"><h3>➕ New Products</h3>`;
      d.new_products.forEach(p => {
        html += `<div class="detail-item"><span class="sku">${p.sku}</span>${p.name}</div>`;
      });
      if (s.add > 50) html += `<div class="detail-item" style="color:#666">... and ${s.add - 50} more</div>`;
      html += `</div></div>`;
    }

    if (d.updated_products && d.updated_products.length > 0) {
      html += `<div class="result-card"><div class="detail-section"><h3>✏️ Updated Products</h3>`;
      d.updated_products.forEach(p => {
        html += `<div class="detail-item"><span class="sku">${p.sku}</span>${p.name}</div>`;
        Object.entries(p.changes).forEach(([col, vals]) => {
          html += `<div class="change-detail">${col}: ${(vals.old||'(empty)').substring(0,30)} → ${(vals.new||'(empty)').substring(0,30)}</div>`;
        });
      });
      if (s.update > 50) html += `<div class="detail-item" style="color:#666">... and ${s.update - 50} more</div>`;
      html += `</div></div>`;
    }

    if (d.deleted_products && d.deleted_products.length > 0) {
      html += `<div class="result-card"><div class="detail-section"><h3>🗑️ Removed Products</h3>`;
      d.deleted_products.forEach(p => {
        html += `<div class="detail-item"><span class="sku">${p.sku}</span>${p.name}</div>`;
      });
      if (s.delete > 50) html += `<div class="detail-item" style="color:#666">... and ${s.delete - 50} more</div>`;
      html += `</div></div>`;
    }
  }

  if (data.execution) {
    html += `<div class="result-card">
      <div class="result-header">API Execution</div>
      <div class="stat-row"><span>Successful</span><span class="stat-value add">${data.execution.success}</span></div>
      <div class="stat-row"><span>Failed</span><span class="stat-value delete">${data.execution.failed}</span></div>
    </div>`;
  }

  if (data.error) {
    html += `<div class="result-card"><div class="result-header">⚠️ Note</div><p style="font-size:13px;color:#888">${data.error}</p></div>`;
  }

  results.innerHTML = html;
  results.classList.add('visible');
}
</script>
</body>
</html>
