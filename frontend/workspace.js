'use strict';

// Original application implementation; diagram styling is informed by the linked design reference.
(() => {
  const I = globalThis.NoFakeNewsI18n;
  const rows = [
    ['report.end','保留来源，也保留问题。','Keep the sources. Keep the questions.','出典も、問いも残す。'],
    ['depth.brief','简要','Brief','簡潔'],
    ['depth.standard','标准','Standard','標準'],
    ['depth.deep','深入','Deep','詳細'],
    ['map.title','证据关系图','Evidence map','証拠の関連図'],
    ['map.help','从命题出发，查看来源如何连接到数据、逻辑和历史分析。','Follow a claim through its sources and comparative analysis.','主張から出典、データ・論理・歴史分析へのつながりを確認します。'],
    ['map.claim','待核查命题','Claim to investigate','検証する主張'],
    ['map.sources','原始资料','Source material','出典資料'],
    ['map.analysis','资料比对 / 可选推论','Comparisons / optional reasoning','比較分析・任意の論証'],
    ['map.select','选择图中命题','Claim shown in map','図に表示する主張'],
    ['map.scope','当前图：{claim} · {sources} 个来源 · {analysis} 项分析','This map: {claim} · {sources} sources · {analysis} analysis items','表示中：{claim}・出典 {sources} 件・分析 {analysis} 件'],
    ['map.note','连线表示已记录的引用关联，不代表因果、证明或可信度分数。点击节点阅读完整内容。','Lines show recorded citation relationships, not causation, proof, or confidence scores. Select a node to read it.','線は記録された引用関係を示し、因果・証明・信頼度ではありません。ノードを選ぶと全文を読めます。'],
    ['map.table','查看完整关系表','Show relationship table','関連の一覧表を表示'],
    ['map.from','起点','From','起点'],
    ['map.to','终点','To','接続先'],
    ['map.relation','关联','Relationship','関連'],
    ['map.citation','引用','Citation','引用'],
    ['map.inspect','节点详情','Selected node','選択したノード'],
    ['map.open','打开原始来源 ↗','Open original source ↗','原資料を開く ↗'],
    ['map.jump','定位完整来源卡片','Go to source record','出典の詳細へ移動'],
    ['map.empty','该命题尚未提供关联资料。','No source relationships were provided for this claim.','この主張に関連する資料はありません。'],
    ['map.data','数据口径','Data definitions','データの定義'],
    ['map.logic','逻辑前提','Logical premises','論理の前提'],
    ['map.history','历史比较','Historical comparison','歴史比較'],
    ['map.reason','AI 推论','AI reasoning','AI の論証'],
    ['language.summary','判断语言：{language}；原资料与基础分析保持原语言。','Judgment language: {language}; existing evidence and analysis retain their original language.','判断の言語：{language}。既存の資料と分析は元の言語を保持します。'],
    ['sources.invalid','请输入不含账户、密码或片段的 HTTP/HTTPS 公网资料 URL。','Enter a public HTTP/HTTPS source URL without embedded credentials or a fragment.','認証情報やフラグメントを含まない公開 HTTP/HTTPS URL を入力してください。'],
    ['sources.limit','最多保存 6 个来源。','Save up to six sources.','保存できる情報源は最大 6 件です。'],
    ['sources.remove','移除 {name}','Remove {name}','{name} を削除'],
    ['sources.none','尚未保存常驻来源。','No resident sources saved.','保存した情報源はありません。'],
    ['sources.summary','{count} 个常驻来源 · {policy}','{count} resident sources · {policy}','保存済み {count} 件・{policy}'],
    ['sources.wide','全网交叉核对','Broader-web cross-check','ウェブ全体も照合'],
    ['sources.restricted','仅指定域名','Selected domains only','指定ドメインのみ'],
    ['sources.need','限定检索需要至少一个来源。','Add at least one source before restricting search.','検索を限定するには情報源を追加してください。'],
    ['credentials.invalid','凭据需精确的 HTTPS Origin；Basic 需账号及密码，Cookie/Bearer 需令牌。禁止换行等控制字符。','Use an exact HTTPS origin. Basic needs username/password; Cookie/Bearer needs a token. Control characters are not allowed.','正確な HTTPS オリジンを指定してください。Basic はユーザー名とパスワード、Cookie/Bearer はトークンが必要です。制御文字は使えません。'],
    ['credentials.limit','最多保留 6 个会话账户，同一网站仅保留一种。','Up to six session accounts; one authentication method per origin.','セッション認証は最大 6 件、オリジンごとに一つの方式です。'],
    ['credentials.none','本会话尚无网站凭据。','No website credentials in this session.','このセッションにはサイト認証情報がありません。'],
    ['credentials.active','{kind} · 仅本次会话','{kind} · this session only','{kind}・このセッションのみ'],
    ['credentials.clear','清除所有网站凭据','Clear all website credentials','すべてのサイト認証情報を消去'],
    ['credentials.cleared','已清除本会话网站凭据。','Website credentials cleared from this session.','セッションのサイト認証情報を消去しました。'],
    ['errors.language','报告语言无效。','Invalid report language.','レポート言語が無効です。'],
  ];
  for (const [key, ...values] of rows) I.languages.forEach((language, index) => { I.dictionaries[language][key] = values[index]; });
  const t = (key, values) => I.t(key, values);
  const $ = id => document.getElementById(id);
  const make = (tag, className, text, attrs = {}) => {
    const node = document.createElement(tag);
    node.className = className || '';
    if (text != null) node.textContent = String(text);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
    return node;
  };
  const storageKey = 'no-fake-news.sources.v1';
  let sources = [], credentials = [], policy = 'balanced';

  function sourceURL(raw, originOnly = false) {
    const parsed = new URL(raw);
    const host = parsed.hostname.toLowerCase();
    if (!['https:', 'http:'].includes(parsed.protocol) || parsed.username || parsed.password || parsed.hash || /[\s\\]/.test(raw) ||
        !host.includes('.') || /(?:^localhost$|\.local$|\.internal$|\.localhost$)/.test(host)) throw new Error(t('sources.invalid'));
    if (originOnly && (parsed.protocol !== 'https:' || !['', '/'].includes(parsed.pathname) || parsed.search)) throw new Error(t('credentials.invalid'));
    return originOnly ? parsed.origin : parsed.href;
  }

  function safeSourcePreferences(input) {
    const clean = [];
    for (const row of Array.isArray(input?.sources) ? input.sources.slice(0, 6) : []) {
      try {
        const url = sourceURL(String(row.url || ''));
        if (!clean.some(source => source.url === url)) clean.push({ url, label: String(row.label || '').slice(0, 300) });
      } catch { /* Invalid stored records are ignored. No credentials are restored. */ }
    }
    return { sources: clean, source_policy: input?.source_policy === 'preferred-only' ? 'preferred-only' : 'balanced' };
  }

  function persist() {
    const safe = safeSourcePreferences({ sources, source_policy: policy });
    try { localStorage.setItem(storageKey, JSON.stringify(safe)); } catch { /* Session use still works. */ }
  }

  function sourceError(error) { $('sources-error').textContent = error.message; $('sources-error').hidden = false; }
  function removeButton(label, handler) {
    const button = make('button', 'icon-button', '×', { type: 'button', 'aria-label': t('sources.remove', { name: label }) });
    button.addEventListener('click', handler);
    return button;
  }

  function renderSources() {
    const list = $('preferred-source-list');
    list.replaceChildren();
    if (!sources.length) list.append(make('p', 'field-help', t('sources.none')));
    sources.forEach((source, index) => {
      const row = make('div', 'source-setting-row');
      const info = make('div');
      info.append(make('strong', '', source.label || new URL(source.url).hostname), make('span', '', source.url));
      row.append(info, removeButton(source.label || source.url, () => { sources.splice(index, 1); persist(); renderSources(); }));
      list.append(row);
    });
    const accounts = $('credential-list');
    accounts.replaceChildren();
    if (!credentials.length) accounts.append(make('p', 'field-help', t('credentials.none')));
    credentials.forEach((credential, index) => {
      const row = make('div', 'source-setting-row');
      const info = make('div');
      info.append(make('strong', '', credential.origin), make('span', '', t('credentials.active', { kind: credential.kind })));
      row.append(info, removeButton(credential.origin, () => { credentials.splice(index, 1); renderSources(); }));
      accounts.append(row);
    });
    if (credentials.length) {
      const clear = make('button', 'import-button', t('credentials.clear'), { type: 'button' });
      clear.addEventListener('click', () => { credentials = []; renderSources(); });
      accounts.append(clear);
    }
    $('source-policy').value = policy;
    $('sources-summary').textContent = t('sources.summary', { count: sources.length, policy: t(policy === 'balanced' ? 'sources.wide' : 'sources.restricted') });
  }

  function setupSources() {
    try { const saved = safeSourcePreferences(JSON.parse(localStorage.getItem(storageKey) || '{}')); sources = saved.sources; policy = saved.source_policy; } catch { /* Ignore invalid preferences. */ }
    const open = () => { $('sources-error').hidden = true; renderSources(); $('sources-dialog').showModal(); };
    ['open-sources', 'configure-sources'].forEach(id => $(id).addEventListener('click', open));
    ['close-sources', 'done-sources'].forEach(id => $(id).addEventListener('click', () => $('sources-dialog').close()));
    $('add-source').addEventListener('click', () => {
      try {
        if (sources.length >= 6) throw new Error(t('sources.limit'));
        const url = sourceURL($('source-url').value.trim());
        if (!sources.some(source => source.url === url)) sources.push({ url, label: $('source-label').value.trim().slice(0, 300) });
        $('source-label').value = ''; $('source-url').value = ''; $('sources-error').hidden = true;
        persist(); renderSources();
      } catch (error) { sourceError(error); }
    });
    $('source-policy').addEventListener('change', () => { policy = $('source-policy').value; persist(); renderSources(); });
    $('credential-kind').addEventListener('change', () => {
      const basic = $('credential-kind').value === 'basic';
      $('basic-credential-fields').hidden = !basic; $('token-credential-fields').hidden = basic;
    });
    $('add-credential').addEventListener('click', () => {
      try {
        const origin = sourceURL($('credential-origin').value.trim(), true);
        const kind = $('credential-kind').value, username = $('credential-username').value.trim(), password = $('credential-password').value, token = $('credential-token').value.trim();
        if ([username, password, token].some(value => /[\x00-\x1f\x7f]/.test(value)) || password.length > 8192 || token.length > 8192 ||
            (kind === 'basic' ? !username || !password || username.includes(':') : !token)) throw new Error(t('credentials.invalid'));
        if (credentials.length >= 6 && !credentials.some(c => c.origin === origin)) throw new Error(t('credentials.limit'));
        credentials = credentials.filter(c => c.origin !== origin);
        credentials.push(kind === 'basic' ? { origin, kind, username, password } : { origin, kind, token });
        ['credential-origin', 'credential-username', 'credential-password', 'credential-token'].forEach(id => { $(id).value = ''; });
        $('sources-error').hidden = true; renderSources();
      } catch (error) { sourceError(error); }
    });
    renderSources();
  }

  function getSourceRequest() {
    if (policy === 'preferred-only' && !sources.length) throw new Error(t('sources.need'));
    return { sources: structuredClone(sources), source_policy: policy, source_credentials: structuredClone(credentials) };
  }

  function graphData(report, selected) {
    const claim = report.claims.find(c => c.id === selected) || report.claims[0];
    const observations = (report.observations || []).map((item, index) => ({ ...item, nodeId: `observation-${index}` })).filter(item => item.claim_ids.includes(claim.id));
    const reasoning = report.mode === 'ai-summary' ? (report.reasoning || []).filter(item => item.claim_id === claim.id) : [];
    const ids = new Set((report.links || []).filter(link => link.to === claim.id).map(link => link.from));
    (report.evidence || []).filter(source => source.claim_ids.includes(claim.id)).forEach(source => ids.add(source.id));
    observations.forEach(item => item.evidence_ids.forEach(id => ids.add(id)));
    reasoning.forEach(item => item.premise_ids.filter(id => id.startsWith('E')).forEach(id => ids.add(id)));
    const sourceNodes = (report.evidence || []).filter(source => ids.has(source.id));
    const edges = [];
    sourceNodes.forEach(source => {
      const explicit = (report.links || []).filter(link => link.from === source.id && link.to === claim.id);
      if (explicit.length) explicit.forEach(link => edges.push({ from: source.id, to: claim.id, relation: report.mode === 'evidence-only' && link.relation !== 'context' ? 'relevant_to' : link.relation }));
      else if (source.claim_ids.includes(claim.id)) edges.push({ from: source.id, to: claim.id, relation: 'relevant_to' });
    });
    observations.forEach(item => item.evidence_ids.forEach(id => edges.push({ from: id, to: item.nodeId, relation: 'citation' })));
    const available = new Set([...sourceNodes.map(item => item.id), ...reasoning.map(item => item.id)]);
    reasoning.forEach(item => item.premise_ids.filter(id => available.has(id)).forEach(id => edges.push({ from: id, to: item.id, relation: 'citation' })));
    return { claim, sources: sourceNodes, observations, reasoning, edges };
  }

  function renderMap(report, hooks) {
    const data = graphData(report, hooks.selected);
    const section = make('section', 'report-section evidence-map', '', { id: 'evidence-map', 'aria-label': t('map.title') });
    const header = make('div', 'map-heading');
    const words = make('div'); words.append(make('span', 'section-kicker', '01 / EVIDENCE MAP'), make('h2', '', t('map.title')), make('p', '', t('map.help')));
    const select = make('select', 'map-select', '', { 'aria-label': t('map.select'), 'data-map-control': '' });
    report.claims.forEach(claim => { const option = make('option', '', `${claim.id} · ${claim.text.slice(0, 45)}`, { value: claim.id }); option.selected = claim.id === data.claim.id; select.append(option); });
    select.addEventListener('change', () => hooks.select(select.value));
    header.append(words, select); section.append(header);
    section.append(make('p', 'map-scope', t('map.scope', { claim: data.claim.id, sources: data.sources.length, analysis: data.observations.length + data.reasoning.length })));
    const analysis = [...data.observations, ...data.reasoning.map(item => ({ ...item, nodeId: item.id, isReasoning: true }))];
    const height = Math.max(224, Math.max(data.sources.length, analysis.length) * 116 + 64);
    const viewport = make('div', 'map-viewport', '', { tabindex: '0', 'aria-label': t('map.title') });
    const canvas = make('div', 'map-canvas'); canvas.style.height = `${height}px`;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', `0 0 960 ${height}`); svg.setAttribute('class', 'map-wires'); svg.setAttribute('aria-hidden', 'true');
    canvas.append(svg);
    [[24, 'map.claim'], [276, 'map.sources'], [616, 'map.analysis']].forEach(([left, label]) => { const text = make('span', 'map-column-label', t(label)); text.style.left = `${left}px`; canvas.append(text); });
    const positions = new Map();
    const inspector = make('div', 'map-inspector', '', { 'aria-live': 'polite' });
    function inspect(node, button) {
      canvas.querySelectorAll('.map-node').forEach(item => item.classList.toggle('selected', item === button));
      inspector.replaceChildren(make('span', 'section-kicker', t('map.inspect')), make('h3', '', node.title), make('p', '', node.text));
      if (node.url) {
        const link = make('a', 'map-original', t('map.open'), { href: node.url, target: '_blank', rel: 'noopener noreferrer' });
        const jump = make('button', 'import-button', t('map.jump'), { type: 'button', 'data-map-control': '' }); jump.addEventListener('click', () => hooks.focusSource(node.id));
        inspector.append(link, jump);
      }
      if (node.refs?.length) inspector.append(make('p', 'map-citations', node.refs.join(' · ')));
    }
    function node(item, x, y, width, kind) {
      positions.set(item.id, { x, y, width });
      const button = make('button', `map-node map-node-${kind}`, '', { type: 'button' });
      Object.assign(button.style, { left: `${x}px`, top: `${y}px`, width: `${width}px` });
      button.append(make('span', 'map-node-id', item.label), make('strong', '', item.title), make('span', 'map-node-preview', item.text));
      button.addEventListener('click', () => inspect(item, button)); canvas.append(button);
      return button;
    }
    const claimNode = { id: data.claim.id, label: data.claim.id, title: t('map.claim'), text: data.claim.text };
    const first = node(claimNode, 24, 64, 184, 'claim');
    data.sources.forEach((source, index) => node({ id: source.id, label: source.id, title: source.publisher || new URL(source.url).hostname, text: source.title, url: source.url, refs: source.claim_ids }, 276, 64 + index * 116, 252, 'source'));
    analysis.forEach((item, index) => node({ id: item.nodeId, label: item.isReasoning ? item.id : t(`map.${item.kind}`), title: item.isReasoning ? t('map.reason') : t(`map.${item.kind}`), text: item.text, refs: item.evidence_ids || item.premise_ids }, 616, 64 + index * 116, 320, item.isReasoning ? 'reason' : 'analysis'));
    for (const edge of data.edges) {
      const from = positions.get(edge.from), to = positions.get(edge.to);
      if (!from || !to) continue;
      const path = document.createElementNS(svg.namespaceURI, 'path');
      const y1 = from.y + 48, y2 = to.y + 48;
      if (to.x > from.x) {
        const x1 = from.x + from.width, x2 = to.x;
        path.setAttribute('d', `M ${x1} ${y1} C ${x1 + 40} ${y1}, ${x2 - 40} ${y2}, ${x2} ${y2}`);
      } else if (to.x < from.x) {
        const x1 = from.x, x2 = to.x + to.width;
        path.setAttribute('d', `M ${x1} ${y1} C ${x1 - 32} ${y1}, ${x2 + 32} ${y2}, ${x2} ${y2}`);
      } else {
        const x1 = from.x + from.width, x2 = to.x + to.width;
        path.setAttribute('d', `M ${x1} ${y1} C ${x1 + 18} ${y1}, ${x2 + 18} ${y2}, ${x2} ${y2}`);
      }
      if (edge.relation === 'context') path.setAttribute('stroke-dasharray', '4 4');
      svg.append(path);
    }
    viewport.append(canvas); section.append(viewport, make('p', 'map-note', t('map.note')), inspector);
    inspect(claimNode, first);
    if (!data.sources.length) section.append(make('p', 'no-data', t('map.empty')));
    const details = make('details', 'map-table'); details.append(make('summary', '', t('map.table')));
    const table = make('table'), head = make('tr'); ['map.from', 'map.to', 'map.relation'].forEach(key => head.append(make('th', '', t(key), { scope: 'col' })));
    const thead = make('thead'); thead.append(head); table.append(thead);
    const tbody = make('tbody');
    data.edges.forEach(edge => { const row = make('tr'); [edge.from, edge.to.startsWith('observation-') ? `${t('map.analysis')} ${Number(edge.to.split('-')[1]) + 1}` : edge.to, edge.relation === 'citation' ? t('map.citation') : hooks.relationLabel(edge.relation)].forEach(text => row.append(make('td', '', text))); tbody.append(row); });
    table.append(tbody); details.append(table); section.append(details);
    return section;
  }
  const api = { setupSources, renderSources, getSourceRequest, safeSourcePreferences, sourceURL, graphData, renderMap };
  globalThis.NoFakeNewsWorkspace = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
