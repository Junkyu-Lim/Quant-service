/**
 * Quant Dashboard – client-side logic.
 *
 * Features:
 *   - Server-side paginated stock table
 *   - Column-header click sorting
 *   - Market / sector / text filtering
 *   - Stock detail modal with price chart (Chart.js)
 *   - Pipeline trigger + toast notification
 */

(function () {
  "use strict";

  const API = "";  // same origin

  // ---- State ----
  let currentPage = 1;
  const pageSize = 50;
  let sortCol = "code";
  let sortOrder = "asc";

  // ---- DOM refs ----
  const tbody       = document.getElementById("stock-tbody");
  const pageInfo    = document.getElementById("page-info");
  const btnPrev     = document.getElementById("btn-prev");
  const btnNext     = document.getElementById("btn-next");
  const snapshotEl  = document.getElementById("snapshot-date");

  // ---- Helpers ----
  function fmt(v, decimals) {
    if (v === null || v === undefined) return "-";
    return Number(v).toLocaleString("ko-KR", {
      minimumFractionDigits: decimals || 0,
      maximumFractionDigits: decimals || 0,
    });
  }

  function changeCls(v) {
    if (v === null || v === undefined) return "";
    return v > 0 ? "text-pos" : v < 0 ? "text-neg" : "";
  }

  // ---- Market summary ----
  async function loadSummary() {
    try {
      const res = await fetch(`${API}/api/markets/summary`);
      const data = await res.json();
      const container = document.getElementById("market-summary");
      container.innerHTML = data
        .map(
          (m) => `
        <div class="col-md-3 col-6">
          <div class="card summary-card ${m.market === "KOSDAQ" ? "kosdaq" : ""} p-3">
            <div class="card-title">${m.market}</div>
            <div class="metric-value">${fmt(m.stock_count)} stocks</div>
            <div class="small text-muted">Avg PER ${fmt(m.avg_per, 2)} &middot; PBR ${fmt(m.avg_pbr, 2)}</div>
          </div>
        </div>`
        )
        .join("");
    } catch (e) {
      console.error("Summary load error", e);
    }
  }

  // ---- Stock table ----
  async function loadStocks() {
    const market = document.getElementById("f-market").value;
    const sector = document.getElementById("f-sector").value.trim();
    const q = document.getElementById("f-search").value.trim();

    const params = new URLSearchParams({
      page: currentPage,
      size: pageSize,
      sort: sortCol,
      order: sortOrder,
    });
    if (market) params.set("market", market);
    if (sector) params.set("sector", sector);
    if (q) params.set("q", q);

    try {
      const res = await fetch(`${API}/api/stocks?${params}`);
      const data = await res.json();

      if (data.snapshot_date) {
        snapshotEl.textContent = `Data: ${data.snapshot_date}`;
      }

      renderTable(data.items);
      renderPagination(data.total, data.page, data.size);
    } catch (e) {
      console.error("Stock load error", e);
      tbody.innerHTML = `<tr><td colspan="13" class="text-center text-danger">Failed to load data</td></tr>`;
    }
  }

  function renderTable(items) {
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="13" class="text-center text-muted">No data available. Run the pipeline to fetch stock data.</td></tr>`;
      return;
    }

    tbody.innerHTML = items
      .map(
        (s) => `
      <tr data-code="${s.code}">
        <td>${s.code}</td>
        <td>${s.name}</td>
        <td><span class="badge ${s.market === "KOSPI" ? "bg-primary" : "bg-danger"}">${s.market}</span></td>
        <td>${s.sector || "-"}</td>
        <td class="${changeCls(s.change_pct)}">${s.change_pct !== null && s.change_pct !== undefined ? (s.change_pct > 0 ? "+" : "") + fmt(s.change_pct, 2) + "%" : "-"}</td>
        <td>${fmt(s.per, 2)}</td>
        <td>${fmt(s.pbr, 2)}</td>
        <td>${fmt(s.eps, 0)}</td>
        <td>${fmt(s.roe, 2)}</td>
        <td>${fmt(s.dividend_yield, 2)}</td>
        <td>${fmt(s.rsi14, 1)}</td>
        <td>${fmt(s.ma5, 0)}</td>
        <td>${fmt(s.ma20, 0)}</td>
      </tr>`
      )
      .join("");
  }

  function renderPagination(total, page, size) {
    const totalPages = Math.ceil(total / size) || 1;
    pageInfo.textContent = `Page ${page} / ${totalPages}  (${total} stocks)`;
    btnPrev.disabled = page <= 1;
    btnNext.disabled = page >= totalPages;
  }

  // ---- Sorting ----
  document.querySelectorAll("#stock-table th[data-col]").forEach((th) => {
    th.addEventListener("click", () => {
      const col = th.dataset.col;
      if (sortCol === col) {
        sortOrder = sortOrder === "asc" ? "desc" : "asc";
      } else {
        sortCol = col;
        sortOrder = "asc";
      }
      // Update sort arrows
      document.querySelectorAll("#stock-table th .sort-arrow").forEach((a) => a.remove());
      const arrow = document.createElement("span");
      arrow.className = "sort-arrow";
      arrow.textContent = sortOrder === "asc" ? "\u25B2" : "\u25BC";
      th.appendChild(arrow);

      currentPage = 1;
      loadStocks();
    });
  });

  // ---- Filtering ----
  document.getElementById("filter-form").addEventListener("submit", (e) => {
    e.preventDefault();
    currentPage = 1;
    loadStocks();
  });
  document.getElementById("btn-clear").addEventListener("click", () => {
    document.getElementById("f-market").value = "";
    document.getElementById("f-sector").value = "";
    document.getElementById("f-search").value = "";
    currentPage = 1;
    loadStocks();
  });

  // ---- Pagination ----
  btnPrev.addEventListener("click", () => {
    if (currentPage > 1) { currentPage--; loadStocks(); }
  });
  btnNext.addEventListener("click", () => {
    currentPage++;
    loadStocks();
  });

  // ---- Refresh ----
  document.getElementById("btn-refresh").addEventListener("click", () => {
    loadSummary();
    loadStocks();
  });

  // ---- Stock detail modal ----
  let priceChart = null;

  tbody.addEventListener("click", async (e) => {
    const row = e.target.closest("tr[data-code]");
    if (!row) return;
    const code = row.dataset.code;

    try {
      const res = await fetch(`${API}/api/stocks/${code}`);
      const data = await res.json();

      document.getElementById("detail-title").textContent = `${data.name} (${data.code}) – ${data.market}`;

      // Metrics pills
      const m = data.metrics || {};
      const metricsHtml = [
        ["PER", m.per, 2],
        ["PBR", m.pbr, 2],
        ["EPS", m.eps, 0],
        ["BPS", m.bps, 0],
        ["ROE %", m.roe, 2],
        ["Div Yield %", m.dividend_yield, 2],
        ["RSI(14)", m.rsi14, 1],
        ["Change %", m.change_pct, 2],
        ["MA5", m.ma5, 0],
        ["MA20", m.ma20, 0],
        ["MA60", m.ma60, 0],
      ]
        .map(
          ([label, val, dec]) =>
            `<div class="metric-pill"><span class="label">${label}</span><br><span class="value">${fmt(val, dec)}</span></div>`
        )
        .join("");
      document.getElementById("detail-metrics").innerHTML = metricsHtml;

      // Price chart
      const prices = data.prices || [];
      const labels = prices.map((p) => p.trade_date);
      const closes = prices.map((p) => p.close);
      const volumes = prices.map((p) => p.volume);

      if (priceChart) priceChart.destroy();

      const ctx = document.getElementById("price-chart").getContext("2d");
      priceChart = new Chart(ctx, {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "Close",
              data: closes,
              borderColor: "#0d6efd",
              backgroundColor: "rgba(13,110,253,0.1)",
              fill: true,
              tension: 0.3,
              yAxisID: "y",
              pointRadius: 1,
            },
            {
              label: "Volume",
              data: volumes,
              type: "bar",
              backgroundColor: "rgba(108,117,125,0.25)",
              yAxisID: "y1",
            },
          ],
        },
        options: {
          responsive: true,
          interaction: { mode: "index", intersect: false },
          scales: {
            y: { position: "left", title: { display: true, text: "Price (KRW)" } },
            y1: {
              position: "right",
              title: { display: true, text: "Volume" },
              grid: { drawOnChartArea: false },
            },
          },
        },
      });

      new bootstrap.Modal(document.getElementById("detail-modal")).show();
    } catch (err) {
      console.error("Detail load error", err);
    }
  });

  // ---- Pipeline trigger ----
  document.getElementById("btn-trigger").addEventListener("click", async () => {
    if (!confirm("Run the data pipeline now?")) return;
    try {
      const res = await fetch(`${API}/api/batch/trigger`, { method: "POST" });
      const data = await res.json();
      showToast(data.message || "Pipeline triggered");
    } catch (err) {
      showToast("Failed to trigger pipeline");
    }
  });

  function showToast(msg) {
    document.getElementById("toast-body").textContent = msg;
    const t = new bootstrap.Toast(document.getElementById("toast-msg"));
    t.show();
  }

  // ---- Init ----
  loadSummary();
  loadStocks();
})();
