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
  let advFilterOpen = false;
  const columnFilters = {}; // { column: { min, max } }

  const tbody = document.getElementById("stock-tbody");
  const headerRow = document.getElementById("table-header");
  const pageInfo = document.getElementById("page-info");
  const btnPrev = document.getElementById("btn-prev");
  const btnNext = document.getElementById("btn-next");

  // ── Tooltip descriptions (Korean with definitions & formulas) ──
  const TOOLTIPS = {
    종목코드: "종목코드: 한국 주식의 고유 식별자 (6자리 숫자)",
    종목명: "종목명: 상장사의 회사명",
    시장구분: "시장구분: KOSPI(유가증권시장) 또는 KOSDAQ(코스닥)",
    종가: "종가: 해당 날짜의 최종 주가",
    PER: "PER (주가수익비율)\n정의: 주가를 1주당 순이익으로 나눈 값\n계산: PER = 주가 / EPS\n낮을수록 저평가된 것으로 평가",
    PBR: "PBR (주가순자산비율)\n정의: 주가를 1주당 순자산으로 나눈 값\n계산: PBR = 주가 / BPS\n낮을수록 자산 대비 저평가된 것으로 평가",
    "ROE(%)": "ROE (자기자본수익률)\n정의: 자기자본을 기준으로 벌어들인 순이익의 비율\n계산: ROE(%) = (순이익 / 자기자본) × 100\n높을수록 자본 효율성이 좋음",
    "영업이익률(%)": "OPM (영업이익률)\n정의: 매출액 대비 영업이익의 비율\n계산: OPM(%) = (영업이익 / 매출액) × 100\n높을수록 핵심 사업의 수익성이 좋음",
    "배당수익률(%)": "배당수익률\n정의: 주가에 대한 배당금의 비율\n계산: 배당수익률(%) = (배당금 / 주가) × 100\n정기적인 현금 수익을 기대할 수 있는 지표",
    "매출_CAGR": "Rev CAGR (매출 연평균 성장률)\n정의: 5년간의 매출액 복합 연평균 성장률\n계산: CAGR = (최종값 / 초기값)^(1/년수) - 1\n높을수록 매출 성장이 우수함",
    "영업이익_CAGR": "Op CAGR (영업이익 연평균 성장률)\n정의: 5년간의 영업이익 복합 연평균 성장률\n높을수록 이익 성장이 우수함",
    "순이익_CAGR": "NI CAGR (순이익 연평균 성장률)\n정의: 5년간의 순이익 복합 연평균 성장률\n높을수록 순이익 성장이 우수함",
    "적정주가_SRIM": "S-RIM (적정주가)\n정의: 단순화된 RIM 모델로 계산한 적정 주가\n이론적 공정가치로, 현재 주가와의 괴리율을 계산하는 기준",
    "괴리율(%)": "Gap% (괴리율)\n정의: 현재 주가와 적정주가의 차이 비율\n계산: Gap% = (현재주가 - 적정주가) / 적정주가 × 100\n음수일 때 저평가, 양수일 때 고평가 상태",
    "종합점수": "종합점수: 여러 재무 지표를 통합한 종합 점수 (0-1000점)\n점수가 높을수록 해당 전략에 적합한 종목",
    "매출_연속성장": "매출 연속성장: 최근 몇 년간 연속으로 매출이 성장한 연도 수\n높을수록 안정적인 성장세를 보임",
    "이익률_개선": "이익률_개선: 전년도 대비 올해 영업이익률이 개선되었는지 여부 (1=개선, 0=악화)",
    "이익률_급개선": "이익률_급개선: 전년도 대비 올해 영업이익률이 급격하게 개선되었는지 여부",
    "PEG": "PEG (PEG 비율)\n정의: PER을 예상 성장률로 나눈 값\n계산: PEG = PER / 성장률(%)\n1 이하이면 저평가된 성장주로 평가",
    "FCF수익률(%)": "FCF% (자유현금흐름 수익률)\n정의: 매출액 대비 자유현금흐름의 비율\n현금 창출 능력을 보여주는 지표\n높을수록 현금 창출력이 좋음",
    "부채비율(%)": "부채비율\n정의: 총부채를 자기자본으로 나눈 값\n계산: 부채비율(%) = (총부채 / 자기자본) × 100\n낮을수록 재정 건전성이 좋음",
    "이익품질_양호": "이익품질_양호: 영업현금흐름이 순이익보다 많은지 여부\n현금 기반 이익인지 확인하는 지표 (1=양호, 0=저조)",
    "흑자전환": "흑자전환: 적자에서 흑자로 전환되었는지 여부 (1=전환, 0=미전환)\n실적 반등 종목을 찾는 데 중요한 지표",
    "이익률_변동폭": "이익률_변동폭: 영업이익률의 최근 변화 폭\n변동폭이 작을수록 이익이 안정적",
  };

  const MARKET_TOOLTIPS = {
    "PER(med)": "중앙값 PER\n정의: 시장의 평균적인 주가수익비율\n낮을수록 시장이 저평가 상태",
    "PBR": "평균 PBR\n정의: 시장의 평균적인 주가순자산비율\n낮을수록 시장이 저평가 상태",
    "ROE": "평균 ROE\n정의: 시장 전체의 평균 자기자본수익률\n높을수록 시장 기업들의 자본 효율성이 좋음",
  };

  // ── Strategy descriptions ──
  const STRATEGY_DESCRIPTIONS = {
    all: {
      title: "📊 모든 상장 종목",
      criteria: "시가총액 기준으로 전체 상장 종목을 조회합니다.",
      formula: "특정 필터링 기준 없음"
    },
    screened: {
      title: "🏆 우량주 (Quality) 전략",
      criteria: "ROE ≥ 5% · PER 1-50 · PBR 0.1-10 · 매출 연속성장 ≥ 2년 · 순이익 연속성장 ≥ 1년",
      formula: "점수 = (PER × 1.0 + PBR × 1.0 + ROE × 1.0 + 매출CAGR × 1.0 + 배당수익률 × 1.0 + 괴리율 × 1.0)의 percentile 가중합"
    },
    momentum: {
      title: "🚀 모멘텀/고성장 (Momentum) 전략",
      criteria: "매출 CAGR ≥ 15% OR 영업이익 CAGR ≥ 15% · 이익률 개선 · ROE ≥ 5%",
      formula: "점수 = (매출CAGR × 2.0 + 영업이익CAGR × 2.5 + ROE × 1.5 + 영업이익률 × 1.0 + 이익률개선 × 1.0)의 percentile 가중합"
    },
    garp: {
      title: "💎 GARP (성장 대비 합리적 가격) 전략",
      criteria: "PEG < 1.5 · 매출 CAGR ≥ 10% · ROE ≥ 12% · PER 5-30",
      formula: "점수 = (저PEG × 3.0 + 매출성장 × 2.0 + 이익성장 × 1.5 + ROE × 2.0 + 저PER × 1.0 + 이익률개선 × 0.5 + 저평가 × 1.0)의 percentile 가중합"
    },
    cashcow: {
      title: "💰 캐시카우 (배당/현금창출) 전략",
      criteria: "ROE ≥ 10% · 영업이익률 ≥ 10% · 부채비율 < 100% · 매출 연속성장 ≥ 1년",
      formula: "점수 = (ROE × 2.5 + 영업이익률 × 2.5 + 저부채 × 2.0 + 안정성장 × 1.0 + 저PER × 1.0 + 배당수익률 × 0.5)의 percentile 가중합"
    },
    turnaround: {
      title: "📈 턴어라운드 (실적 반등) 전략",
      criteria: "적자→흑자 전환 OR 영업이익률 +5%p 급개선 · 현재 순이익 > 0 · 시가총액 ≥ 300억",
      formula: "점수 = (이익률변동폭 × 2.5 + 매출성장 × 1.5 + ROE × 1.5 + 흑전보너스 × 1.5 + 저PER × 1.0 + 급개선보너스 × 1.0)의 percentile 가중합"
    }
  };

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

  // ── Filterable columns ──
  const FILTERABLE_COLUMNS = [
    "PER", "PBR", "ROE(%)", "영업이익률(%)", "배당수익률(%)",
    "매출_CAGR", "영업이익_CAGR", "순이익_CAGR", "적정주가_SRIM",
    "괴리율(%)", "종합점수", "FCF수익률(%)", "부채비율(%)",
    "매출_연속성장", "이익률_변동폭"
  ];

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
              <span data-bs-toggle="tooltip" data-bs-placement="top" title="${MARKET_TOOLTIPS["PER(med)"]}">
                PER(med) ${m.avg_per != null ? Number(m.avg_per).toFixed(1) : "-"}
              </span>
              &middot;
              <span data-bs-toggle="tooltip" data-bs-placement="top" title="${MARKET_TOOLTIPS["PBR"]}">
                PBR ${m.avg_pbr != null ? Number(m.avg_pbr).toFixed(2) : "-"}
              </span>
              &middot;
              <span data-bs-toggle="tooltip" data-bs-placement="top" title="${MARKET_TOOLTIPS["ROE"]}">
                ROE ${m.avg_roe != null ? Number(m.avg_roe).toFixed(1) + "%" : "-"}
              </span>
            </div>
          </div>
        </div>`).join("");
      initTooltips();
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
    headerRow.innerHTML = cols.map(c => {
      const tooltip = TOOLTIPS[c.key] || "";
      const isFilterable = FILTERABLE_COLUMNS.includes(c.key);
      const filterIcon = isFilterable ? `<button class="btn btn-sm btn-link p-0 ms-1 filter-icon" data-filter-col="${c.key}" style="font-size: 0.75rem; line-height: 1; color: #6c757d;" title="Filter">▼</button>` : "";
      return `<th data-col="${c.key}" ${tooltip ? `data-bs-toggle="tooltip" data-bs-placement="bottom" title="${tooltip}"` : ""} style="position: relative;">${c.label}${filterIcon}</th>`;
    }).join("");

    // Re-bind click sorting (3-way cycle: asc → desc → none → asc)
    headerRow.querySelectorAll("th[data-col]").forEach(th => {
      th.addEventListener("click", (e) => {
        // Don't trigger sort if clicking filter icon
        if (e.target.classList.contains("filter-icon")) return;

        const col = th.dataset.col;
        if (sortCol === col) {
          // Cycle: asc → desc → none → asc
          if (sortOrder === "asc") {
            sortOrder = "desc";
          } else if (sortOrder === "desc") {
            sortOrder = "none";
          } else {
            sortOrder = "asc";
          }
        } else {
          sortCol = col;
          sortOrder = "desc"; // Default to desc for new column
        }

        // Update arrow
        headerRow.querySelectorAll(".sort-arrow").forEach(a => a.remove());
        if (sortOrder !== "none") {
          const arrow = document.createElement("span");
          arrow.className = "sort-arrow";
          arrow.textContent = sortOrder === "asc" ? "\u25B2" : "\u25BC";
          th.appendChild(arrow);
        }
        currentPage = 1;
        loadStocks();
      });
    });

    // Bind filter icon clicks
    headerRow.querySelectorAll(".filter-icon").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const col = btn.dataset.filterCol;
        showColumnFilterPopup(btn, col);
      });
    });

    initTooltips();
  }

  // ── Initialize tooltips ──
  function initTooltips() {
    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
      new bootstrap.Tooltip(el, { delay: { show: 200, hide: 100 } });
    });
  }

  // ── Show column filter popup ──
  function showColumnFilterPopup(btn, colName) {
    // Check if popup for this column already exists
    const existingPopup = document.getElementById(`filter-popup-${colName}`);
    if (existingPopup) {
      existingPopup.remove();
      return;
    }

    const cols = COLUMNS[currentScreen] || COLUMNS.all;
    const col = cols.find(c => c.key === colName);
    if (!col) return;

    const currentMin = columnFilters[colName]?.min ?? "";
    const currentMax = columnFilters[colName]?.max ?? "";

    const popup = document.createElement("div");
    popup.id = `filter-popup-${colName}`;
    popup.className = "filter-popup";

    // Get button position
    const rect = btn.getBoundingClientRect();
    const scrollY = window.scrollY;
    const scrollX = window.scrollX;

    popup.style.cssText = `
      position: fixed;
      top: ${rect.bottom + scrollY + 4}px;
      left: ${rect.left + scrollX - 80}px;
      background: white;
      border: 1px solid #ddd;
      border-radius: 4px;
      padding: 10px;
      z-index: 10000;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
      min-width: 160px;
      font-size: 0.85rem;
    `;

    popup.innerHTML = `
      <div style="font-size: 0.8rem; margin-bottom: 8px; font-weight: 600; color: #333;">${col.label}</div>
      <div style="display: grid; gap: 5px;">
        <input type="number" placeholder="Min" step="0.01" class="form-control form-control-sm filter-min-input" value="${currentMin}" style="font-size: 0.85rem;">
        <input type="number" placeholder="Max" step="0.01" class="form-control form-control-sm filter-max-input" value="${currentMax}" style="font-size: 0.85rem;">
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px;">
          <button class="btn btn-sm btn-primary filter-apply-btn" style="font-size: 0.8rem;">Apply</button>
          <button class="btn btn-sm btn-outline-secondary filter-clear-btn" style="font-size: 0.8rem;">Clear</button>
        </div>
      </div>
    `;

    document.body.appendChild(popup);

    // Auto focus min input
    popup.querySelector(".filter-min-input").focus();

    // Apply button
    popup.querySelector(".filter-apply-btn").addEventListener("click", () => {
      const min = popup.querySelector(".filter-min-input").value;
      const max = popup.querySelector(".filter-max-input").value;

      if (!columnFilters[colName]) columnFilters[colName] = {};
      columnFilters[colName].min = min ? parseFloat(min) : null;
      columnFilters[colName].max = max ? parseFloat(max) : null;

      currentPage = 1;
      loadStocks();
      popup.remove();
    });

    // Clear button
    popup.querySelector(".filter-clear-btn").addEventListener("click", () => {
      delete columnFilters[colName];
      currentPage = 1;
      loadStocks();
      popup.remove();
    });

    // Close on outside click
    const closePopup = (e) => {
      if (!popup.contains(e.target) && e.target !== btn && !btn.contains(e.target)) {
        popup.remove();
        document.removeEventListener("click", closePopup);
      }
    };
    document.addEventListener("click", closePopup);

    // Enter key to apply
    popup.querySelector(".filter-max-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter") popup.querySelector(".filter-apply-btn").click();
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
      order: sortOrder === "none" ? "desc" : sortOrder,
    });
    if (market) params.set("market", market);
    if (q) params.set("q", q);

    // Add column filters
    Object.keys(columnFilters).forEach(col => {
      const filter = columnFilters[col];
      if (filter.min !== null && filter.min !== undefined) {
        params.set(`min_${col}`, filter.min);
      }
      if (filter.max !== null && filter.max !== undefined) {
        params.set(`max_${col}`, filter.max);
      }
    });

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

  // ── Update strategy description ──
  function updateStrategyDescription(screenKey) {
    const desc = STRATEGY_DESCRIPTIONS[screenKey] || {};
    const html = desc.title ? `
      <div><strong>${desc.title}</strong></div>
      <div style="margin-top: 0.5rem; color: #666;">
        <div><span style="color: #555; font-weight: 500;">기준:</span> ${desc.criteria}</div>
        <div style="margin-top: 0.3rem;"><span style="color: #555; font-weight: 500;">점수:</span> ${desc.formula}</div>
      </div>
    ` : "";
    document.getElementById("strategy-desc").innerHTML = html;
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
    updateStrategyDescription(currentScreen);
    buildHeader();
    loadStocks();
  });

  // ── Build advanced filter panel ──
  function buildAdvFilterPanel() {
    const cols = COLUMNS[currentScreen] || COLUMNS.all;
    const filterCols = cols.filter(c => FILTERABLE_COLUMNS.includes(c.key));

    const panelHtml = filterCols.map(c => `
      <div class="col-auto">
        <div class="input-group input-group-sm">
          <span class="input-group-text" style="font-size: .75rem; min-width: 60px;">${c.label}</span>
          <input type="number" class="form-control form-control-sm col-filter"
                 data-col="${c.key}" placeholder="Min" step="0.01" style="width: 50px;">
          <input type="number" class="form-control form-control-sm col-filter"
                 data-col="${c.key}" placeholder="Max" step="0.01" style="width: 50px;">
        </div>
      </div>
    `).join("");

    const panel = document.getElementById("column-filters");
    panel.innerHTML = panelHtml + `
      <div class="col-auto">
        <button type="button" id="btn-apply-adv" class="btn btn-success btn-sm">Apply Filters</button>
        <button type="button" id="btn-reset-adv" class="btn btn-outline-secondary btn-sm">Reset</button>
      </div>
    `;

    // Bind events
    document.querySelectorAll(".col-filter").forEach(input => {
      input.addEventListener("change", () => {
        const col = input.dataset.col;
        if (!columnFilters[col]) columnFilters[col] = {};
        if (input.placeholder === "Min") {
          columnFilters[col].min = input.value ? parseFloat(input.value) : null;
        } else {
          columnFilters[col].max = input.value ? parseFloat(input.value) : null;
        }
      });
    });

    document.getElementById("btn-apply-adv").addEventListener("click", () => {
      currentPage = 1;
      loadStocks();
    });

    document.getElementById("btn-reset-adv").addEventListener("click", () => {
      Object.keys(columnFilters).forEach(k => delete columnFilters[k]);
      document.querySelectorAll(".col-filter").forEach(inp => inp.value = "");
      currentPage = 1;
      loadStocks();
    });
  }

  // ── Toggle advanced filter panel ──
  document.getElementById("btn-adv-filter").addEventListener("click", () => {
    advFilterOpen = !advFilterOpen;
    const panel = document.getElementById("adv-filter-panel");
    panel.style.display = advFilterOpen ? "block" : "none";
    document.getElementById("btn-adv-filter").textContent = advFilterOpen ? "Advanced ▲" : "Advanced ▼";
    if (advFilterOpen) buildAdvFilterPanel();
  });

  // ── Filters ──
  document.getElementById("filter-form").addEventListener("submit", e => {
    e.preventDefault(); currentPage = 1; loadStocks();
  });
  document.getElementById("btn-clear").addEventListener("click", () => {
    document.getElementById("f-market").value = "";
    document.getElementById("f-search").value = "";
    Object.keys(columnFilters).forEach(k => delete columnFilters[k]);
    currentPage = 1; loadStocks();
  });

  // ── Pagination ──
  btnPrev.addEventListener("click", () => { if (currentPage > 1) { currentPage--; loadStocks(); } });
  btnNext.addEventListener("click", () => { currentPage++; loadStocks(); });

  // ── Refresh ──
  document.getElementById("btn-refresh").addEventListener("click", () => {
    loadSummary(); loadTabCounts(); loadStocks();
  });

  // ── Tooltip map for detail modal ──
  const DETAIL_TOOLTIPS = {
    "Price": "종가: 해당 날짜의 최종 주가",
    "Mkt Cap": "시가총액: 주식 총 개수 × 현재 주가",
    "PER": "PER (주가수익비율): 주가 / EPS\n낮을수록 저평가",
    "PBR": "PBR (주가순자산비율): 주가 / BPS\n낮을수록 저평가",
    "PSR": "PSR (주가매출비율): 시가총액 / 매출액\n낮을수록 저평가",
    "PEG": "PEG: PER / 성장률\n1 이하이면 저평가된 성장주",
    "ROE%": "ROE (자기자본수익률): (순이익 / 자기자본) × 100\n높을수록 자본 효율성 좋음",
    "EPS": "EPS (주당순이익): 순이익 / 발행주식수",
    "BPS": "BPS (주당순자산): 자기자본 / 발행주식수",
    "OPM%": "OPM (영업이익률): (영업이익 / 매출액) × 100\n높을수록 수익성 좋음",
    "Debt%": "부채비율: (총부채 / 자기자본) × 100\n낮을수록 재정 건전성 좋음",
    "Div%": "배당수익률: (배당금 / 주가) × 100\n정기적인 현금 수익",
    "FCF%": "FCF% (자유현금흐름 수익률): (자유현금흐름 / 매출액) × 100\n높을수록 현금 창출력 좋음",
    "Earn Yield%": "이익수익률: (EPS / 주가) × 100\nPER의 역수",
    "Rev CAGR": "Rev CAGR (매출 연평균 성장률): 5년간의 매출 복합 연평균 성장률",
    "OP CAGR": "Op CAGR (영업이익 연평균 성장률): 5년간의 영업이익 복합 연평균 성장률",
    "NI CAGR": "NI CAGR (순이익 연평균 성장률): 5년간의 순이익 복합 연평균 성장률",
    "Rev Streak": "매출 연속성장: 최근 몇 년간 연속으로 매출이 성장한 연도 수",
    "OP Streak": "영업이익 연속성장: 최근 몇 년간 연속으로 영업이익이 성장한 연도 수",
    "S-RIM": "S-RIM (적정주가): 단순화된 RIM 모델로 계산한 공정가치",
    "Gap%": "Gap% (괴리율): (현재주가 - 적정주가) / 적정주가 × 100\n음수=저평가, 양수=고평가",
    "Score": "종합점수: 여러 재무 지표를 통합한 종합 점수 (0-1000점)",
  };

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
        const tooltip = DETAIL_TOOLTIPS[lbl] || "";
        const tooltipAttr = tooltip ? `data-bs-toggle="tooltip" data-bs-placement="top" title="${tooltip.replace(/"/g, '&quot;')}"` : "";
        return `<div class="metric-pill" ${tooltipAttr}><span class="lbl">${lbl}</span><br><span class="val">${display}</span></div>`;
      }).join("");

      document.getElementById("detail-body").innerHTML =
        `<div class="metric-grid">${pillsHtml}</div>`;

      // Initialize tooltips for modal
      setTimeout(() => {
        document.querySelectorAll('#detail-body [data-bs-toggle="tooltip"]').forEach(el => {
          new bootstrap.Tooltip(el, { delay: { show: 200, hide: 100 } });
        });
      }, 100);

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
  updateStrategyDescription(currentScreen);
  initTooltips();
})();
