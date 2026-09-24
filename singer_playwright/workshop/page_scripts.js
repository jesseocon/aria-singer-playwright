/** Generalized page-model scripts for the Playwright scraper workshop. */

function normalizeText(value) {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function collectPageInfoScript(pageLabel) {
  const tabs = Array.from(document.querySelectorAll('[role="tab"]')).map((el) => ({
    text: normalizeText(el.textContent),
    selected: el.getAttribute("aria-selected") === "true",
    href: el.getAttribute("href"),
  }));

  const links = Array.from(document.querySelectorAll("a"))
    .map((el) => normalizeText(el.textContent))
    .filter((t) => t.length > 0 && t.length < 60);

  const buttons = Array.from(document.querySelectorAll("button"))
    .map((el) => normalizeText(el.textContent))
    .filter((t) => t.length > 0 && t.length < 60);

  const subNav = Array.from(
    document.querySelectorAll('[role="tablist"] [role="tab"], nav a, [class*="sub"] a, [class*="sub"] button'),
  )
    .map((el) => normalizeText(el.textContent))
    .filter(Boolean);

  const bodyText = normalizeText(document.body?.textContent ?? "");
  const loginSignals = {
    hasEmailInput: !!document.querySelector('input[type="email"]'),
    hasPasswordInput: !!document.querySelector('input[type="password"]'),
    loginMarkers: ["sign in", "log in", "password", "forgot password"].filter((m) =>
      bodyText.toLowerCase().includes(m),
    ),
    urlLooksLikeLogin: /login|signin|sign-in/i.test(location.href),
  };

  return {
    label: pageLabel,
    url: location.href,
    title: document.title,
    tabs: tabs.slice(0, 20),
    subNav: [...new Set(subNav)].slice(0, 30),
    links: [...new Set(links)].slice(0, 40),
    buttons: [...new Set(buttons)].slice(0, 40),
    iframeCount: document.querySelectorAll("iframe").length,
    loginSignals,
    bodyPreview: bodyText.slice(0, 1500),
  };
}

function getInteractiveControlsScript() {
  return Array.from(document.querySelectorAll("a, button, [role='tab'], [role='link'], input, select"))
    .slice(0, 80)
    .map((el, index) => ({
      index,
      tag: el.tagName,
      role: el.getAttribute("role"),
      type: el.getAttribute("type"),
      text: normalizeText(el.textContent || el.getAttribute("aria-label") || el.getAttribute("placeholder")).slice(
        0,
        80,
      ),
      href: el.getAttribute("href"),
      name: el.getAttribute("name"),
      id: el.id || null,
      className: (el.className || "").slice(0, 120),
    }))
    .filter((item) => item.text || item.href || item.name || item.type);
}

function findTableCandidatesScript() {
  const markers = [
    "As of Date",
    "On The Books",
    "Revenue",
    "Rate Shop",
    "Forecast",
    "Date",
    "Total",
    "Amount",
  ];

  const preferred = document.querySelector("table.analytics.day-by-day");
  if (preferred) {
    const headers = Array.from(preferred.querySelectorAll("thead th")).map((cell, index) =>
      normalizeText(cell.textContent).replace(/\s+/g, "_").toLowerCase() || `column_${index}`,
    );
    return [
      {
        selector: "table.analytics.day-by-day",
        tag: preferred.tagName,
        className: preferred.className,
        rowCount: preferred.querySelectorAll("tbody tr").length,
        headers: headers.slice(0, 40),
        score: 100,
      },
    ];
  }

  const candidates = Array.from(
    document.querySelectorAll('table, [role="grid"], [role="table"], [class*="table"], [class*="grid"]'),
  )
    .map((el) => {
      const text = normalizeText(el.textContent);
      const markerHits = markers.filter((m) => text.includes(m)).length;
      const headers = Array.from(el.querySelectorAll("thead th, [role='columnheader']"))
        .map((cell, index) => normalizeText(cell.textContent).replace(/\s+/g, "_").toLowerCase() || `column_${index}`)
        .slice(0, 40);
      const rowCount = el.querySelectorAll("tbody tr, [role='row']").length;
      const score =
        markerHits * 10 + (el.classList?.contains("day-by-day") ? 50 : 0) + Math.min(rowCount, 20);
      let selector = el.tagName.toLowerCase();
      if (el.id) selector = `#${el.id}`;
      else if (el.className) selector = `${el.tagName.toLowerCase()}.${String(el.className).split(/\s+/)[0]}`;
      return {
        selector,
        tag: el.tagName,
        className: el.className,
        rowCount,
        headers,
        score,
        textPreview: text.slice(0, 200),
      };
    })
    .filter((item) => item.score > 0 || item.rowCount >= 3)
    .sort((a, b) => b.score - a.score)
    .slice(0, 10);

  return candidates;
}

function extractTableScript(selector) {
  const table = selector ? document.querySelector(selector) : document.querySelector("table.analytics.day-by-day");
  if (!table) {
    return { headers: [], rows: [], error: selector ? `Selector not found: ${selector}` : "No table found" };
  }

  const headerCells = Array.from(table.querySelectorAll("thead th, [role='columnheader']"));
  const headers = headerCells.map((cell, index) => {
    const text = normalizeText(cell.textContent).replace(/\s+/g, "_").toLowerCase();
    return text || `column_${index}`;
  });

  const bodyRows = Array.from(table.querySelectorAll("tbody tr, [role='row']")).filter((row) =>
    row.querySelector("td, [role='gridcell'], [role='cell']"),
  );

  const rows = bodyRows.slice(0, 500).map((row) => {
    const cells = Array.from(row.querySelectorAll("td, [role='gridcell'], [role='cell']"));
    const record = {};
    cells.forEach((cell, index) => {
      const key = headers[index] || `column_${index}`;
      record[key] = normalizeText(cell.textContent);
    });
    return record;
  });

  return { headers, rows, error: null, rowCount: rows.length };
}

function detectLoadingScript() {
  const loading = document.querySelector('.loading-indicator, .spinner, [class*="loading"], [aria-busy="true"]');
  const visible =
    loading && loading instanceof HTMLElement && loading.offsetParent !== null && loading.offsetWidth > 0;
  return { loading: !!visible, reason: visible ? "loading indicator visible" : null };
}

function analyzePageScript() {
  const body = normalizeText(document.body?.textContent ?? "");
  const tables = findTableCandidatesScript();
  const loading = detectLoadingScript();
  return {
    url: location.href,
    title: document.title,
    hasAsOfDate: body.includes("As of Date"),
    loading,
    tables,
    bodyPreview: body.slice(0, 1200),
  };
}
