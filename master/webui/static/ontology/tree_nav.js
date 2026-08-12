/* Ontology Viewer — 공용 트리 네비게이션 + 패널 리사이저 (Phase η.9.1, 2026-07-25)
 * index.html(도메인 목록) · domain.html(도메인 상세) 양쪽에서 공유.
 * - renderDomainTree: /api/v1/ontology/domains 를 parent_domain 기반 트리로 그려 좌측 tree-nav 에 삽입
 * - setupResizer: 패널 사이 구분선 드래그 리사이즈 + localStorage 폭 기억
 * 전역 window.OntologyTreeNav 로 노출 (모듈 번들러 없이 <script> 순서 로딩).
 */
(function () {
  function escapeHtmlLocal(s) {
    return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // parent_domain 으로 부모→자식 매핑 (index.html loadDomains 의 계층 구성 로직과 동일 규칙)
  function buildTree(domains) {
    const byName = {};
    for (const d of domains) byName[d.name] = d;
    const knownSet = new Set(domains.map(d => d.name));
    const childrenMap = {};
    for (const d of domains) {
      const p = d.parent_domain || "";
      if (p && knownSet.has(p)) (childrenMap[p] = childrenMap[p] || []).push(d);
    }
    for (const k in childrenMap) childrenMap[k].sort((a, b) => a.name.localeCompare(b.name));
    const topLevel = domains
      .filter(d => !d.parent_domain || !knownSet.has(d.parent_domain))
      .sort((a, b) => a.name.localeCompare(b.name));
    return { byName, childrenMap, topLevel };
  }

  // 현재 도메인의 상위 체인 — 자동 펼침 대상 (순환 방지 guard)
  function ancestorChain(name, byName) {
    const chain = new Set();
    let cur = name;
    let guard = 0;
    while (cur && byName[cur] && guard++ < 50) {
      const parent = byName[cur].parent_domain;
      if (!parent || !byName[parent] || chain.has(parent)) break;
      chain.add(parent);
      cur = parent;
    }
    return chain;
  }

  function renderNode(d, childrenMap, currentName, openSet, container) {
    const kids = childrenMap[d.name] || [];
    const hasKids = kids.length > 0;

    const row = document.createElement("a");
    row.className = "tree-row" + (d.name === currentName ? " current" : "");
    row.href = "/ontology/domain/" + encodeURIComponent(d.name);
    const tier = (d.tier === 1 || d.tier === 2 || d.tier === 3) ? d.tier : 0;
    row.innerHTML =
      `<span class="caret${hasKids ? "" : " leaf"}">${hasKids ? "▸" : ""}</span>` +
      `<span class="tier-dot t${tier}"></span>` +
      `<span class="tn-label">${escapeHtmlLocal(d.name)}</span>`;

    const item = document.createElement("div");
    item.className = "tree-item";
    item.appendChild(row);

    if (hasKids) {
      const childWrap = document.createElement("div");
      const open = openSet.has(d.name);
      childWrap.className = "tree-children" + (open ? " expanded" : "");
      if (open) row.classList.add("open");
      for (const k of kids) renderNode(k, childrenMap, currentName, openSet, childWrap);
      item.appendChild(childWrap);

      // caret 클릭만 접기/펼치기 — 나머지 영역 클릭은 <a href> 기본 동작(이동)에 맡김
      const caret = row.querySelector(".caret");
      caret.addEventListener("click", evt => {
        evt.preventDefault();
        evt.stopPropagation();
        const opened = childWrap.classList.toggle("expanded");
        row.classList.toggle("open", opened);
      });
    }

    container.appendChild(item);
  }

  async function fetchDomains() {
    const res = await fetch("/api/v1/ontology/domains");
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    return data.domains || [];
  }

  /**
   * rootEl 안에 "도메인 트리" 헤더 + 트리를 렌더링.
   * currentName 을 주면 해당 항목 강조 + 그 상위 체인·자기 자신을 자동 펼침.
   */
  async function renderDomainTree(rootEl, currentName) {
    rootEl.innerHTML = '<div class="nav-head">도메인 트리</div><div class="loading" style="padding:10px 14px;font-size:12px;">로딩 중…</div>';
    let domains;
    try {
      domains = await fetchDomains();
    } catch (err) {
      rootEl.innerHTML = '<div class="nav-head">도메인 트리</div><div class="empty" style="padding:10px 14px;font-size:12px;">로딩 실패</div>';
      return;
    }
    rootEl.innerHTML = '<div class="nav-head">도메인 트리</div>';
    if (domains.length === 0) {
      rootEl.innerHTML += '<div class="empty" style="padding:10px 14px;font-size:12px;">등록된 도메인 없음</div>';
      return;
    }
    const { byName, childrenMap, topLevel } = buildTree(domains);
    const openSet = currentName ? ancestorChain(currentName, byName) : new Set();
    if (currentName) openSet.add(currentName);
    for (const d of topLevel) renderNode(d, childrenMap, currentName, openSet, rootEl);
  }

  /**
   * handleEl 을 드래그하면 host(기본 <html>) 의 CSS 커스텀 프로퍼티(targetVar)를 min~max px 범위에서 조절.
   * storageKey 가 있으면 localStorage 에 마지막 폭을 저장해 다음 방문 시 복원.
   */
  function setupResizer(handleEl, targetVar, opts) {
    opts = opts || {};
    const min = opts.min || 160;
    const max = opts.max || 800;
    const storageKey = opts.storageKey || null;
    const host = document.documentElement;

    if (storageKey) {
      const saved = parseInt(localStorage.getItem(storageKey), 10);
      if (!isNaN(saved)) host.style.setProperty(targetVar, Math.min(max, Math.max(min, saved)) + "px");
    }

    let dragging = false;
    let startX = 0;
    let startW = 0;

    handleEl.addEventListener("mousedown", e => {
      dragging = true;
      handleEl.classList.add("dragging");
      startX = e.clientX;
      const cur = parseInt(getComputedStyle(host).getPropertyValue(targetVar), 10);
      startW = isNaN(cur) ? min : cur;
      document.body.style.userSelect = "none";
      e.preventDefault();
    });
    window.addEventListener("mousemove", e => {
      if (!dragging) return;
      const next = Math.min(max, Math.max(min, startW + (e.clientX - startX)));
      host.style.setProperty(targetVar, next + "px");
    });
    window.addEventListener("mouseup", () => {
      if (!dragging) return;
      dragging = false;
      handleEl.classList.remove("dragging");
      document.body.style.userSelect = "";
      if (storageKey) {
        const finalVal = parseInt(getComputedStyle(host).getPropertyValue(targetVar), 10);
        if (!isNaN(finalVal)) localStorage.setItem(storageKey, String(finalVal));
      }
    });
  }

  window.OntologyTreeNav = { renderDomainTree, setupResizer };
})();
