/**
 * Quant Dashboard – client-side logic (v2).
 * Adapted for CSV-based screener data with 6 screening tabs.
 */
(function () {
  "use strict";

  // ── State ──
  let currentScreen = "all";
  let currentPage = 1;
  const pageSize = 50;
  let sortCol = "종합점수";
  let sortOrder = "desc";

  const tbody = document.getElementById("stock-tbody");
  const headerRow = document.getElementById("table-header");
  const pageInfo = document.getElementById("page-info");
  const btnPrev = document.getElementById("btn-prev");
  const btnNext = document.getElementById("btn-next");

  // ── Column definitions per tab ──
  const COLUMNS = {
    all: [
      { key: "종목코드", label: "Code" },
      { key: "종목명", label: "Name" },
      { key: "시장구분", label: "Market" },
      { key: "종가", label: "Price", fmt: "int" },
      { key: "PER", label: "PER", fmt: "f2" },
      { key: "PBR", label: "PBR", fmt: "f2" },
      { key: "ROE(%)", label: "ROE%", fmt: "f2" },
      { key: "영업이익률(%)", label: "OPM%", fmt: "f2" },
      { key: "배당수익률(%)", label: "Div%", fmt: "f2" },
      { key: "매출_CAGR", label: "Rev CAGR", fmt: "f1" },
      { key: "적정주가_SRIM", label: "S-RIM", fmt: "int" },
      { key: "괴리율(%)", label: "Gap%", fmt: "f2" },
      { key: "종합점수", label: "Score", fmt: "f1" },
    ],
    screened: [
      { key: "종목코드", label: "Code" },
      { key: "종목명", label: "Name" },
      { key: "시장구분", label: "Market" },
      { key: "종가", label: "Price", fmt: "int" },
      { key: "PER", label: "PER", fmt: "f2" },
      { key: "PBR", label: "PBR", fmt: "f2" },
      { key: "ROE(%)", label: "ROE%", fmt: "f2" },
      { key: "매출_연속성장", label: "RevGrowth", fmt: "int" },
      { key: "영업이익률(%)", label: "OPM%", fmt: "f2" },
      { key: "배당수익률(%)", label: "Div%", fmt: "f2" },
      { key: "적정주가_SRIM", label: "S-RIM", fmt: "int" },
      { key: "괴리율(%)", label: "Gap%", fmt: "f2" },
      { key: "종합점수", label: "Score", fmt: "f1" },
    ],
    momentum: [
      { key: "종목코드", label: "Code" },
      { key: "종목명", label: "Name" },
      { key: "시장구분", label: "Market" },
      { key: "종가", label: "Price", fmt: "int" },
      { key: "매출_CAGR", label: "Rev CAGR", fmt: "f1" },
      { key: "영업이익_CAGR", label: "OP CAGR", fmt: "f1" },
      { key: "영업이익률(%)", label: "OPM%", fmt: "f2" },
      { key: "ROE(%)", label: "ROE%", fmt: "f2" },
      { key: "PER", label: "PER", fmt: "f2" },
      { key: "이익률_개선", label: "Improved", fmt: "flag" },
      { key: "종합점수", label: "Score", fmt: "f1" },
    ],
    garp: [
      { key: "종목코드", label: "Code" },
      { key: "종목명", label: "Name" },
      { key: "시장구분", label: "Market" },
      { key: "종가", label: "Price", fmt: "int" },
      { key: "PEG", label: "PEG", fmt: "f2" },
      { key: "매출_CAGR", label: "Rev CAGR", fmt: "f1" },
      { key: "순이익_CAGR", label: "NI CAGR", fmt: "f1" },
      { key: "ROE(%)", label: "ROE%", fmt: "f2" },
      { key: "PER", label: "PER", fmt: "f2" },
      { key: "괴리율(%)", label: "Gap%", fmt: "f2" },
      { key: "종합점수", label: "Score", fmt: "f1" },
    ],
    cashcow: [
      { key: "종목코드", label: "Code" },
      { key: "종목명", label: "Name" },
      { key: "시장구분", label: "Market" },
      { key: "종가", label: "Price", fmt: "int" },
      { key: "FCF수익률(%)", label: "FCF%", fmt: "f2" },
      { key: "영업이익률(%)", label: "OPM%", fmt: "f2" },
      { key: "부채비율(%)", label: "Debt%", fmt: "f1" },
      { key: "ROE(%)", label: "ROE%", fmt: "f2" },
      { key: "이익품질_양호", label: "Quality", fmt: "flag" },
      { key: "배당수익률(%)", label: "Div%", fmt: "f2" },
      { key: "종합점수", label: "Score", fmt: "f1" },
    ],
    turnaround: [
      { key: "종목코드", label: "Code" },
      { key: "종목명", label: "Name" },
      { key: "시장구분", label: "Market" },
      { key: "종가", label: "Price", fmt: "int" },
      { key: "흑자전환", label: "B/E Turn", fmt: "flag" },
      { key: "이익률_급개선", label: "OPM Jump", fmt: "flag" },
      { key: "이익률_변동폭", label: "OPM Delta", fmt: "f1" },
      { key: "영업이익률(%)", label: "OPM%", fmt: "f2" },
      { key: "ROE(%)", label: "ROE%", fmt: "f2" },
      { key: "PER", label: "PER", fmt: "f2" },
      { key: "종합점수", label: "Score", fmt: "f1" },
    ],
  };

  // ── Helpers ──
  function fmt(v, type) {
    if (v === null || v === undefined) return "-";
    if (type === "int") return Number(v).toLocaleString("ko-KR", { maximumFractionDigits: 0 });
    if (type === "f1") return Number(v).toFixed(1);
    if (type === "f2") return Number(v).toFixed(2);
    if (type === "flag") return Number(v) === 1 ? "O" : "-";
    return String(v);
  }

  function valClass(v) {
    if (v === null || v === undefined) return "";
    return Number(v) > 0 ? "val-pos" : Number(v) < 0 ? "val-neg" : "";
  }

  function showToast(msg) {
    document.getElementById("toast-body").textContent = msg;
    new bootstrap.Toast(document.getElementById("toast-msg")).show();
  }

  // ── Market summary ──
  async function loadSummary() {
    try {
      const res = await fetch("/api/markets/summary");
      const data = await res.json();
      document.getElementById("market-summary").innerHTML = data.map(m => `
        <div class="col-md-3 col-6">
          <div class="card summary-card ${m.market === "KOSDAQ" ? "kosdaq" : ""} p-3">
            <div class="card-title">${m.market}</div>
            <div class="metric-value">${(m.stock_count || 0).toLocaleString()} stocks</div>
            <div class="small text-muted">
              PER(med) ${m.avg_per != null ? Number(m.avg_per).toFixed(1) : "-"}
              &middot; PBR ${m.avg_pbr != null ? Number(m.avg_pbr).toFixed(2) : "-"}
              &middot; ROE ${m.avg_roe != null ? Number(m.avg_roe).toFixed(1) + "%" : "-"}
            </div>
          </div>
        </div>`).join("");
    } catch (e) { console.error("Summary error", e); }
  }

  // ── Tab counts ──
  async function loadTabCounts() {
    const screens = ["all", "screened", "momentum", "garp", "cashcow", "turnaround"];
    for (const s of screens) {
      try {
        const res = await fetch(`/api/stocks?screen=${s}&size=1`);
        const data = await res.json();
        const el = document.getElementById(`cnt-${s}`);
        if (el) el.textContent = data.total || 0;
      } catch (e) { /* ignore */ }
    }
  }

  // ── Build table header ──
  function buildHeader() {
    const cols = COLUMNS[currentScreen] || COLUMNS.all;
    headerRow.innerHTML = cols.map(c =>
      `<th data-col="${c.key}">${c.label}</th>`
    ).join("");

    // Re-bind click sorting
    headerRow.querySelectorAll("th[data-col]").forEach(th => {
      th.addEventListener("click", () => {
        const col = th.dataset.col;
        if (sortCol === col) {
          sortOrder = sortOrder === "asc" ? "desc" : "asc";
        } else {
          sortCol = col;
          sortOrder = col === "종목코드" || col === "종목명" ? "asc" : "desc";
        }
        headerRow.querySelectorAll(".sort-arrow").forEach(a => a.remove());
        const arrow = document.createElement("span");
        arrow.className = "sort-arrow";
        arrow.textContent = sortOrder === "asc" ? "\u25B2" : "\u25BC";
        th.appendChild(arrow);
        currentPage = 1;
        loadStocks();
      });
    });
  }

  // ── Load stocks ──
  async function loadStocks() {
    const market = document.getElementById("f-market").value;
    const q = document.getElementById("f-search").value.trim();

    const params = new URLSearchParams({
      screen: currentScreen,
      page: currentPage,
      size: pageSize,
      sort: sortCol,
      order: sortOrder,
    });
    if (market) params.set("market", market);
    if (q) params.set("q", q);

    try {
      const res = await fetch(`/api/stocks?${params}`);
      const data = await res.json();
      renderTable(data.items);
      renderPagination(data.total, data.page, data.size);
    } catch (e) {
      console.error("Load error", e);
      tbody.innerHTML = `<tr><td colspan="20" class="text-center text-danger">Failed to load data</td></tr>`;
    }
  }

  function renderTable(items) {
    const cols = COLUMNS[currentScreen] || COLUMNS.all;
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="${cols.length}" class="text-center text-muted">
        No data. Run the pipeline first.</td></tr>`;
      return;
    }
    tbody.innerHTML = items.map(s => {
      const cells = cols.map(c => {
        const v = s[c.key];
        let cls = "";
        if (c.key === "괴리율(%)" || c.key === "이익률_변동폭") cls = valClass(v);
        if (c.key === "시장구분") {
          return `<td><span class="badge ${v === "KOSPI" ? "bg-primary" : "bg-danger"}">${v || "-"}</span></td>`;
        }
        return `<td class="${cls}">${fmt(v, c.fmt)}</td>`;
      }).join("");
      return `<tr data-code="${s["종목코드"]}">${cells}</tr>`;
    }).join("");
  }

  function renderPagination(total, page, size) {
    const totalPages = Math.ceil(total / size) || 1;
    pageInfo.textContent = `Page ${page} / ${totalPages}  (${total.toLocaleString()} stocks)`;
    btnPrev.disabled = page <= 1;
    btnNext.disabled = page >= totalPages;
  }

  // ── Tab switching ──
  document.getElementById("screen-tabs").addEventListener("click", e => {
    const link = e.target.closest("[data-screen]");
    if (!link) return;
    e.preventDefault();
    document.querySelectorAll("#screen-tabs .nav-link").forEach(l => l.classList.remove("active"));
    link.classList.add("active");
    currentScreen = link.dataset.screen;
    currentPage = 1;
    sortCol = "종합점수";
    sortOrder = "desc";
    buildHeader();
    loadStocks();
  });

  // ── Filters ──
  document.getElementById("filter-form").addEventListener("submit", e => {
    e.preventDefault(); currentPage = 1; loadStocks();
  });
  document.getElementById("btn-clear").addEventListener("click", () => {
    document.getElementById("f-market").value = "";
    document.getElementById("f-search").value = "";
    currentPage = 1; loadStocks();
  });

  // ── Pagination ──
  btnPrev.addEventListener("click", () => { if (currentPage > 1) { currentPage--; loadStocks(); } });
  btnNext.addEventListener("click", () => { currentPage++; loadStocks(); });

  // ── Refresh ──
  document.getElementById("btn-refresh").addEventListener("click", () => {
    loadSummary(); loadTabCounts(); loadStocks();
  });

  // ── Detail modal ──
  tbody.addEventListener("click", async e => {
    const row = e.target.closest("tr[data-code]");
    if (!row) return;
    const code = row.dataset.code;
    try {
      const res = await fetch(`/api/stocks/${code}`);
      const d = await res.json();

      document.getElementById("detail-title").textContent =
        `${d["종목명"] || ""} (${d["종목코드"] || ""}) - ${d["시장구분"] || ""}`;

      const metrics = [
        ["Price", d["종가"], "int"],
        ["Mkt Cap", d["시가총액"] ? Math.round(d["시가총액"] / 1e8) + " 억" : null, "str"],
        ["PER", d["PER"], "f2"], ["PBR", d["PBR"], "f2"], ["PSR", d["PSR"], "f2"],
        ["PEG", d["PEG"], "f2"],
        ["ROE%", d["ROE(%)"], "f2"], ["EPS", d["EPS"], "int"], ["BPS", d["BPS"], "int"],
        ["OPM%", d["영업이익률(%)"], "f2"], ["Debt%", d["부채비율(%)"], "f1"],
        ["Div%", d["배당수익률(%)"], "f2"], ["FCF%", d["FCF수익률(%)"], "f2"],
        ["Earn Yield%", d["이익수익률(%)"], "f2"],
        ["Rev CAGR", d["매출_CAGR"], "f1"], ["OP CAGR", d["영업이익_CAGR"], "f1"],
        ["NI CAGR", d["순이익_CAGR"], "f1"],
        ["Rev Streak", d["매출_연속성장"], "int"], ["OP Streak", d["영업이익_연속성장"], "int"],
        ["S-RIM", d["적정주가_SRIM"], "int"], ["Gap%", d["괴리율(%)"], "f2"],
        ["Score", d["종합점수"], "f1"],
      ];

      const pillsHtml = metrics.map(([lbl, val, type]) => {
        const display = val != null ? (type === "str" ? val : fmt(val, type)) : "-";
        return `<div class="metric-pill"><span class="lbl">${lbl}</span><br><span class="val">${display}</span></div>`;
      }).join("");

      document.getElementById("detail-body").innerHTML =
        `<div class="metric-grid">${pillsHtml}</div>`;

      new bootstrap.Modal(document.getElementById("detail-modal")).show();
    } catch (err) { console.error("Detail error", err); }
  });

  // ── Pipeline trigger ──
  document.getElementById("btn-trigger").addEventListener("click", async () => {
    if (!confirm("Run the data pipeline now?")) return;
    try {
      const res = await fetch("/api/batch/trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      showToast(data.message || "Pipeline triggered");
    } catch (err) { showToast("Failed to trigger pipeline"); }
  });

  // ── Init ──
  buildHeader();
  loadSummary();
  loadTabCounts();
  loadStocks();
})();
