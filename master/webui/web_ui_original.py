"""웹 UI HTML 상수. http_server.py에서 import하여 사용."""

WEB_UI_HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentWatch Context Server</title>
<style>
  :root { --bg: #0d1117; --surface: #161b22; --border: #30363d; --text: #e6edf3; --dim: #8b949e; --accent: #58a6ff; --green: #3fb950; --orange: #d29922; --red: #f85149; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; }
  .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
  h1 { font-size: 1.5rem; margin-bottom: 8px; }
  h1 span { color: var(--accent); }
  .subtitle { color: var(--dim); margin-bottom: 24px; font-size: 0.9rem; }

  /* 상태 카드 */
  .status-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 24px; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
  .card .label { color: var(--dim); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }
  .card .value { font-size: 1.5rem; font-weight: 600; margin-top: 4px; }
  .card .value.ok { color: var(--green); }
  .card .value.warn { color: var(--orange); }

  /* 검색 */
  .search-box { display: flex; gap: 8px; margin-bottom: 16px; }
  .search-box input { flex: 1; background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 10px 14px; color: var(--text); font-size: 0.95rem; outline: none; }
  .search-box input:focus { border-color: var(--accent); }
  .search-box button { background: var(--accent); color: #fff; border: none; border-radius: 6px; padding: 10px 20px; cursor: pointer; font-weight: 600; font-size: 0.95rem; white-space: nowrap; }
  .search-box button:hover { opacity: 0.9; }
  .search-opts { display: flex; gap: 16px; margin-bottom: 20px; align-items: center; flex-wrap: wrap; }
  .search-opts label { color: var(--dim); font-size: 0.85rem; }
  .search-opts input, .search-opts select { background: var(--surface); border: 1px solid var(--border); border-radius: 4px; padding: 4px 8px; color: var(--text); font-size: 0.85rem; }

  /* 탭 */
  .tabs { display: flex; gap: 0; margin-bottom: 20px; border-bottom: 1px solid var(--border); }
  .tab { padding: 8px 20px; cursor: pointer; color: var(--dim); border-bottom: 2px solid transparent; font-size: 0.9rem; }
  .tab:hover { color: var(--text); }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); }
  .tab-content { display: none; }
  .tab-content.active { display: block; }

  /* 결과 */
  .result { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 12px; }
  .result-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
  .result-file { color: var(--accent); font-weight: 600; font-size: 0.95rem; }
  .result-score { color: var(--dim); font-size: 0.8rem; }
  .result-category { color: var(--orange); font-size: 0.8rem; margin-bottom: 6px; }
  .result-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
  .tag { background: #1f6feb22; color: var(--accent); border: 1px solid #1f6feb44; border-radius: 12px; padding: 2px 10px; font-size: 0.75rem; cursor: pointer; }
  .tag:hover { background: #1f6feb44; }
  .result-body { color: var(--dim); font-size: 0.85rem; white-space: pre-wrap; max-height: 200px; overflow-y: auto; }

  /* 문서 목록 */
  .doc-list { display: grid; gap: 8px; }
  .doc-item { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; cursor: pointer; }
  .doc-item:hover { border-color: var(--accent); }
  .doc-name { color: var(--accent); font-size: 0.9rem; }
  .doc-tags { display: flex; gap: 4px; flex-wrap: wrap; }

  /* 태그 클라우드 */
  .tag-cloud { display: flex; flex-wrap: wrap; gap: 8px; }
  .tag-cloud .tag { font-size: 0.85rem; padding: 4px 12px; }
  .tag-count { color: var(--dim); font-size: 0.75rem; margin-left: 4px; }

  .empty { color: var(--dim); text-align: center; padding: 40px; }
  .loading { color: var(--dim); text-align: center; padding: 20px; }

  /* 도메인 탭 */
  .domain-controls { display: flex; gap: 8px; margin-bottom: 16px; align-items: center; }
  .domain-controls select { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 8px 12px; color: var(--text); font-size: 0.9rem; }
  .domain-item { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 8px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; }
  .domain-item:hover { border-color: var(--accent); }
  .domain-item .domain-info { flex: 1; }
  .domain-item .domain-title { color: var(--accent); font-weight: 600; font-size: 1rem; }
  .domain-item .domain-summary { color: var(--dim); font-size: 0.85rem; margin-top: 4px; }
  .domain-item .domain-meta { display: flex; gap: 8px; align-items: center; font-size: 0.8rem; }
  .status-badge { padding: 2px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }
  .status-badge.draft { background: #d2992222; color: var(--orange); border: 1px solid #d2992244; }
  .status-badge.active { background: #3fb95022; color: var(--green); border: 1px solid #3fb95044; }

  /* 도메인 상세 */
  .domain-detail-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
  .domain-detail-header h2 { flex: 1; font-size: 1.2rem; }
  .back-btn { background: var(--surface); border: 1px solid var(--border); color: var(--text); border-radius: 6px; padding: 6px 12px; cursor: pointer; font-size: 0.85rem; }
  .back-btn:hover { border-color: var(--accent); }
  .domain-layout { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; height: calc(100vh - 280px); }
  .domain-doc-panel { overflow-y: auto; padding-right: 8px; }
  .domain-doc-panel h3 { color: var(--dim); font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; margin: 16px 0 8px; }
  .domain-doc-panel h3:first-child { margin-top: 0; }
  .domain-content { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; white-space: pre-wrap; font-size: 0.85rem; max-height: 40vh; overflow-y: auto; }
  .domain-sources { display: grid; gap: 8px; }
  .source-item { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 12px; }
  .source-item .source-name { color: var(--accent); font-size: 0.85rem; font-weight: 600; margin-bottom: 4px; }
  .source-item .source-preview { color: var(--dim); font-size: 0.8rem; white-space: pre-wrap; max-height: 150px; overflow-y: auto; }

  /* 채팅 */
  .domain-chat-panel { display: flex; flex-direction: column; }
  .domain-chat-panel h3 { color: var(--dim); font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; }
  .chat-messages { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; padding: 8px; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 8px; min-height: 200px; }
  .chat-msg { padding: 10px 14px; border-radius: 8px; font-size: 0.85rem; white-space: pre-wrap; max-width: 90%; word-break: break-word; }
  .chat-msg.user { background: #1f6feb33; align-self: flex-end; color: var(--text); }
  .chat-msg.assistant { background: var(--bg); align-self: flex-start; color: var(--text); border: 1px solid var(--border); }
  .chat-input-area { margin-top: auto; }
  .chat-input-area textarea { width: 100%; background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 10px; color: var(--text); font-size: 0.9rem; resize: vertical; outline: none; font-family: inherit; }
  .chat-input-area textarea:focus { border-color: var(--accent); }
  .chat-buttons { display: flex; gap: 8px; margin-top: 8px; }
  .chat-buttons button { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.85rem; }
  #chatSendBtn { background: var(--accent); color: #fff; flex: 1; }
  #chatSendBtn:hover { opacity: 0.9; }
  #chatSendBtn:disabled, #createDomainBtn:disabled, #rebuildBtn:disabled { opacity: 0.5; cursor: not-allowed; }
  .activate-btn { background: var(--green); color: #fff; }
  .activate-btn:hover { opacity: 0.9; }
  .apply-btn { background: var(--orange); color: #fff; }
  .apply-btn:hover { opacity: 0.9; }
  .clear-btn { background: var(--surface); color: var(--dim); border: 1px solid var(--border) !important; }
  .delete-btn { background: #a1260d; color: #fff; border: none; border-radius: 6px; padding: 6px 12px; cursor: pointer; font-size: 0.85rem; }
  .delete-btn:hover { opacity: 0.9; }
</style>
</head>
<body>
<div class="container">
  <h1 style="display:flex;align-items:center;gap:16px;">
    <span style="flex:1;"><span class="brand-name">AgentWatch</span> Context Server</span>
    <a href="/ontology" style="font-size:0.7em;font-weight:500;color:#4ec9b0;background:#252526;border:1px solid #4ec9b0;border-radius:6px;padding:6px 14px;text-decoration:none;">Ontology Viewer →</a>
  </h1>
  <p class="subtitle" id="projectRoot">Loading...</p>

  <div class="status-row" id="statusCards">
    <div class="card"><div class="label">Status</div><div class="value" id="sStatus">-</div></div>
    <div class="card"><div class="label">Documents</div><div class="value" id="sDocs">-</div></div>
    <div class="card"><div class="label">Tags</div><div class="value" id="sTags">-</div></div>
    <div class="card"><div class="label">Updating</div><div class="value" id="sUpdating">-</div></div>
    <div class="card" style="display:flex;align-items:center;justify-content:center;">
      <button id="rebuildBtn" onclick="rebuildIndex()" style="background:var(--orange);color:#fff;border:none;border-radius:6px;padding:10px 20px;cursor:pointer;font-weight:600;font-size:0.85rem;">Rebuild Index</button>
    </div>
  </div>

  <div class="tabs">
    <div class="tab active" data-tab="search">Search</div>
    <div class="tab" data-tab="docs">Documents</div>
    <div class="tab" data-tab="tags">Tags</div>
    <div class="tab" data-tab="domains">Domains</div>
  </div>

  <!-- Search Tab -->
  <div class="tab-content active" id="tab-search">
    <div class="search-box">
      <input type="text" id="searchQuery" placeholder="Search query..." />
      <button onclick="doSearch()">Search</button>
    </div>
    <div class="search-opts">
      <label>Results: <input type="number" id="searchN" value="5" min="1" max="50" style="width:60px"></label>
      <label>Category: <input type="text" id="searchCat" placeholder="filter..." style="width:120px"></label>
      <label>Tags: <input type="text" id="searchTags" placeholder="comma separated" style="width:160px"></label>
    </div>
    <div id="searchResults"><div class="empty">Enter a query to search the context database.</div></div>
  </div>

  <!-- Documents Tab -->
  <div class="tab-content" id="tab-docs">
    <div class="search-box">
      <input type="text" id="docFilter" placeholder="Filter documents..." oninput="filterDocs()" />
    </div>
    <div id="docList"><div class="loading">Loading documents...</div></div>
  </div>

  <!-- Tags Tab -->
  <div class="tab-content" id="tab-tags">
    <div id="tagCloud"><div class="loading">Loading tags...</div></div>
  </div>

  <!-- Domains Tab -->
  <div class="tab-content" id="tab-domains">
    <div id="domainListView">
      <div class="domain-controls">
        <select id="domainFilter">
          <option value="all">All</option>
          <option value="draft">Draft</option>
          <option value="active">Active</option>
        </select>
        <span id="domainCounts" style="color:var(--dim);font-size:0.85rem;"></span>
        <button onclick="toggleNewDomain()" style="margin-left:auto;background:var(--accent);color:#fff;border:none;border-radius:6px;padding:8px 16px;cursor:pointer;font-weight:600;font-size:0.85rem;">+ New Domain</button>
      </div>
      <div id="newDomainForm" style="display:none;margin-bottom:16px;">
        <div class="result" style="border-color:var(--accent);">
          <div style="margin-bottom:8px;color:var(--dim);font-size:0.85rem;">Describe what you want to document — a pattern, a recipe, a system overview, etc.</div>
          <div class="search-box" style="margin-bottom:0;">
            <input type="text" id="newDomainTopic" placeholder="e.g. 미션 태스크를 추가하는 방법을 정리해줘" />
            <button onclick="createDomain()" id="createDomainBtn">Create</button>
          </div>
        </div>
      </div>
      <div id="domainList"><div class="loading">Loading domains...</div></div>
    </div>

    <div id="domainDetail" style="display:none;">
      <div class="domain-detail-header">
        <button class="back-btn" onclick="closeDomainDetail()">&larr; Back</button>
        <h2 id="domainDetailName"></h2>
        <span id="domainDetailStatus" class="status-badge"></span>
        <button class="delete-btn" onclick="deleteDomain()" title="모든 표면(MD·패키지·DB·인덱스)에서 완전 제거" style="margin-left:auto;">Delete</button>
      </div>
      <div class="domain-layout">
        <div class="domain-doc-panel">
          <h3>Domain Document</h3>
          <div id="domainContent" class="domain-content"></div>
          <h3>Source Documents</h3>
          <div id="domainSources" class="domain-sources"></div>
        </div>
        <div class="domain-chat-panel">
          <h3>Chat with LLM</h3>
          <div id="chatMessages" class="chat-messages"></div>
          <div class="chat-input-area">
            <textarea id="chatInput" placeholder="Ask about patterns, recipes, pitfalls..." rows="3"></textarea>
            <div class="chat-buttons">
              <button id="chatSendBtn" onclick="sendChat()">Send</button>
              <button class="apply-btn" onclick="applyToDocument()" title="Apply last LLM response to document">Apply</button>
              <button class="activate-btn" id="activateBtn" onclick="activateDomain()" style="display:none;">Activate</button>
              <button class="clear-btn" onclick="clearChat()" title="Clear chat history">Clear</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<script>
const API = '';

// ── Tabs ──
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
    if (tab.dataset.tab === 'domains') loadDomains();
  });
});

// ── Status ──
async function loadStatus() {
  try {
    const [health, status, tags] = await Promise.all([
      fetch(API + '/api/v1/health').then(r => r.json()),
      fetch(API + '/api/v1/index/status').then(r => r.json()),
      fetch(API + '/api/v1/tags').then(r => r.json()),
    ]);
    document.getElementById('projectRoot').textContent = health.project_root || '';
    document.getElementById('sStatus').textContent = health.status || 'unknown';
    document.getElementById('sStatus').className = 'value' + (health.status === 'ok' ? ' ok' : ' warn');
    document.getElementById('sDocs').textContent = status.indexed_documents || 0;
    document.getElementById('sTags').textContent = tags.total_tags || 0;
    document.getElementById('sUpdating').textContent = health.updating ? 'Yes' : 'No';
    document.getElementById('sUpdating').className = 'value' + (health.updating ? ' warn' : ' ok');

    // tags cloud
    renderTagCloud(tags.tags || {});
  } catch(e) {
    document.getElementById('sStatus').textContent = 'Error';
    document.getElementById('sStatus').className = 'value warn';
  }
}

// ── Rebuild ──
async function rebuildIndex() {
  if (!confirm('Rebuild vector index? This may take a while.')) return;
  const btn = document.getElementById('rebuildBtn');
  btn.disabled = true; btn.textContent = 'Rebuilding...';
  try {
    const resp = await fetch(API + '/api/v1/index/rebuild', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}' });
    const data = await resp.json();
    if (data.error) { alert('Error: ' + data.error); }
    else { alert('Rebuild complete: ' + (data.indexed_files || 0) + ' documents indexed.'); loadStatus(); }
  } catch(e) { alert('Rebuild failed: ' + e.message); }
  finally { btn.disabled = false; btn.textContent = 'Rebuild Index'; }
}

// ── Search ──
document.getElementById('searchQuery').addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });

async function doSearch() {
  const query = document.getElementById('searchQuery').value.trim();
  if (!query) return;
  const n = parseInt(document.getElementById('searchN').value) || 10;
  const cat = document.getElementById('searchCat').value.trim();
  const tagsRaw = document.getElementById('searchTags').value.trim();
  const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : null;

  document.getElementById('searchResults').innerHTML = '<div class="loading">Searching...</div>';

  try {
    const body = { query, n_results: n };
    if (cat) body.category_filter = cat;
    if (tags) body.tags = tags;

    const resp = await fetch(API + '/api/v1/search/combined', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
    });
    const data = await resp.json();
    renderResults(data);
  } catch(e) {
    document.getElementById('searchResults').innerHTML = '<div class="empty">Search failed: ' + e.message + '</div>';
  }
}

function renderResults(data) {
  const el = document.getElementById('searchResults');
  const results = data.results || [];
  if (!results.length) { el.innerHTML = '<div class="empty">No results found.</div>'; return; }

  el.innerHTML = results.map((r, i) => {
    const tags = (r.tags || []).map(t => '<span class="tag" onclick="searchByTag(\'' + t + '\')">' + t + '</span>').join('');
    const score = r.similarity != null && r.similarity > 0 ? (r.similarity * 100).toFixed(1) + '%' : (r.source || '');
    const preview = (r.content_preview || r.body || '').substring(0, 400);
    // 의존 그래프 정보
    const inclBy = (r.included_by || []);
    const depHtml = inclBy.length ? '<div style="color:var(--orange);font-size:0.8rem;margin-top:6px;">\u25B6 referenced by: ' + inclBy.map(f => '<span style="color:var(--dim)">' + escHtml(f) + '</span>').join(', ') + '</div>' : '';
    // co-commit 정보
    const coCh = (r.co_changed || []);
    const coHtml = coCh.length ? '<div style="color:var(--green);font-size:0.8rem;margin-top:4px;">\u25B6 co-changed: ' + coCh.map(e => '<span style="color:var(--dim)">' + escHtml(e.file) + ' (' + e.count + ')</span>').join(', ') + '</div>' : '';
    return '<div class="result">' +
      '<div class="result-header"><span class="result-file">' + (r.file || r.id || '?') + '</span><span class="result-score">' + score + '</span></div>' +
      (r.category ? '<div class="result-category">' + r.category + '</div>' : '') +
      (tags ? '<div class="result-tags">' + tags + '</div>' : '') +
      '<div class="result-body">' + escHtml(preview) + '</div>' +
      depHtml + coHtml +
    '</div>';
  }).join('');
}

function searchByTag(tag) {
  document.getElementById('searchTags').value = tag;
  const q = document.getElementById('searchQuery').value.trim();
  if (!q) document.getElementById('searchQuery').value = tag;
  doSearch();
}

// ── Documents ──
let allDocs = [];

async function loadDocs() {
  try {
    const tags = await fetch(API + '/api/v1/tags').then(r => r.json());
    const status = await fetch(API + '/api/v1/index/status').then(r => r.json());

    const resp = await fetch(API + '/api/v1/search/vector', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ query: ' ', n_results: status.indexed_documents || 100 }),
    });
    const data = await resp.json();
    allDocs = (data.results || []).map(r => ({
      file: r.file || r.id || '?',
      tags: r.tags || [],
      category: r.category || '',
      preview: (r.content_preview || r.body || '').substring(0, 200),
    }));
    allDocs.sort((a, b) => a.file.localeCompare(b.file));
    renderDocs(allDocs);
  } catch(e) {
    document.getElementById('docList').innerHTML = '<div class="empty">Failed to load documents.</div>';
  }
}

function renderDocs(docs) {
  const el = document.getElementById('docList');
  if (!docs.length) { el.innerHTML = '<div class="empty">No documents found.</div>'; return; }
  el.innerHTML = docs.map(d => {
    const tags = d.tags.slice(0, 5).map(t => '<span class="tag" onclick="searchByTag(\'' + t + '\')">' + t + '</span>').join('');
    return '<div class="doc-item" onclick="searchDoc(\'' + escAttr(d.file) + '\')">' +
      '<span class="doc-name">' + escHtml(d.file) + '</span>' +
      '<span class="doc-tags">' + tags + '</span>' +
    '</div>';
  }).join('');
}

function filterDocs() {
  const q = document.getElementById('docFilter').value.toLowerCase();
  renderDocs(q ? allDocs.filter(d => d.file.toLowerCase().includes(q) || d.tags.some(t => t.toLowerCase().includes(q))) : allDocs);
}

function searchDoc(file) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.querySelector('[data-tab="search"]').classList.add('active');
  document.getElementById('tab-search').classList.add('active');
  document.getElementById('searchQuery').value = file.replace('.md', '');
  doSearch();
}

// ── Tags ──
function renderTagCloud(tags) {
  const el = document.getElementById('tagCloud');
  const entries = Object.entries(tags).sort((a, b) => b[1] - a[1]);
  if (!entries.length) { el.innerHTML = '<div class="empty">No tags found.</div>'; return; }
  el.innerHTML = '<div class="tag-cloud">' + entries.map(([tag, count]) =>
    '<span class="tag" onclick="searchByTag(\'' + tag + '\')">' + escHtml(tag) + '<span class="tag-count">' + count + '</span></span>'
  ).join('') + '</div>';
}

// ── Domains ──
let _allDomains = [];
let _currentDomain = null;
let _currentDomainContent = '';

async function loadDomains() {
  try {
    const resp = await fetch(API + '/api/v1/domains');
    const data = await resp.json();
    _allDomains = data.domains || [];
    const c = data.counts || {};
    document.getElementById('domainCounts').textContent =
      'Draft: ' + (c.draft||0) + '  Active: ' + (c.active||0);
    renderDomainList();
  } catch(e) {
    document.getElementById('domainList').innerHTML = '<div class="empty">Failed to load domains.</div>';
  }
}

function renderDomainList() {
  const filter = document.getElementById('domainFilter').value;
  const filtered = filter === 'all' ? _allDomains : _allDomains.filter(d => d.status === filter);
  const el = document.getElementById('domainList');
  if (!filtered.length) { el.innerHTML = '<div class="empty">No domains found.</div>'; return; }
  el.innerHTML = filtered.map(d =>
    '<div class="domain-item" onclick="openDomain(\'' + escAttr(d.name) + '\')">' +
      '<div class="domain-info">' +
        '<div class="domain-title">' + escHtml(d.name) + '</div>' +
        '<div class="domain-summary">' + escHtml(d.summary || '') + '</div>' +
      '</div>' +
      '<div class="domain-meta">' +
        '<span class="status-badge ' + d.status + '">' + d.status + '</span>' +
        '<span style="color:var(--dim)">' + (d.source_documents||[]).length + ' sources</span>' +
      '</div>' +
    '</div>'
  ).join('');
}

document.getElementById('domainFilter').addEventListener('change', renderDomainList);

function toggleNewDomain() {
  const form = document.getElementById('newDomainForm');
  form.style.display = form.style.display === 'none' ? 'block' : 'none';
  if (form.style.display === 'block') document.getElementById('newDomainTopic').focus();
}

document.getElementById('newDomainTopic').addEventListener('keydown', e => {
  if (e.key === 'Enter') createDomain();
});

async function createDomain() {
  const input = document.getElementById('newDomainTopic');
  const topic = input.value.trim();
  if (!topic) return;

  const btn = document.getElementById('createDomainBtn');
  btn.disabled = true; btn.textContent = 'Analyzing sources...';

  try {
    const resp = await fetch(API + '/api/v1/domains', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ topic }),
    });
    const data = await resp.json();
    if (data.status === 'created') {
      input.value = '';
      document.getElementById('newDomainForm').style.display = 'none';
      await loadDomains();
      openDomain(data.domain_name);
    } else if (data.error) {
      alert('Error: ' + data.error);
    }
  } catch(e) {
    alert('Failed: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Create';
  }
}

async function openDomain(name) {
  _currentDomain = name;
  document.getElementById('domainListView').style.display = 'none';
  document.getElementById('domainDetail').style.display = 'block';
  document.getElementById('domainDetailName').textContent = name;
  document.getElementById('domainContent').textContent = 'Loading...';
  document.getElementById('domainSources').innerHTML = '<div class="loading">Loading...</div>';

  try {
    const resp = await fetch(API + '/api/v1/domains/' + encodeURIComponent(name));
    const data = await resp.json();

    const badge = document.getElementById('domainDetailStatus');
    badge.textContent = data.status;
    badge.className = 'status-badge ' + data.status;
    document.getElementById('activateBtn').style.display = data.status === 'draft' ? 'inline-block' : 'none';

    _currentDomainContent = data.content || '';
    document.getElementById('domainContent').textContent = _currentDomainContent;

    const srcEl = document.getElementById('domainSources');
    srcEl.innerHTML = (data.source_documents || []).map(s =>
      '<div class="source-item">' +
        '<div class="source-name">' + escHtml(s.file) + '</div>' +
        '<div class="source-preview">' + escHtml((s.content||'').substring(0, 500)) + '</div>' +
      '</div>'
    ).join('') || '<div class="empty">No source documents.</div>';

    const chatEl = document.getElementById('chatMessages');
    chatEl.innerHTML = '';
    (data.chat_history || []).forEach(msg => appendChatMsg(msg.role, msg.content));
    chatEl.scrollTop = chatEl.scrollHeight;
  } catch(e) {
    document.getElementById('domainContent').textContent = 'Error: ' + e.message;
  }
}

function closeDomainDetail() {
  _currentDomain = null;
  document.getElementById('domainDetail').style.display = 'none';
  document.getElementById('domainListView').style.display = 'block';
  loadDomains();
}

async function deleteDomain() {
  if (!_currentDomain) return;
  const status = document.getElementById('domainDetailStatus').textContent;
  const isActive = status === 'active';
  const warn = '이 도메인을 모든 표면(MD + 패키지 yaml + DB row + 검색 인덱스)에서 완전 제거합니다.\\n되돌릴 수 없습니다.'
    + (isActive ? '\\n\\n active 도메인입니다 — 사용자 SSOT 가 사라집니다. 정말 삭제하시겠습니까?' : '');
  if (!confirm(warn)) return;
  if (isActive && !confirm('한 번 더 확인: active 도메인 "' + _currentDomain + '" 을(를) 강제 삭제합니다.')) return;
  try {
    const resp = await fetch(API + '/api/v1/ontology/delete_domain',
      { method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ domain_name: _currentDomain, allow_active: isActive }) });
    const data = await resp.json();
    if (data.status === 'deleted') {
      const s = data.surfaces || {};
      alert('삭제 완료: MD=' + (s.md ? 'O' : '-')
        + ' / 패키지파일=' + (s.package_files || 0)
        + ' / DB도메인row=' + (s.db_domain_row ? 'O' : '-')
        + ' / 분류=' + (s.db_classifications || 0)
        + ' / 재인덱싱=' + ((data.reindex||{}).synced || 0) + '개 도메인');
      closeDomainDetail();
    } else {
      alert('삭제 실패: ' + (data.reason || data.status || data.error || 'unknown'));
    }
  } catch(e) {
    alert('삭제 오류: ' + e.message);
  }
}

function appendChatMsg(role, content) {
  const el = document.getElementById('chatMessages');
  const div = document.createElement('div');
  div.className = 'chat-msg ' + role;
  div.textContent = content;
  el.appendChild(div);
}

async function sendChat() {
  const input = document.getElementById('chatInput');
  const message = input.value.trim();
  if (!message || !_currentDomain) return;

  input.value = '';
  appendChatMsg('user', message);
  const chatEl = document.getElementById('chatMessages');
  chatEl.scrollTop = chatEl.scrollHeight;

  const btn = document.getElementById('chatSendBtn');
  // 사용자 메시지가 2개 이하면 첫 분석 단계 (guide + user 첫 응답)
  const userMsgCount = document.querySelectorAll('#chatMessages .chat-msg.user').length;
  btn.disabled = true;
  btn.textContent = userMsgCount <= 2 ? 'Analyzing sources...' : 'Thinking...';

  try {
    const resp = await fetch(
      API + '/api/v1/domains/' + encodeURIComponent(_currentDomain) + '/chat',
      { method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ message }) }
    );
    const data = await resp.json();
    if (data.content) appendChatMsg('assistant', data.content);
    else if (data.error) appendChatMsg('assistant', '[Error] ' + data.error);
  } catch(e) {
    appendChatMsg('assistant', '[Error] ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Send';
    chatEl.scrollTop = chatEl.scrollHeight;
  }
}

document.getElementById('chatInput').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
});

function applyToDocument() {
  const msgs = document.querySelectorAll('#chatMessages .chat-msg.assistant');
  if (!msgs.length) { alert('No LLM response to apply.'); return; }
  const lastResponse = msgs[msgs.length - 1].textContent;

  // LLM 응답에서 마크다운 섹션 추출하여 도메인 문서에 추가
  const currentContent = _currentDomainContent;
  const newContent = currentContent.trimEnd() + '\n\n' + lastResponse.trim() + '\n';
  _currentDomainContent = newContent;
  document.getElementById('domainContent').textContent = newContent;

  // 서버에 저장
  fetch(API + '/api/v1/domains/' + encodeURIComponent(_currentDomain) + '/update',
    { method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ content: newContent }) }
  ).then(r => r.json()).then(data => {
    if (data.status === 'updated') appendChatMsg('assistant', '[System] Document updated.');
  }).catch(e => appendChatMsg('assistant', '[Error] Save failed: ' + e.message));
}

async function activateDomain() {
  if (!_currentDomain) return;
  if (!confirm('Activate this domain? It will be included in vector indexing.')) return;

  try {
    const resp = await fetch(
      API + '/api/v1/domains/' + encodeURIComponent(_currentDomain) + '/activate',
      { method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ content: _currentDomainContent }) }
    );
    const data = await resp.json();
    if (data.status === 'activated') {
      document.getElementById('domainDetailStatus').textContent = 'active';
      document.getElementById('domainDetailStatus').className = 'status-badge active';
      document.getElementById('activateBtn').style.display = 'none';
      _currentDomainContent = _currentDomainContent.replace('status: draft', 'status: active');
      document.getElementById('domainContent').textContent = _currentDomainContent;
      appendChatMsg('assistant', '[System] Domain activated and indexed.');
    }
  } catch(e) {
    alert('Activation failed: ' + e.message);
  }
}

async function clearChat() {
  if (!_currentDomain) return;
  if (!confirm('Clear chat history?')) return;
  try {
    await fetch(API + '/api/v1/domains/' + encodeURIComponent(_currentDomain) + '/chat', { method: 'DELETE' });
    document.getElementById('chatMessages').innerHTML = '';
  } catch(e) { alert('Failed: ' + e.message); }
}

// ── Utils ──
function escHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function escAttr(s) { return s.replace(/'/g, "\\'").replace(/"/g, '&quot;'); }

// ── Init ──
loadStatus();
loadDocs();
</script>
</body>
</html>
"""
