"""
Claude API를 활용한 종목 정성 분석 보고서 생성기.

5대 투자 대가(Warren Buffett, Aswath Damodaran, Philip Fisher,
Pat Dorsey, André Kostolany)의 핵심 철학을 기반으로
구조화된 정성 평가를 수행합니다.
"""

import json
import logging
from datetime import datetime

import anthropic

import config

log = logging.getLogger("Analyzer")

# ─────────────────────────────────────────
# 프롬프트 템플릿
# ─────────────────────────────────────────

SYSTEM_PROMPT = """\
당신은 한국 주식시장 전문 애널리스트입니다.
5대 투자 대가의 투자 철학을 기반으로 종목의 정성적 분석을 수행합니다.
반드시 제공된 정량 데이터를 근거로 분석하되, 데이터만으로는 알 수 없는
정성적 판단(경쟁우위, 경영진, 산업 전망 등)도 해당 기업에 대한
일반적으로 알려진 정보를 바탕으로 분석해 주세요.

분석 프레임워크:

1. Warren Buffett (경제적 해자 & 안전마진)
   - 경쟁 우위 지속 가능성 (Economic Moat)
   - 사업 모델의 이해 용이성 (Circle of Competence)
   - 경영진의 정직성과 역량 (Management Quality)
   - 안전마진 (Margin of Safety: S-RIM 괴리율 활용)
   - 장기 보유 적합성

2. Aswath Damodaran (내재가치 & 내러티브)
   - 기업의 성장 단계 (도입/성장/성숙/쇠퇴)
   - 내러티브 vs 숫자의 일관성 (Story-Numbers alignment)
   - 리스크 대비 보상 (Risk-Reward)
   - 재투자 효율성 (ROIC vs WACC 관점)

3. Philip Fisher (성장 잠재력 & 경영 품질)
   - R&D 및 혁신 역량
   - 이익률 개선 추세 (Profit Margin Trajectory)
   - 장기 성장 잠재력
   - 노사관계 및 조직 문화

4. Pat Dorsey (경제적 해자 심층 분석)
   - 네트워크 효과 (Network Effects)
   - 전환 비용 (Switching Costs)
   - 무형 자산 (브랜드, 특허, 라이선스)
   - 비용 우위 (Cost Advantages)
   - 해자 트렌드 (확대/유지/축소)

5. André Kostolany (시장 심리 & 역발상)
   - 현재 시장 심리 상태 (과열/공포/중립)
   - 역발상 투자 기회 여부
   - 유동성 및 수급 분석
   - 인내심 필요 정도 (달걀이론 관점)
"""

USER_PROMPT_TEMPLATE = """\
아래 종목의 정량 데이터를 분석하여, 5대 투자 대가 관점에서 정성 분석 보고서를 작성해주세요.

## 종목 정보
- 종목코드: {code}
- 종목명: {name}
- 시장: {market}

## 정량 데이터
{quant_data}

## 출력 형식

반드시 아래 JSON 형식으로 응답하세요. JSON 외 다른 텍스트는 포함하지 마세요.

```json
{{
  "buffett": {{
    "score": <1-10 정수>,
    "title": "<한 줄 요약>",
    "analysis": "<3-5문장의 분석>"
  }},
  "damodaran": {{
    "score": <1-10 정수>,
    "title": "<한 줄 요약>",
    "analysis": "<3-5문장의 분석>"
  }},
  "fisher": {{
    "score": <1-10 정수>,
    "title": "<한 줄 요약>",
    "analysis": "<3-5문장의 분석>"
  }},
  "dorsey": {{
    "score": <1-10 정수>,
    "title": "<한 줄 요약>",
    "analysis": "<3-5문장의 분석>"
  }},
  "kostolany": {{
    "score": <1-10 정수>,
    "title": "<한 줄 요약>",
    "analysis": "<3-5문장의 분석>"
  }},
  "composite_score": <1-100 정수, 가중평균: Buffett 25%, Damodaran 20%, Fisher 20%, Dorsey 20%, Kostolany 15%>,
  "investment_grade": "<A+/A/B+/B/C+/C/D 중 하나>",
  "summary": "<5-7문장의 종합 투자 의견>",
  "risks": ["<리스크1>", "<리스크2>", "<리스크3>"],
  "catalysts": ["<촉매1>", "<촉매2>", "<촉매3>"]
}}
```
"""


# ─────────────────────────────────────────
# 정량 데이터 포맷팅
# ─────────────────────────────────────────

# 분석에 포함할 지표 그룹
QUANT_SECTIONS = {
    "밸류에이션": [
        ("PER", "f2"), ("PBR", "f2"), ("PSR", "f2"), ("PEG", "f2"),
        ("ROE(%)", "f2"), ("EPS", "int"), ("BPS", "int"),
        ("이익수익률(%)", "f2"), ("적정주가_SRIM", "int"), ("괴리율(%)", "f2"),
    ],
    "수익성": [
        ("영업이익률(%)", "f2"), ("영업이익률_최근", "f2"), ("영업이익률_전년", "f2"),
        ("이익률_개선", "flag"), ("이익률_급개선", "flag"), ("이익률_변동폭", "f2"),
        ("이익품질_양호", "flag"), ("현금전환율(%)", "f1"), ("FCF수익률(%)", "f2"),
    ],
    "성장성": [
        ("매출_CAGR", "f1"), ("영업이익_CAGR", "f1"), ("순이익_CAGR", "f1"),
        ("영업CF_CAGR", "f1"), ("FCF_CAGR", "f1"),
        ("매출_연속성장", "int"), ("영업이익_연속성장", "int"),
        ("순이익_연속성장", "int"), ("영업CF_연속성장", "int"),
    ],
    "재무건전성": [
        ("F스코어", "int"), ("부채비율(%)", "f1"),
        ("부채상환능력", "f2"), ("CAPEX비율(%)", "f1"),
        ("흑자전환", "flag"),
    ],
    "배당": [
        ("배당수익률(%)", "f2"), ("DPS_최근", "int"), ("DPS_CAGR", "f2"),
        ("배당_연속증가", "int"), ("배당_수익동반증가", "flag"),
    ],
    "기술적 지표": [
        ("52주_최고대비(%)", "f1"), ("52주_최저대비(%)", "f1"),
        ("MA20_이격도(%)", "f1"), ("MA60_이격도(%)", "f1"),
        ("RSI_14", "f1"), ("거래대금_20일평균", "int"),
        ("거래대금_증감(%)", "f1"), ("변동성_60일(%)", "f1"),
    ],
    "TTM 실적": [
        ("TTM_매출", "int"), ("TTM_영업이익", "int"), ("TTM_순이익", "int"),
        ("TTM_영업CF", "int"), ("TTM_CAPEX", "int"), ("TTM_FCF", "int"),
        ("자본", "int"), ("부채", "int"), ("자산총계", "int"),
    ],
    "시가총액": [
        ("종가", "int"), ("시가총액", "int"),
    ],
}


def _fmt_val(v, fmt_type: str) -> str:
    if v is None:
        return "N/A"
    try:
        if fmt_type == "int":
            return f"{int(float(v)):,}"
        if fmt_type == "f1":
            return f"{float(v):.1f}"
        if fmt_type == "f2":
            return f"{float(v):.2f}"
        if fmt_type == "flag":
            return "O" if int(float(v)) == 1 else "X"
    except (ValueError, TypeError):
        return str(v)
    return str(v)


def format_quant_data(stock: dict) -> str:
    """종목 데이터를 분석용 텍스트로 포맷팅."""
    lines = []
    for section, metrics in QUANT_SECTIONS.items():
        lines.append(f"\n### {section}")
        for col, fmt_type in metrics:
            val = stock.get(col)
            lines.append(f"- {col}: {_fmt_val(val, fmt_type)}")
    return "\n".join(lines)


# ─────────────────────────────────────────
# Claude API 호출
# ─────────────────────────────────────────

def generate_report(stock: dict) -> dict:
    """
    Claude API를 호출하여 종목 분석 보고서를 생성합니다.

    Args:
        stock: dashboard_result의 한 종목 데이터 (dict)

    Returns:
        {
            "scores": { ... },       # 파싱된 JSON 분석 결과
            "report_html": "...",     # 렌더링된 HTML 보고서
            "model": "...",           # 사용된 모델명
            "generated_date": "...",  # 생성 시각
        }
    """
    if not config.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")

    code = str(stock.get("종목코드", "")).zfill(6)
    name = stock.get("종목명", "Unknown")
    market = stock.get("시장구분", "")

    quant_text = format_quant_data(stock)
    user_prompt = USER_PROMPT_TEMPLATE.format(
        code=code, name=name, market=market, quant_data=quant_text,
    )

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=config.ANALYSIS_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = message.content[0].text.strip()

    # JSON 파싱 (```json ... ``` 블록 제거)
    json_str = raw_text
    if "```json" in json_str:
        json_str = json_str.split("```json", 1)[1]
    if "```" in json_str:
        json_str = json_str.split("```", 1)[0]
    json_str = json_str.strip()

    try:
        scores = json.loads(json_str)
    except json.JSONDecodeError as e:
        log.error(f"JSON 파싱 실패 ({code} {name}): {str(e)[:100]}")
        log.debug(f"시도한 JSON: {json_str[:200]}")
        return {
            "scores": {},
            "report_html": f"<p>오류: JSON 파싱 실패</p>",
            "error": str(e)
        }

    generated_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_html = render_html(code, name, market, stock, scores, generated_date)

    return {
        "scores": scores,
        "report_html": report_html,
        "model": config.ANALYSIS_MODEL,
        "generated_date": generated_date,
    }


# ─────────────────────────────────────────
# HTML 보고서 렌더링
# ─────────────────────────────────────────

MASTER_INFO = {
    "buffett": {
        "name": "Warren Buffett",
        "icon": "WB",
        "color": "#1a5276",
        "philosophy": "경제적 해자 & 안전마진",
    },
    "damodaran": {
        "name": "Aswath Damodaran",
        "icon": "AD",
        "color": "#7d3c98",
        "philosophy": "내재가치 & 내러티브",
    },
    "fisher": {
        "name": "Philip Fisher",
        "icon": "PF",
        "color": "#1e8449",
        "philosophy": "성장 잠재력 & 경영 품질",
    },
    "dorsey": {
        "name": "Pat Dorsey",
        "icon": "PD",
        "color": "#b9770e",
        "philosophy": "경제적 해자 심층 분석",
    },
    "kostolany": {
        "name": "André Kostolany",
        "icon": "AK",
        "color": "#c0392b",
        "philosophy": "시장 심리 & 역발상",
    },
}


def _grade_color(grade: str) -> str:
    colors = {
        "A+": "#1a5276", "A": "#2471a3", "B+": "#1e8449",
        "B": "#7d8c3c", "C+": "#b9770e", "C": "#d35400", "D": "#c0392b",
    }
    return colors.get(grade, "#6c757d")


def _score_bar_width(score: int, max_score: int = 10) -> int:
    return max(5, min(100, int(score / max_score * 100)))


def render_html(code: str, name: str, market: str, stock: dict,
                scores: dict, generated_date: str) -> str:
    """분석 결과를 HTML 보고서로 렌더링."""

    composite = scores.get("composite_score", 0)
    grade = scores.get("investment_grade", "N/A")
    summary = scores.get("summary", "")
    risks = scores.get("risks", [])
    catalysts = scores.get("catalysts", [])

    # 대가별 분석 카드 HTML
    master_cards = ""
    for key, info in MASTER_INFO.items():
        m = scores.get(key, {})
        s = m.get("score", 0)
        title = m.get("title", "")
        analysis = m.get("analysis", "")
        bar_w = _score_bar_width(s)

        master_cards += f"""
        <div class="master-card">
          <div class="master-header" style="border-left: 4px solid {info['color']};">
            <div class="master-icon" style="background: {info['color']};">{info['icon']}</div>
            <div class="master-info">
              <div class="master-name">{info['name']}</div>
              <div class="master-philosophy">{info['philosophy']}</div>
            </div>
            <div class="master-score">
              <span class="score-num">{s}</span><span class="score-max">/10</span>
            </div>
          </div>
          <div class="score-bar-wrap">
            <div class="score-bar-fill" style="width: {bar_w}%; background: {info['color']};"></div>
          </div>
          <div class="master-title">{title}</div>
          <div class="master-analysis">{analysis}</div>
        </div>"""

    # 리스크 & 촉매 리스트
    risk_items = "".join(f'<li class="risk-item">{r}</li>' for r in risks)
    catalyst_items = "".join(f'<li class="catalyst-item">{c}</li>' for c in catalysts)

    # 주요 지표 요약
    key_metrics = ""
    for label, col, fmt in [
        ("PER", "PER", "f2"), ("PBR", "PBR", "f2"), ("ROE", "ROE(%)", "f1"),
        ("F-Score", "F스코어", "int"), ("영업이익률", "영업이익률(%)", "f1"),
        ("괴리율", "괴리율(%)", "f1"),
    ]:
        key_metrics += (
            f'<div class="kv-pill">'
            f'<span class="kv-label">{label}</span>'
            f'<span class="kv-value">{_fmt_val(stock.get(col), fmt)}</span>'
            f'</div>'
        )

    grade_color = _grade_color(grade)

    return f"""\
<div class="analysis-report">
  <div class="report-header">
    <div class="stock-identity">
      <h2 class="stock-name">{name}</h2>
      <span class="stock-code">{code}</span>
      <span class="stock-market badge {'bg-primary' if market == 'KOSPI' else 'bg-danger'}">{market}</span>
    </div>
    <div class="composite-section">
      <div class="composite-grade" style="background: {grade_color};">{grade}</div>
      <div class="composite-score-wrap">
        <div class="composite-label">종합 정성 점수</div>
        <div class="composite-num">{composite}<span class="composite-max">/100</span></div>
      </div>
    </div>
  </div>

  <div class="key-metrics">{key_metrics}</div>

  <div class="summary-box">
    <h4>종합 투자 의견</h4>
    <p>{summary}</p>
  </div>

  <h4 class="section-title">5대 투자 대가 관점 분석</h4>
  <div class="master-cards">{master_cards}</div>

  <div class="risk-catalyst-grid">
    <div class="risk-section">
      <h4>주요 리스크</h4>
      <ul class="risk-list">{risk_items}</ul>
    </div>
    <div class="catalyst-section">
      <h4>상승 촉매</h4>
      <ul class="catalyst-list">{catalyst_items}</ul>
    </div>
  </div>

  <div class="report-footer">
    <span>Generated by Claude ({scores.get('_model', config.ANALYSIS_MODEL)})</span>
    <span>{generated_date}</span>
  </div>
</div>"""
