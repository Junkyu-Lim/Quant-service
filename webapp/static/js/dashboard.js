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

  // ── Watchlist (localStorage) ──
  const WATCHLIST_KEY = "quant_watchlist";

  function getWatchlist() {
    try { return new Set(JSON.parse(localStorage.getItem(WATCHLIST_KEY) || "[]")); }
    catch { return new Set(); }
  }
  function saveWatchlist(set) {
    localStorage.setItem(WATCHLIST_KEY, JSON.stringify([...set]));
  }
  function updateWatchlistCount() {
    const el = document.getElementById("cnt-watchlist");
    if (el) el.textContent = getWatchlist().size;
  }
  function updateAllStarButtons() {
    const wl = getWatchlist();
    document.querySelectorAll(".watch-btn").forEach(btn => {
      const watched = wl.has(btn.dataset.code);
      btn.textContent = watched ? "★" : "☆";
      btn.classList.toggle("watched", watched);
    });
    // 모달 내 관심 버튼도 업데이트
    const btnWD = document.getElementById("btn-watch-detail");
    if (btnWD && btnWD.dataset.code) {
      const watched = wl.has(btnWD.dataset.code);
      btnWD.textContent = watched ? "★ 관심 해제" : "☆ 관심 종목";
      btnWD.classList.toggle("btn-warning", watched);
      btnWD.classList.toggle("btn-outline-warning", !watched);
    }
  }
  function toggleWatch(code) {
    const wl = getWatchlist();
    if (wl.has(code)) wl.delete(code); else wl.add(code);
    saveWatchlist(wl);
    updateAllStarButtons();
    updateWatchlistCount();
    if (currentScreen === "watchlist") loadStocks();
  }

  // ── Filter Presets (localStorage) ──
  const PRESETS_KEY = "quant_filter_presets";

  function getPresets() {
    try { return JSON.parse(localStorage.getItem(PRESETS_KEY) || "[]"); }
    catch { return []; }
  }
  function savePresets(presets) {
    localStorage.setItem(PRESETS_KEY, JSON.stringify(presets));
  }

  function getCurrentFilterState() {
    return {
      screen: currentScreen,
      market: document.getElementById("f-market").value,
      search: document.getElementById("f-search").value.trim(),
      columnFilters: JSON.parse(JSON.stringify(columnFilters)),
    };
  }

  function describeFilterState(state) {
    const parts = [];
    if (state.screen && state.screen !== "all") {
      const tabNames = { screened: "Quality", momentum: "Momentum", garp: "GARP", cashcow: "Cashcow", turnaround: "Turnaround", dividend_growth: "Dividend Growth", watchlist: "Watchlist" };
      parts.push("Tab: " + (tabNames[state.screen] || state.screen));
    }
    if (state.market) parts.push("Market: " + state.market);
    if (state.search) parts.push("Search: " + state.search);
    const cf = state.columnFilters || {};
    Object.keys(cf).forEach(col => {
      const f = cf[col];
      if (f.min !== null && f.min !== undefined && f.max !== null && f.max !== undefined) {
        parts.push(f.min + " <= " + col + " <= " + f.max);
      } else if (f.min !== null && f.min !== undefined) {
        parts.push(col + " >= " + f.min);
      } else if (f.max !== null && f.max !== undefined) {
        parts.push(col + " <= " + f.max);
      }
    });
    return parts.length ? parts.join(", ") : "No filters set";
  }

  function applyPreset(preset) {
    // Apply screen tab
    if (preset.screen) {
      currentScreen = preset.screen;
      document.querySelectorAll("#screen-tabs .nav-link").forEach(l => {
        l.classList.toggle("active", l.dataset.screen === preset.screen);
      });
      updateStrategyDescription(currentScreen);
    }
    // Apply market
    document.getElementById("f-market").value = preset.market || "";
    // Apply search
    document.getElementById("f-search").value = preset.search || "";
    // Apply column filters
    Object.keys(columnFilters).forEach(k => delete columnFilters[k]);
    if (preset.columnFilters) {
      Object.assign(columnFilters, preset.columnFilters);
    }
    currentPage = 1;
    sortCol = "종합점수";
    sortOrder = "desc";
    buildHeader();
    loadStocks();
    showToast("Preset loaded: " + preset.name);
  }

  function renderPresetDropdown() {
    const presets = getPresets();
    const dropdown = document.getElementById("preset-dropdown");
    if (!presets.length) {
      dropdown.innerHTML = '<li><span class="dropdown-item text-muted small">No saved presets</span></li>';
      return;
    }
    dropdown.innerHTML = presets.map((p, i) => `
      <li class="preset-item">
        <a class="dropdown-item d-flex align-items-center gap-2 preset-load-btn" href="#" data-idx="${i}">
          <div class="flex-grow-1" style="min-width:0;">
            <div class="fw-semibold small">${escapeHtml(p.name)}</div>
            <div class="text-muted preset-desc">${escapeHtml(describeFilterState(p))}</div>
          </div>
          <button class="btn btn-outline-danger btn-sm preset-del-btn px-1 py-0" data-idx="${i}" title="Delete">&times;</button>
        </a>
      </li>
    `).join("") + '<li><hr class="dropdown-divider"></li><li><a class="dropdown-item text-danger small preset-clear-all" href="#">Delete All Presets</a></li>';

    // Bind load
    dropdown.querySelectorAll(".preset-load-btn").forEach(btn => {
      btn.addEventListener("click", e => {
        e.preventDefault();
        if (e.target.closest(".preset-del-btn")) return;
        const idx = parseInt(btn.dataset.idx);
        const presets = getPresets();
        if (presets[idx]) applyPreset(presets[idx]);
      });
    });

    // Bind delete
    dropdown.querySelectorAll(".preset-del-btn").forEach(btn => {
      btn.addEventListener("click", e => {
        e.preventDefault();
        e.stopPropagation();
        const idx = parseInt(btn.dataset.idx);
        const presets = getPresets();
        const name = presets[idx]?.name || "";
        presets.splice(idx, 1);
        savePresets(presets);
        renderPresetDropdown();
        showToast("Preset deleted: " + name);
      });
    });

    // Bind clear all
    const clearAll = dropdown.querySelector(".preset-clear-all");
    if (clearAll) {
      clearAll.addEventListener("click", e => {
        e.preventDefault();
        if (!confirm("Delete all saved presets?")) return;
        savePresets([]);
        renderPresetDropdown();
        showToast("All presets deleted");
      });
    }
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // Save preset button -> open modal
  document.getElementById("btn-save-preset").addEventListener("click", () => {
    const state = getCurrentFilterState();
    document.getElementById("preset-save-summary").textContent = describeFilterState(state);
    document.getElementById("preset-name-input").value = "";
    const modal = new bootstrap.Modal(document.getElementById("preset-save-modal"));
    modal.show();
    setTimeout(() => document.getElementById("preset-name-input").focus(), 200);
  });

  // Confirm save
  document.getElementById("btn-confirm-save-preset").addEventListener("click", () => {
    const name = document.getElementById("preset-name-input").value.trim();
    if (!name) {
      document.getElementById("preset-name-input").classList.add("is-invalid");
      return;
    }
    document.getElementById("preset-name-input").classList.remove("is-invalid");

    const state = getCurrentFilterState();
    state.name = name;
    state.createdAt = new Date().toISOString();

    const presets = getPresets();
    // Overwrite if same name exists
    const existIdx = presets.findIndex(p => p.name === name);
    if (existIdx >= 0) {
      presets[existIdx] = state;
    } else {
      presets.push(state);
    }
    savePresets(presets);
    renderPresetDropdown();

    bootstrap.Modal.getInstance(document.getElementById("preset-save-modal")).hide();
    showToast("Preset saved: " + name);
  });

  // Enter key in preset name input
  document.getElementById("preset-name-input").addEventListener("keydown", e => {
    if (e.key === "Enter") {
      e.preventDefault();
      document.getElementById("btn-confirm-save-preset").click();
    }
  });

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
    "FCF수익률(%)": "FCF Yield (자유현금흐름 수익률)\n정의: 시가총액 대비 FCF(영업CF - CAPEX) 비율\n계산: FCF수익률 = (영업CF - CAPEX) / 시가총액 × 100\n높을수록 현금 창출력 대비 저평가",
    "현금전환율(%)": "현금전환율 (Cash Conversion)\n정의: 순이익 대비 영업현금흐름 비율\n계산: 영업CF / 순이익 × 100\n100% 이상이면 이익이 실제 현금으로 뒷받침됨",
    "CAPEX비율(%)": "CAPEX 비율\n정의: 영업CF 대비 설비투자 비중\n계산: CAPEX / 영업CF × 100\n낮을수록 경자산(asset-light) 비즈니스",
    "영업CF_CAGR": "영업CF CAGR\n정의: 영업활동현금흐름의 연평균 성장률\n현금 창출 능력의 성장 추세",
    "FCF_CAGR": "FCF CAGR\n정의: 자유현금흐름(영업CF - CAPEX)의 연평균 성장률\n지속가능한 현금 성장력",
    "영업CF_연속성장": "영업CF 연속성장\n최근 몇 년간 연속으로 영업CF가 성장한 연도 수",
    "TTM_CAPEX": "TTM CAPEX\n최근 연간 유형자산 취득액 (설비투자)",
    "TTM_FCF": "TTM FCF (자유현금흐름)\n계산: 영업CF - CAPEX\n실제로 주주에게 돌아갈 수 있는 현금",
    "부채비율(%)": "부채비율\n정의: 총부채를 자기자본으로 나눈 값\n계산: 부채비율(%) = (총부채 / 자기자본) × 100\n낮을수록 재정 건전성이 좋음",
    "이익품질_양호": "이익품질_양호: 영업현금흐름이 순이익보다 많은지 여부\n현금 기반 이익인지 확인하는 지표 (1=양호, 0=저조)",
    "흑자전환": "흑자전환: 적자에서 흑자로 전환되었는지 여부 (1=전환, 0=미전환)\n실적 반등 종목을 찾는 데 중요한 지표",
    "이익률_변동폭": "이익률_변동폭: 영업이익률의 최근 변화 폭\n변동폭이 작을수록 이익이 안정적",
    "F스코어": "Piotroski F-Score (0~9점)\n재무건전성 종합 점수\nF1:수익성 F2:영업CF F3:ROA개선 F4:이익품질\nF5:레버리지감소 F6:유동성개선 F7:희석없음\nF8:매출총이익률개선 F9:자산회전율개선\n7점 이상 = 재무적으로 매우 건전",
    "부채상환능력": "부채상환능력\n정의: 영업CF / 부채총계\n1.0 = 영업CF 1년으로 부채 전액 상환 가능\n높을수록 부채 부담이 적고 안전",
    "52주_최고대비(%)": "52주 최고가 대비 현재 주가 위치\n음수 = 고점 대비 하락 중\n-10% 이하 = 조정 구간 진입",
    "52주_최저대비(%)": "52주 최저가 대비 현재 주가 위치\n양수 = 저점 대비 상승\n높을수록 저점에서 많이 반등",
    "MA20_이격도(%)": "20일 이동평균선 이격도\n양수 = 단기 MA 위\n음수 = 단기 MA 아래 (과매도 가능)",
    "MA60_이격도(%)": "60일 이동평균선 이격도\n양수 = 중기 상승 추세\n음수 = 중기 하락 추세",
    "RSI_14": "RSI 14일 (상대강도지수)\n70 이상 = 과매수\n30 이하 = 과매도\n50 = 중립",
    "거래대금_20일평균": "최근 20거래일 평균 거래대금\n유동성(거래 활발도)을 나타내는 지표",
    "거래대금_증감(%)": "거래대금 증감률\n최근 5일 평균 / 20일 평균 - 1\n급등 시 관심 증가 신호",
    "변동성_60일(%)": "60일 변동성 (연환산)\n수익률 표준편차 × √252\n낮을수록 안정적",
    // 계절성 통제 지표
    "Q_매출_YoY(%)": "분기 매출 YoY (전년동기비)\n최근 분기 매출 vs 전년 같은 분기\n계절성을 제거한 진짜 매출 성장률",
    "Q_영업이익_YoY(%)": "분기 영업이익 YoY (전년동기비)\n최근 분기 영업이익 vs 전년 같은 분기\n계절성을 제거한 진짜 이익 성장률",
    "Q_순이익_YoY(%)": "분기 순이익 YoY (전년동기비)\n최근 분기 순이익 vs 전년 같은 분기\n계절성을 제거한 진짜 순이익 성장률",
    "Q_매출_연속YoY성장": "분기 매출 연속 YoY 성장\n몇 분기 연속 전년동기 대비 매출 성장 중인지\n높을수록 계절성 무관 안정 성장",
    "Q_영업이익_연속YoY성장": "분기 영업이익 연속 YoY 성장\n몇 분기 연속 전년동기 대비 영업이익 성장 중인지",
    "Q_순이익_연속YoY성장": "분기 순이익 연속 YoY 성장\n몇 분기 연속 전년동기 대비 순이익 성장 중인지",
    "TTM_매출_YoY(%)": "TTM 매출 YoY\n최근 4분기 합 vs 전년 4분기 합\n연환산 매출의 전년 대비 성장률",
    "TTM_영업이익_YoY(%)": "TTM 영업이익 YoY\n최근 4분기 합 vs 전년 4분기 합\n연환산 영업이익의 전년 대비 성장률",
    "TTM_순이익_YoY(%)": "TTM 순이익 YoY\n최근 4분기 합 vs 전년 4분기 합\n연환산 순이익의 전년 대비 성장률",
    "최근분기": "최근 분기: 가장 최근 수집된 분기 기준일",
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
      formula: "종합점수 = 저PER×1.5 + 저PBR×1.0 + ROE×2.0 + 매출CAGR×2.0 + 영업이익CAGR×2.0 + 순이익CAGR×1.0 + F-Score×2.0 + FCF수익률×1.5 + ..."
    },
    screened: {
      title: "🏆 우량주 (Quality) 전략",
      criteria: "ROE ≥ 5% · PER 1-50 · PBR 0.1-10 · 매출 연속성장 ≥ 2년 · 순이익 연속성장 ≥ 1년 · F-Score ≥ 5",
      formula: "종합점수 기준 정렬 (밸류에이션 + 성장성 + 재무건전성 + FCF 수익률 종합)"
    },
    momentum: {
      title: "🚀 모멘텀/고성장 (Momentum) 전략",
      criteria: "매출 CAGR ≥ 15% OR 영업이익 CAGR ≥ 15% · 이익률 개선 · ROE ≥ 5%",
      formula: "점수 = 영업이익CAGR×2.5 + Q매출YoY×2.0 + Q영업이익YoY×2.0 + 매출CAGR×2.0 + Q연속YoY성장×1.5 + ROE×1.5 + RSI×1.0 + MA20×1.0"
    },
    garp: {
      title: "💎 GARP (성장 대비 합리적 가격) 전략",
      criteria: "PEG < 1.5 · 매출 CAGR ≥ 10% · ROE ≥ 12% · PER 5-30",
      formula: "점수 = 저PEG×3.0 + ROE×2.0 + 매출CAGR×2.0 + 이익CAGR×1.5 + 저PER×1.5 + 저PBR×1.0 + 현금전환율×1.0 + F-Score×0.5"
    },
    cashcow: {
      title: "💰 캐시카우 (현금창출 우량주) 전략",
      criteria: "ROE ≥ 10% · 영업이익률 ≥ 10% · 부채비율 < 100% · 이익품질 양호 · F-Score ≥ 6",
      formula: "점수 = FCF수익률×2.5 + 부채상환능력×2.0 + ROE×2.0 + 영업이익률×2.0 + 저부채×1.5 + F-Score×1.0 + 배당×0.5"
    },
    turnaround: {
      title: "📈 턴어라운드 (실적 반등) 전략",
      criteria: "적자→흑자 전환 OR 영업이익률 +5%p 급개선 · 현재 순이익 > 0 · 시가총액 ≥ 300억",
      formula: "점수 = 이익률변동×2.0 + 매출CAGR×2.0 + 흑전보너스×2.0 + 급개선×1.5 + ROE×1.5 + 과매도RSI×1.0 + 52W저점×1.0"
    },
    dividend_growth: {
      title: "💰 배당 성장 (수익+배당 동반증가) 전략",
      criteria: "순이익 연속성장 ≥ 2년 · 배당금 연속증가 ≥ 1년 · DPS CAGR > 0% · ROE ≥ 5% · 배당수익률 > 0% · 시가총액 ≥ 300억",
      formula: "점수 = DPS_CAGR×3.0 + 순이익CAGR×2.5 + 배당연속증가×2.0 + 순이익연속성장×2.0 + ROE×1.5 + 배당수익률×1.5 + 저부채×1.0"
    },
    watchlist: {
      title: "★ 관심 종목",
      criteria: "별표로 저장한 관심 종목입니다. 브라우저에 저장되며 서버에 전송되지 않습니다.",
      formula: "테이블 각 행의 ★ 버튼으로 추가/제거"
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
      { key: "F스코어", label: "F-Score", fmt: "int" },
      { key: "영업이익률(%)", label: "OPM%", fmt: "f2" },
      { key: "매출_CAGR", label: "Rev CAGR", fmt: "f1" },
      { key: "FCF수익률(%)", label: "FCF%", fmt: "f2" },
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
      { key: "F스코어", label: "F-Score", fmt: "int" },
      { key: "매출_연속성장", label: "RevGrowth", fmt: "int" },
      { key: "FCF수익률(%)", label: "FCF%", fmt: "f2" },
      { key: "배당수익률(%)", label: "Div%", fmt: "f2" },
      { key: "괴리율(%)", label: "Gap%", fmt: "f2" },
      { key: "종합점수", label: "Score", fmt: "f1" },
    ],
    momentum: [
      { key: "종목코드", label: "Code" },
      { key: "종목명", label: "Name" },
      { key: "시장구분", label: "Market" },
      { key: "종가", label: "Price", fmt: "int" },
      { key: "영업이익_CAGR", label: "OP CAGR", fmt: "f1" },
      { key: "매출_CAGR", label: "Rev CAGR", fmt: "f1" },
      { key: "Q_매출_YoY(%)", label: "Q Rev YoY", fmt: "f1" },
      { key: "Q_영업이익_YoY(%)", label: "Q OP YoY", fmt: "f1" },
      { key: "Q_매출_연속YoY성장", label: "QYoY Streak", fmt: "int" },
      { key: "영업이익률(%)", label: "OPM%", fmt: "f2" },
      { key: "RSI_14", label: "RSI", fmt: "f1" },
      { key: "종합점수", label: "Score", fmt: "f1" },
    ],
    garp: [
      { key: "종목코드", label: "Code" },
      { key: "종목명", label: "Name" },
      { key: "시장구분", label: "Market" },
      { key: "종가", label: "Price", fmt: "int" },
      { key: "PEG", label: "PEG", fmt: "f2" },
      { key: "PER", label: "PER", fmt: "f2" },
      { key: "PBR", label: "PBR", fmt: "f2" },
      { key: "매출_CAGR", label: "Rev CAGR", fmt: "f1" },
      { key: "ROE(%)", label: "ROE%", fmt: "f2" },
      { key: "현금전환율(%)", label: "CashConv%", fmt: "f1" },
      { key: "F스코어", label: "F-Score", fmt: "int" },
      { key: "종합점수", label: "Score", fmt: "f1" },
    ],
    cashcow: [
      { key: "종목코드", label: "Code" },
      { key: "종목명", label: "Name" },
      { key: "시장구분", label: "Market" },
      { key: "종가", label: "Price", fmt: "int" },
      { key: "FCF수익률(%)", label: "FCF%", fmt: "f2" },
      { key: "부채상환능력", label: "DebtPay", fmt: "f2" },
      { key: "영업이익률(%)", label: "OPM%", fmt: "f2" },
      { key: "부채비율(%)", label: "Debt%", fmt: "f1" },
      { key: "ROE(%)", label: "ROE%", fmt: "f2" },
      { key: "F스코어", label: "F-Score", fmt: "int" },
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
      { key: "RSI_14", label: "RSI", fmt: "f1" },
      { key: "52주_최고대비(%)", label: "52W High%", fmt: "f1" },
      { key: "ROE(%)", label: "ROE%", fmt: "f2" },
      { key: "PER", label: "PER", fmt: "f2" },
      { key: "종합점수", label: "Score", fmt: "f1" },
    ],
    dividend_growth: [
      { key: "종목코드", label: "Code" },
      { key: "종목명", label: "Name" },
      { key: "시장구분", label: "Market" },
      { key: "종가", label: "Price", fmt: "int" },
      { key: "DPS_CAGR", label: "DPS CAGR%", fmt: "f2" },
      { key: "순이익_CAGR", label: "NI CAGR%", fmt: "f2" },
      { key: "배당수익률(%)", label: "Div%", fmt: "f2" },
      { key: "배당_연속증가", label: "Div GrowYrs", fmt: "int" },
      { key: "순이익_연속성장", label: "NI GrowYrs", fmt: "int" },
      { key: "ROE(%)", label: "ROE%", fmt: "f2" },
      { key: "부채비율(%)", label: "Debt%", fmt: "f1" },
      { key: "배당성장_점수", label: "Score", fmt: "f1" },
    ],
    watchlist: [
      { key: "종목코드", label: "Code" },
      { key: "종목명", label: "Name" },
      { key: "시장구분", label: "Market" },
      { key: "종가", label: "Price", fmt: "int" },
      { key: "PER", label: "PER", fmt: "f2" },
      { key: "PBR", label: "PBR", fmt: "f2" },
      { key: "ROE(%)", label: "ROE%", fmt: "f2" },
      { key: "F스코어", label: "F-Score", fmt: "int" },
      { key: "영업이익률(%)", label: "OPM%", fmt: "f2" },
      { key: "매출_CAGR", label: "Rev CAGR", fmt: "f1" },
      { key: "FCF수익률(%)", label: "FCF%", fmt: "f2" },
      { key: "괴리율(%)", label: "Gap%", fmt: "f2" },
      { key: "종합점수", label: "Score", fmt: "f1" },
    ],
  };

  // ── Filterable columns ──
  const FILTERABLE_COLUMNS = [
    "PER", "PBR", "ROE(%)", "영업이익률(%)", "배당수익률(%)",
    "매출_CAGR", "영업이익_CAGR", "순이익_CAGR", "적정주가_SRIM",
    "괴리율(%)", "종합점수", "FCF수익률(%)", "부채비율(%)",
    "매출_연속성장", "이익률_변동폭", "F스코어",
    "52주_최고대비(%)", "52주_최저대비(%)", "RSI_14", "변동성_60일(%)",
    "Q_매출_YoY(%)", "Q_영업이익_YoY(%)", "Q_순이익_YoY(%)",
    "Q_매출_연속YoY성장", "TTM_매출_YoY(%)", "TTM_영업이익_YoY(%)"
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
    const starTh = `<th style="width:24px;text-align:center;cursor:default;" title="관심 종목">★</th>`;
    headerRow.innerHTML = starTh + cols.map(c => {
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

    // watchlist 탭: 저장된 코드 목록으로 필터링
    let apiScreen = currentScreen;
    let codesParam = "";
    if (currentScreen === "watchlist") {
      const wl = [...getWatchlist()];
      if (wl.length === 0) {
        renderTable([]);
        renderPagination(0, 1, pageSize);
        return;
      }
      apiScreen = "all";
      codesParam = wl.join(",");
    }

    const params = new URLSearchParams({
      screen: apiScreen,
      page: currentPage,
      size: pageSize,
      sort: sortCol,
      order: sortOrder === "none" ? "desc" : sortOrder,
    });
    if (market) params.set("market", market);
    if (q) params.set("q", q);
    if (codesParam) params.set("codes", codesParam);

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
      const msg = currentScreen === "watchlist"
        ? "관심 종목이 없습니다. 테이블에서 ★ 버튼으로 추가하세요."
        : "No data. Run the pipeline first.";
      tbody.innerHTML = `<tr><td colspan="${cols.length + 1}" class="text-center text-muted py-4">${msg}</td></tr>`;
      return;
    }
    const wl = getWatchlist();
    tbody.innerHTML = items.map(s => {
      const code = s["종목코드"];
      const watched = wl.has(code);
      const starCell = `<td style="text-align:center;padding:2px 4px;"><button class="watch-btn${watched ? " watched" : ""}" data-code="${code}">${watched ? "★" : "☆"}</button></td>`;
      const cells = cols.map(c => {
        const v = s[c.key];
        let cls = "";
        if (c.key === "괴리율(%)" || c.key === "이익률_변동폭") cls = valClass(v);
        if (c.key === "시장구분") {
          return `<td><span class="badge ${v === "KOSPI" ? "bg-primary" : "bg-danger"}">${v || "-"}</span></td>`;
        }
        return `<td class="${cls}">${fmt(v, c.fmt)}</td>`;
      }).join("");
      return `<tr data-code="${code}">${starCell}${cells}</tr>`;
    }).join("");

    // 별표 버튼 이벤트
    tbody.querySelectorAll(".watch-btn").forEach(btn => {
      btn.addEventListener("click", e => {
        e.stopPropagation();
        toggleWatch(btn.dataset.code);
      });
    });
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
    "DebtPay": "부채상환능력: 영업CF / 부채총계\n1.0 이상이면 1년 내 부채 전액 상환 가능",
    "CashConv%": "현금전환율: 영업CF / 순이익 × 100\n100% 이상이면 이익이 현금으로 뒷받침됨",
    "OCF CAGR": "영업CF CAGR: 영업활동현금흐름의 연평균 성장률\n현금 창출 능력의 성장 추세",
    "F-Score": "Piotroski F-Score (0~9점)\n7+ = 재무적으로 매우 건전\n5-6 = 보통\n4 이하 = 주의 필요",
    "52W High%": "52주 최고가 대비 위치\n음수 = 고점 대비 하락 중",
    "52W Low%": "52주 최저가 대비 위치\n양수 = 저점 대비 상승",
    "RSI": "RSI 14일: 70+ 과매수, 30- 과매도",
    "MA20%": "20일 이동평균 이격도\n양수=MA 위, 음수=MA 아래",
    "Vol60%": "60일 연환산 변동성\n낮을수록 안정적",
    "Score": "종합점수: 밸류에이션 + 성장성 + F-Score + FCF수익률 등 종합",
  };

  // ── Financial chart ──
  let financialChart = null;

  async function loadFinancialChart(code) {
    const area = document.getElementById("financial-chart-area");
    area.style.display = "none";
    try {
      const res = await fetch(`/api/stocks/${code}/financials`);
      const data = await res.json();
      if (!data.years || !data.years.length || !data.series || !data.series.length) return;

      area.style.display = "block";
      if (financialChart) { financialChart.destroy(); financialChart = null; }

      const COLORS = ["#0d6efd", "#198754", "#dc3545"];
      const LABELS = { "매출액": "매출액", "영업이익": "영업이익", "당기순이익": "순이익" };

      const ctx = document.getElementById("financial-chart").getContext("2d");
      financialChart = new Chart(ctx, {
        type: "bar",
        data: {
          labels: data.years,
          datasets: data.series.map((s, i) => ({
            label: LABELS[s.name] || s.name,
            data: s.data,
            backgroundColor: COLORS[i % COLORS.length] + "bb",
            borderColor: COLORS[i % COLORS.length],
            borderWidth: 1,
          })),
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { position: "top", labels: { font: { size: 10 }, boxWidth: 12 } },
            tooltip: {
              callbacks: {
                label: ctx => {
                  const v = ctx.parsed.y;
                  if (v == null) return "-";
                  return ` ${ctx.dataset.label}: ${Number(v).toLocaleString("ko-KR")}`;
                }
              }
            }
          },
          scales: {
            y: { ticks: { font: { size: 9 }, callback: v => Number(v).toLocaleString("ko-KR") } },
            x: { ticks: { font: { size: 10 } } },
          },
        },
      });
    } catch (e) { console.error("Chart error", e); }
  }

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
        ["DebtPay", d["부채상환능력"], "f2"],
        ["Div%", d["배당수익률(%)"], "f2"], ["FCF%", d["FCF수익률(%)"], "f2"],
        ["CashConv%", d["현금전환율(%)"], "f1"],
        ["Earn Yield%", d["이익수익률(%)"], "f2"],
        ["Rev CAGR", d["매출_CAGR"], "f1"], ["OP CAGR", d["영업이익_CAGR"], "f1"],
        ["NI CAGR", d["순이익_CAGR"], "f1"], ["OCF CAGR", d["영업CF_CAGR"], "f1"],
        ["Rev Streak", d["매출_연속성장"], "int"], ["OP Streak", d["영업이익_연속성장"], "int"],
        ["S-RIM", d["적정주가_SRIM"], "int"], ["Gap%", d["괴리율(%)"], "f2"],
        ["F-Score", d["F스코어"], "int"],
        ["52W High%", d["52주_최고대비(%)"], "f1"], ["52W Low%", d["52주_최저대비(%)"], "f1"],
        ["RSI", d["RSI_14"], "f1"], ["MA20%", d["MA20_이격도(%)"], "f1"],
        ["Vol60%", d["변동성_60일(%)"], "f1"],
        ["Score", d["종합점수"], "f1"],
      ];

      const pillsHtml = metrics.map(([lbl, val, type]) => {
        const display = val != null ? (type === "str" ? val : fmt(val, type)) : "-";
        const tooltip = DETAIL_TOOLTIPS[lbl] || "";
        const tooltipAttr = tooltip ? `data-bs-toggle="tooltip" data-bs-placement="top" title="${tooltip.replace(/"/g, '&quot;')}"` : "";
        return `<div class="metric-pill" ${tooltipAttr}><span class="lbl">${lbl}</span><br><span class="val">${display}</span></div>`;
      }).join("");

      document.getElementById("detail-metrics").innerHTML = pillsHtml;

      // 관심 종목 버튼 상태 업데이트
      const btnWatch = document.getElementById("btn-watch-detail");
      btnWatch.dataset.code = code;
      const wl = getWatchlist();
      const isWatched = wl.has(code);
      btnWatch.textContent = isWatched ? "★ 관심 해제" : "☆ 관심 종목";
      btnWatch.className = `btn btn-sm ${isWatched ? "btn-warning" : "btn-outline-warning"}`;

      // Set up analysis button with stock code
      const btnAnalysis = document.getElementById("btn-analysis");
      btnAnalysis.dataset.code = code;

      // Check if report exists and update button label
      try {
        const rptRes = await fetch(`/api/stocks/${code}/report`);
        const rptData = await rptRes.json();
        if (rptData.exists) {
          btnAnalysis.innerHTML = 'AI 정성 분석 <span class="badge bg-success ms-1">보고서 있음</span>';
        } else {
          btnAnalysis.textContent = 'AI 정성 분석';
        }
      } catch (_) {
        btnAnalysis.textContent = 'AI 정성 분석';
      }

      // Initialize tooltips for modal
      setTimeout(() => {
        document.querySelectorAll('#detail-metrics [data-bs-toggle="tooltip"]').forEach(el => {
          new bootstrap.Tooltip(el, { delay: { show: 200, hide: 100 } });
        });
      }, 100);

      new bootstrap.Modal(document.getElementById("detail-modal")).show();

      // 재무 추이 차트 로드
      loadFinancialChart(code);
    } catch (err) { console.error("Detail error", err); }
  });

  // ── Analysis Report ──
  async function openReport(code, forceRegenerate = false) {
    const reportModal = new bootstrap.Modal(document.getElementById("report-modal"));
    const loading = document.getElementById("report-loading");
    const content = document.getElementById("report-content");
    const btnRegen = document.getElementById("btn-regenerate");
    const reportMeta = document.getElementById("report-meta");

    // Close detail modal, open report modal
    const detailModal = bootstrap.Modal.getInstance(document.getElementById("detail-modal"));
    if (detailModal) detailModal.hide();

    content.innerHTML = "";
    loading.style.display = "block";
    btnRegen.style.display = "none";
    reportMeta.textContent = "";
    reportModal.show();

    try {
      // Check for existing report first (unless regenerating)
      if (!forceRegenerate) {
        const existRes = await fetch(`/api/stocks/${code}/report`);
        const existData = await existRes.json();
        if (existData.exists) {
          loading.style.display = "none";
          content.innerHTML = existData.report_html;
          document.getElementById("report-title").textContent =
            `AI 정성 분석 - ${existData["종목명"] || code}`;
          btnRegen.dataset.code = code;
          btnRegen.style.display = "inline-block";
          reportMeta.textContent = `${existData.model_used} | ${existData.generated_date}`;
          return;
        }
      }

      // Generate new report
      const res = await fetch(`/api/stocks/${code}/report`, { method: "POST" });
      const data = await res.json();

      loading.style.display = "none";

      if (data.error) {
        content.innerHTML = `<div class="alert alert-danger">${data.error}</div>`;
        return;
      }

      content.innerHTML = data.report_html;
      document.getElementById("report-title").textContent =
        `AI 정성 분석 - ${data["종목명"] || code}`;
      btnRegen.dataset.code = code;
      btnRegen.style.display = "inline-block";
      reportMeta.textContent = `${data.model_used} | ${data.generated_date}`;
    } catch (err) {
      loading.style.display = "none";
      content.innerHTML = `<div class="alert alert-danger">보고서 생성 실패: ${err.message}</div>`;
      console.error("Report error", err);
    }
  }

  // 모달 관심 종목 버튼
  document.getElementById("btn-watch-detail").addEventListener("click", () => {
    const code = document.getElementById("btn-watch-detail").dataset.code;
    if (code) toggleWatch(code);
  });

  // Analysis button in detail modal
  document.getElementById("btn-analysis").addEventListener("click", () => {
    const code = document.getElementById("btn-analysis").dataset.code;
    if (code) openReport(code);
  });

  // Regenerate button
  document.getElementById("btn-regenerate").addEventListener("click", () => {
    const code = document.getElementById("btn-regenerate").dataset.code;
    if (code && confirm("보고서를 재생성하시겠습니까? (Claude API 호출)")) {
      openReport(code, true);
    }
  });

  // ── Pipeline trigger ──
  const btnTrigger  = document.getElementById("btn-trigger");
  const btnSpinner  = document.getElementById("btn-trigger-spinner");
  const btnLabel    = document.getElementById("btn-trigger-label");
  let pipelinePoller = null;

  function setPipelineRunning(running) {
    btnTrigger.disabled = running;
    btnSpinner.classList.toggle("d-none", !running);
    btnLabel.textContent = running ? "Running…" : "Run Pipeline";
  }

  async function pollPipelineStatus() {
    try {
      const res = await fetch("/api/batch/status");
      const data = await res.json();
      if (!data.running) {
        clearInterval(pipelinePoller);
        pipelinePoller = null;
        setPipelineRunning(false);
        if (data.error) {
          showToast("파이프라인 오류: " + data.error);
        } else if (data.finished_at) {
          showToast("파이프라인 완료! 데이터를 새로고침합니다.");
          loadSummary();
          loadTabCounts();
          loadStocks();
        }
      }
    } catch (_) {}
  }

  // 페이지 로드 시 이미 실행 중이면 버튼 비활성화
  fetch("/api/batch/status").then(r => r.json()).then(data => {
    if (data.running) {
      setPipelineRunning(true);
      pipelinePoller = setInterval(pollPipelineStatus, 3000);
    }
  }).catch(() => {});

  btnTrigger.addEventListener("click", async () => {
    if (!confirm("Run the full data pipeline now?")) return;
    try {
      const res = await fetch("/api/batch/trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (res.status === 409) {
        showToast(data.message);
        return;
      }
      showToast(data.message || "Pipeline triggered");
      setPipelineRunning(true);
      pipelinePoller = setInterval(pollPipelineStatus, 3000);
    } catch (err) { showToast("Failed to trigger pipeline"); }
  });

  // ── Init ──
  buildHeader();
  loadSummary();
  loadTabCounts();
  loadStocks();
  updateStrategyDescription(currentScreen);
  updateWatchlistCount();
  renderPresetDropdown();
  initTooltips();
})();
