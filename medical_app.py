import streamlit as st
import pdfplumber
import anthropic
import json
import re
import subprocess, sys
from datetime import date, timedelta
from io import BytesIO
from collections import defaultdict


for pkg in ['reportlab','anthropic']:
    try: __import__(pkg)
    except: subprocess.check_call([sys.executable,'-m','pip','install',pkg,'--break-system-packages','-q'])

st.set_page_config(page_title="리치앤아이 병력분석", page_icon="🏥", layout="wide")

# ===== URL 파라미터 읽기 =====
def get_url_params():
    try:
        params = st.query_params
        uid = params.get('uid', '')
        cid = params.get('cid', '')
        name = params.get('name', '')
        return uid, cid, name
    except: return '', '', ''

# ===== Firestore 저장 함수 =====

# ===== HTML 생성 (Firestore 저장용) =====
def generate_html(r, customer_name, today_str, cost_stats=None):
    """결과를 HTML 문자열로 생성 (Firestore 저장용)"""
    s1=r.get('section1',[])
    s2=r.get('section2',[])
    s3=r.get('section3',[])
    s4=r.get('section4',[])
    s5=r.get('section5',{})
    summary=r.get('요약',[])

    css = """<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;800;900&display=swap');
    .mr-wrap{font-family:'Noto Sans KR','Malgun Gothic',sans-serif;max-width:900px;margin:0 auto;padding:16px;}
    .mr-banner{background:linear-gradient(135deg,#0f1e3d,#1a2f5e);border-radius:16px;padding:20px 24px;margin-bottom:20px;border-bottom:4px solid #c9a84c;}
    .mr-banner-title{color:#c9a84c;font-size:20px;font-weight:900;}
    .mr-banner-customer{color:white;font-size:17px;font-weight:700;margin-top:6px;}
    .mr-banner-sub{color:#8899bb;font-size:12px;margin-top:4px;}
    .mr-sec-title{font-size:16px;font-weight:900;color:#1a2744;padding:12px 0 8px;border-bottom:3px solid #1a2744;margin-bottom:12px;display:flex;align-items:center;gap:8px;}
    .mr-sec-num{background:#1a2744;color:#c9a84c;width:26px;height:26px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:12px;font-weight:900;flex-shrink:0;}
    .mr-box{border:1.5px solid #e8eaf0;border-radius:10px;margin-bottom:10px;overflow:hidden;}
    .mr-box-title{padding:10px 14px;}
    .mr-box-title-text{color:white;font-size:14px;font-weight:800;}
    .mr-box-body{padding:10px 14px;background:white;}
    .mr-line{font-size:13px;color:#374151;padding:3px 0;border-bottom:1px solid #f3f4f6;}
    .mr-divider{height:3px;background:linear-gradient(90deg,#1a2744,#c9a84c,#1a2744);border-radius:2px;margin:16px 0;}
    .mr-d5-row{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0;}
    .mr-d5-ok{background:#f0fdf4;border:1.5px solid #86efac;border-radius:8px;padding:5px 12px;font-size:12px;font-weight:700;color:#16a34a;}
    .mr-d5-bad{background:#fef2f2;border:1.5px solid #fca5a5;border-radius:8px;padding:5px 12px;font-size:12px;font-weight:700;color:#dc2626;}
    .mr-summary-box{background:linear-gradient(135deg,#0f1e3d,#1a2f5e);border-radius:14px;padding:20px 24px;margin-top:20px;border-bottom:4px solid #c9a84c;}
    .mr-summary-title{color:#c9a84c;font-size:15px;font-weight:900;margin-bottom:12px;}
    .mr-summary-item{display:flex;gap:10px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.1);}
    .mr-summary-arrow{color:#c9a84c;font-size:13px;font-weight:900;flex-shrink:0;}
    .mr-summary-text{color:#e8d5a3;font-size:13px;line-height:1.6;}
    .mr-stat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px;}
    .mr-stat-box{background:white;border-radius:8px;padding:10px 12px;border:1px solid #e8eaf0;text-align:center;}
    .mr-stat-label{font-size:10px;color:#6b7280;font-weight:600;margin-bottom:3px;}
    .mr-stat-value{font-size:15px;font-weight:900;color:#1a2744;}
    </style>"""

    def make_box(title, lines, color='#1a2744'):
        lines_html = ''.join([f'<div class="mr-line">{l}</div>' for l in lines if l])
        return f'<div class="mr-box"><div class="mr-box-title" style="background:{color};"><div class="mr-box-title-text">{title}</div></div><div class="mr-box-body">{lines_html}</div></div>'

    html = css + '<div class="mr-wrap">'
    html += f'<div class="mr-banner"><div class="mr-banner-title">병력 고지사항 확인서</div><div class="mr-banner-customer">{customer_name} 고객님</div><div class="mr-banner-sub">분석일: {today_str} · 리치앤아이 · 글로벌금융판매</div></div>'

    if s1:
        html += '<div class="mr-sec-title"><span class="mr-sec-num">1</span>최근 3개월 이내 진료 기록</div>'
        for item in s1:
            if not isinstance(item, dict): continue
            lines = []
            lines.append(f"진료일: {item.get('진료일','')} | 최종: {item.get('최종진료일','')} | 통원 {item.get('통원횟수',0)}회")
            lines.append(f"병원: {item.get('병원','')}")
            if item.get('수술'): lines.append(f"수술: {item.get('수술')}")
            for d in item.get('투약',[]):
                if not isinstance(d, dict): continue
                first = f" (최초처방: {d.get('최초처방일','')})" if d.get('최초처방일') else ''
                lines.append(f"  · {d.get('약품명','')} ({d.get('성분명','')}) — {d.get('용도','')} — {d.get('투약일수',0)}일{first}")
            if item.get('치료내역'): lines.append(f"치료: {item.get('치료내역','')}")
            html += make_box(item.get('질병명',''), lines)
        html += '<div class="mr-divider"></div>'

    if s2:
        html += '<div class="mr-sec-title"><span class="mr-sec-num">2</span>최근 1년 이내 재검사 / 추가검사</div>'
        for item in s2:
            if not isinstance(item, dict): continue
            lines = []
            lines.append(f"최초검사일: {item.get('최초검사일','')} | 추가검사일: {item.get('추가검사일','')}")
            if item.get('최초검사내용'): lines.append(f"최초: {item.get('최초검사내용','')}")
            if item.get('추가검사내용'): lines.append(f"추가: {item.get('추가검사내용','')}")
            html += make_box(f"{item.get('질병명','')} [{item.get('구분','추가검사')}]", lines, '#0891b2')
        html += '<div class="mr-divider"></div>'

    if s3:
        html += '<div class="mr-sec-title"><span class="mr-sec-num">3</span>최근 5년 이내 병력</div>'
        def has_inop(item):
            고지 = item.get('고지항목',[]) if isinstance(item, dict) else []
            return '입원' in 고지 or '수술' in 고지
        s3_sorted = sorted(s3, key=lambda x: (0 if has_inop(x) else 1))
        for item in s3_sorted:
            if not isinstance(item, dict): continue
            고지항목 = item.get('고지항목',[])
            고지str = ' · '.join([f'[{g}]' for g in 고지항목]) if 고지항목 else ''
            title = f"{item.get('질병명','')}{'  '+고지str if 고지str else ''}"
            lines = [f"초진: {item.get('초진일','')} | 최종: {item.get('최종진료일','')} | 통원 {item.get('통원횟수',0)}회"]
            입원목록 = item.get('입원',[])
            if 입원목록:
                for h in 입원목록:
                    if isinstance(h, dict): lines.append(f"입원: {h.get('날짜','')} · {h.get('병원','')} · {h.get('일수',0)}일")
            else:
                lines.append("입원: 없음")
            수술목록 = item.get('수술',[])
            if 수술목록:
                for s in 수술목록:
                    if isinstance(s, dict): lines.append(f"수술: {s.get('수술명','')} · {s.get('날짜','')} · {s.get('병원','')}")
            else:
                lines.append("수술: 없음")
            for d in item.get('투약',[]):
                if isinstance(d, dict): lines.append(f"  · {d.get('약품명','')} ({d.get('성분명','')}) — {d.get('용도','')} — 합계 {d.get('합산일수',0)}일")
            if item.get('치료내역'): lines.append(f"치료: {item.get('치료내역','')}")
            html += make_box(title, lines, '#dc2626' if has_inop(item) else '#1a2744')
        html += '<div class="mr-divider"></div>'

    if s4:
        html += '<div class="mr-sec-title"><span class="mr-sec-num">4</span>약물 상시복용</div>'
        for item in s4:
            if not isinstance(item, dict): continue
            lines = [
                f"성분명: {item.get('성분명','')}",
                f"최초처방일: {item.get('최초처방일','')} | 최근처방일: {item.get('최근처방일','')}",
                f"복용 상태: {'현재 복용 중' if item.get('복용중') else '과거 복용'}"
            ]
            html += make_box(f"{item.get('약물분류','')} — {item.get('약품명','')}", lines, '#7c3aed')
        html += '<div class="mr-divider"></div>'

    diseases_11 = ['암','백혈병','고혈압','협심증','심근경색','심장판막증','간경화증','뇌졸중','당뇨','에이즈HIV','항문질환']
    해당목록 = s5.get('해당목록',[]) if isinstance(s5, dict) else []
    미해당 = [d for d in diseases_11 if d not in 해당목록]
    html += '<div class="mr-sec-title"><span class="mr-sec-num">5</span>최근 5년 이내 11대 질병</div>'
    if 해당목록:
        html += '<div style="margin-bottom:6px;"><b style="color:#dc2626;font-size:13px;">해당 있음:</b></div>'
        html += '<div class="mr-d5-row">' + ''.join([f'<span class="mr-d5-bad">{d}</span>' for d in 해당목록]) + '</div>'
        for item in (s5.get('상세',[]) if isinstance(s5, dict) else []):
            if not isinstance(item, dict): continue
            lines = [f"초진: {item.get('초진일','')} | 최종: {item.get('최종진료일','')} | 통원 {item.get('통원횟수',0)}회"]
            for h in item.get('입원',[]):
                if isinstance(h, dict): lines.append(f"입원: {h.get('날짜','')} · {h.get('병원','')} · {h.get('일수',0)}일")
            for s in item.get('수술',[]):
                if isinstance(s, dict): lines.append(f"수술: {s.get('수술명','')}")
            for d in item.get('투약',[]):
                if isinstance(d, dict): lines.append(f"투약: {d.get('약품명','')} ({d.get('용도','')}) — {d.get('합산일수',0)}일")
            if item.get('검사내용'): lines.append(f"검사: {item.get('검사내용','')}")
            html += make_box(item.get('질병명',''), lines, '#dc2626')
    html += '<div style="margin:8px 0 6px;"><b style="color:#16a34a;font-size:13px;">해당 없음:</b></div>'
    html += '<div class="mr-d5-row">' + ''.join([f'<span class="mr-d5-ok">{d}</span>' for d in 미해당]) + '</div>'
    html += '<div class="mr-divider"></div>'

    if cost_stats:
        year_data = cost_stats.get('year',{})
        total_paid = cost_stats.get('total_paid',0)
        avg_paid = cost_stats.get('avg_paid',0)
        total_count = cost_stats.get('total_count',0)
        html += f'<div class="mr-stat-grid"><div class="mr-stat-box"><div class="mr-stat-label">총 본인부담금</div><div class="mr-stat-value">{total_paid:,}원</div></div><div class="mr-stat-box"><div class="mr-stat-label">연평균 본인부담금</div><div class="mr-stat-value" style="color:#2563eb;">{avg_paid:,}원</div></div><div class="mr-stat-box"><div class="mr-stat-label">총 진료 건수</div><div class="mr-stat-value">{total_count}건</div></div></div>'
        html += '<div class="mr-sec-title"><span class="mr-sec-num">6</span>연도별 본인부담 의료비</div>'
        for y, d in year_data.items():
            html += f'<div style="display:flex;justify-content:space-between;padding:10px 14px;border:1px solid #e8eaf0;border-radius:10px;margin-bottom:8px;background:white;"><div><div style="font-size:14px;font-weight:800;color:#1a2744;">{y}년</div><div style="font-size:12px;color:#9ca3af;">{d["count"]}건 진료</div></div><div style="text-align:right;"><div style="font-size:15px;font-weight:900;color:#1D9E75;">{d["paid"]:,}원</div><div style="font-size:11px;color:#9ca3af;">보험혜택 {d["ins"]:,}원</div></div></div>'

    if summary:
        items_html = ''.join([f'<div class="mr-summary-item"><span class="mr-summary-arrow">▶</span><span class="mr-summary-text">{s}</span></div>' for s in summary])
        html += f'<div class="mr-summary-box"><div class="mr-summary-title">핵심 병력 요약</div>{items_html}</div>'

    html += '</div>'
    return html


def save_to_firestore(uid, cid, result, customer_name, today_str, cost_stats=None):
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore as fs
        import os, json

        # 이미 초기화됐는지 확인
        try:
            firebase_admin.get_app()
        except ValueError:
            # 환경변수나 secrets에서 Firebase 서비스 계정 키 읽기
            if 'firebase' in st.secrets:
                cred_dict = dict(st.secrets['firebase'])
                cred = credentials.Certificate(cred_dict)
            else:
                st.error("Firebase 설정이 없습니다. Streamlit secrets에 firebase 설정을 추가해주세요.")
                return False
            firebase_admin.initialize_app(cred)

        db_fs = fs.client()
        doc_ref = db_fs.collection('users').document(uid).collection('customers').document(cid).collection('meta').document('medical_result')
        # HTML로 변환해서 저장
        html_content = generate_html(result, customer_name, today_str, cost_stats)
        doc_ref.set({
            'html': html_content,
            'customerName': customer_name,
            'analyzedAt': fs.SERVER_TIMESTAMP,
            'today_str': today_str,
        })
        return True
    except Exception as e:
        st.error(f"저장 오류: {str(e)}")
        return False
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800;900&display=swap');
*{font-family:'Noto Sans KR','Malgun Gothic',sans-serif;}
.main .block-container{padding-top:1rem;padding-bottom:2rem;}
.top-banner{background:linear-gradient(135deg,#0f1e3d,#1a2f5e);border-radius:20px;padding:24px 32px;margin-bottom:24px;border-bottom:4px solid #c9a84c;box-shadow:0 8px 32px rgba(15,30,61,0.2);}
.banner-title{color:#c9a84c;font-size:22px;font-weight:900;}
.banner-customer{color:white;font-size:18px;font-weight:700;margin-top:6px;}
.banner-sub{color:#8899bb;font-size:13px;margin-top:4px;}
.badge-alert{display:inline-block;background:#dc2626;color:white;font-size:13px;font-weight:800;padding:5px 14px;border-radius:20px;margin-top:8px;}
.badge-ok{display:inline-block;background:#16a34a;color:white;font-size:13px;font-weight:800;padding:5px 14px;border-radius:20px;margin-top:8px;}
.badge-signal{display:inline-block;font-size:13px;font-weight:700;padding:5px 14px;border-radius:20px;margin-top:8px;margin-left:8px;}
.sec-title{font-size:17px;font-weight:900;color:#1a2744;padding:14px 0 10px;border-bottom:3px solid #1a2744;margin-bottom:14px;display:flex;align-items:center;gap:10px;}
.sec-num{background:#1a2744;color:#c9a84c;width:30px;height:30px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:13px;font-weight:900;flex-shrink:0;}
.item-title{font-size:15px;font-weight:800;color:#1a2744;padding:10px 0 8px;border-bottom:2px solid #e8eaf0;margin-bottom:8px;}
.disease-card{border-radius:12px;padding:16px 20px;margin-bottom:12px;border:2px solid #c7d2fe;background:#f8f9ff;}
.disease-card-warn{border-color:#fca5a5;background:#fff8f8;}
.dname{font-size:16px;font-weight:800;color:#1a2744;margin-bottom:10px;}
.code-badge{background:#1a2744;color:#c9a84c;font-size:11px;font-weight:700;padding:2px 8px;border-radius:5px;margin-left:6px;}
.warn-badge{background:#dc2626;color:white;font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px;margin-left:6px;}
.stats-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px;}
.stat-box{background:white;border-radius:8px;padding:10px 12px;border:1px solid #e8eaf0;text-align:center;}
.stat-label{font-size:10px;color:#6b7280;font-weight:600;margin-bottom:3px;}
.stat-value{font-size:16px;font-weight:900;color:#1a2744;}
.stat-red{color:#dc2626!important;}
.stat-blue{color:#2563eb!important;}
.recheck-box{background:#fffbeb;border:1.5px solid #fcd34d;border-radius:8px;padding:10px 14px;margin-bottom:10px;font-size:13px;color:#78350f;font-weight:600;line-height:1.6;}
.drug-card{background:white;border-radius:10px;padding:14px 18px;margin-bottom:8px;border:2px solid #e8eaf0;}
.drug-card-alert{border-color:#fca5a5;background:#fff8f8;}
.drug-name{font-size:16px;font-weight:800;color:#1a2744;margin-bottom:3px;}
.drug-comp{font-size:12px;color:#6b7280;margin-bottom:6px;}
.drug-purpose{display:inline-block;background:#eff6ff;color:#1d4ed8;font-size:12px;font-weight:600;padding:3px 10px;border-radius:6px;margin-bottom:8px;}
.drug-days-red{font-size:20px;font-weight:900;color:#dc2626;}
.drug-days-ok{font-size:20px;font-weight:900;color:#16a34a;}
.surgery-card{background:linear-gradient(135deg,#fff0f0,#fff);border:2px solid #dc2626;border-radius:12px;padding:14px 18px;margin-bottom:8px;display:flex;align-items:center;gap:14px;}
.surgery-name{font-size:15px;font-weight:800;color:#dc2626;margin-bottom:3px;}
.surgery-info{font-size:12px;color:#6b7280;}
.proc-box{background:#fffbeb;border:2px solid #fcd34d;border-radius:10px;padding:14px 18px;margin-top:10px;}
.proc-title{font-size:14px;font-weight:800;color:#92400e;margin-bottom:8px;}
.proc-item{font-size:13px;color:#78350f;padding:4px 0;border-bottom:1px solid #fde68a;display:flex;gap:8px;}
.d5-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;}
.d5-ok{background:#f0fdf4;border:1.5px solid #86efac;border-radius:8px;padding:6px 14px;font-size:13px;font-weight:700;color:#16a34a;}
.d5-bad{background:#fef2f2;border:1.5px solid #fca5a5;border-radius:8px;padding:6px 14px;font-size:13px;font-weight:700;color:#dc2626;}
.summary-box{background:linear-gradient(135deg,#0f1e3d,#1a2f5e);border-radius:16px;padding:24px 28px;margin-top:24px;border-bottom:4px solid #c9a84c;}
.summary-title{color:#c9a84c;font-size:16px;font-weight:900;margin-bottom:16px;}
.summary-item{display:flex;gap:12px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.1);align-items:flex-start;}
.summary-item:last-child{border-bottom:none;}
.summary-arrow{color:#c9a84c;font-size:15px;font-weight:900;flex-shrink:0;}
.summary-text{color:#e8d5a3;font-size:14px;line-height:1.6;}
.extract-box{background:white;border:2px solid #86efac;border-radius:10px;padding:12px 16px;margin-bottom:8px;display:flex;align-items:center;justify-content:space-between;}
.extract-label{font-size:14px;font-weight:700;color:#065f46;}
.extract-count{background:#16a34a;color:white;font-size:12px;font-weight:700;padding:3px 12px;border-radius:6px;}
.divider{height:3px;background:linear-gradient(90deg,#1a2744,#c9a84c,#1a2744);border-radius:2px;margin:20px 0;}
@media print {
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="stSidebarNav"] { display: none !important; }
    header { display: none !important; }
    footer { display: none !important; }
    .stButton { display: none !important; }
    [data-testid="stToolbar"] { display: none !important; }
    [data-testid="stDecoration"] { display: none !important; }
    .no-print { display: none !important; }
    .main .block-container { padding: 0 !important; max-width: 100% !important; }
    .stColumns { break-inside: avoid; }
    div[data-testid="column"] { break-inside: avoid; }
    @page { margin: 10mm; size: A4 portrait; }
}
</style>
""", unsafe_allow_html=True)

# ===== 질병코드 한글 매핑 =====
DN = {
    'AM513':'추간판변성(기타명시된)','AS3350':'요추 염좌 및 긴장','AM5457':'요통(요천부)',
    'AM501':'경추간판장애(신경뿌리병증)','AM171':'무릎관절증','AM179':'무릎관절증(상세불명)',
    'AM750':'어깨 유착성관절낭염','AM766':'아킬레스힘줄염','AM1996':'관절증(아래다리)',
    'AF432':'적응장애','AB001':'헤르페스바이러스 소수포피부염','AK591':'기능성 설사',
    'AJ0301':'재발성 연쇄알균편도염','AH108':'결막염','AJ383':'성대의 기타 질환',
    'AL720':'표피낭','AL239':'알레르기성 접촉피부염','AL309':'피부염(상세불명)',
    'AK0530':'만성 단순치주염','AK0531':'만성 복합치주염','AK0510':'치은염',
    'AJ209':'급성 기관지염','AN342':'기타 요도염','AN341':'비특이성 요도염',
    'AN419':'전립선 염증성 질환','AK297':'위염','AK929':'소화계통 상세불명 질환',
    'AH0411':'건성안증후군','AH001':'콩다래끼','AH0001':'내맥립종',
    'AH5221':'규칙난시','AH169':'각막염','AH571':'눈통증','AH1618':'표재성 각막염',
    'AL259':'접촉피부염(상세불명)','AL238':'알레르기성 접촉피부염(기타)',
    'AL210':'두피지루','AL301':'발한이상','AK035':'치아의 강직증',
    'AK0480':'치아뿌리낭','AK0462':'구강연결동','AS0252':'법랑질 파절',
    'AK0318':'치아 마모','AM8599':'골밀도 장애','AR318':'혈뇨',
    'AR060':'호흡곤란','AZ115':'바이러스질환 특수선별검사','AZ038':'의심질환 관찰',
    'AR1012':'명치통증','AS2340':'늑골 염좌 및 긴장','AJ9848':'폐의 기타 장애',
    'AK588':'과민대장증후군','BM5456':'요통(한방)','BM6096':'근염(아래다리)',
    'BM6266':'근육긴장(아래다리)','BM6268':'근육긴장(기타)','AJ40':'기관지염',
    'AA099':'위장염 및 결장염','AK291':'급성위염',
}

SURGERY_KW = [
    # 절제/적출/절개
    '절제술','적출술','절개술','절단술','봉합술','피판술',
    # 치과 수술
    '발치술','임플란트식립','치조골절제','임플란트고정체식립','고정체식립','식립술',
    # 이비인후과/편도
    '편도절제술','아데노이드절제술',
    # 복부/소화기
    '충수절제술','용종절제술','결장경하종양수술','위절제술','담낭절제술','장절제술',
    # 관절/척추
    '관절경','복강경','척추성형술','경피적척추성형술','골시멘트','추간판절제술','추체성형술',
    # 부인과
    '자궁절제술','제왕절개','자궁근종절제술','난소절제술','소작술','약물소작술','레이저소작술',
    # 피부/종양
    '낭종제거술','피부절제술','피부양성종양적출','종양절제','지방종절제','피지낭종제거',
    # 안과
    '산립종절개','백내장수술','유리체절제술','망막수술',
    # 기타 수술
    '치핵절제술','탈장수술','갑상선절제술','편평상피절제','고막절개술','골절정복술',
    '내고정술','외고정술','인공관절치환술','골이식술',
    # SNARE/올가미 시술 (내시경적 절제)
    'SNARE','snare','올가미절제','내시경절제','점막절제술','점막하박리술',
]
NOT_SURGERY_KW = [
    '단순처치','염증성처치','드레싱','창상처치','신경차단','관절천자',
    '관절강내주사','히알루론산','스테로이드주사','물리치료','표층열','심층열',
    '초음파치료','전기자극','견인치료','스케일링','치주소파','치근활택',
    '신경치료','근관성형','크라운','보철','주사치료','재활저출력','간헐적견인',
    '경피적전기','조영술','혈관조영','도관삽입','스텐트삽입','풍선확장',
    '화상처치','욕창처치','봉합처치','창상봉합처치',
]
CRITICAL_CODES = ['AF','F3','F4','F5','F6','F7','F8','F9']
CRITICAL_KW = ['암','악성','종양','백혈병','뇌졸중','심근경색','협심증','간경화','당뇨','고혈압']

def dname(code, raw=''):
    if code and code in DN: return DN[code]
    if raw: return re.sub(r'\(양방\)|\(한방\)','',raw).strip()
    return code or ''

def is_critical(code, name=''):
    if code:
        for p in CRITICAL_CODES:
            if code.startswith(p): return True
    for k in CRITICAL_KW:
        if k in (name or ''): return True
    return False

def is_pharm(hospital, dept):
    return '약국' in (hospital or '') or dept in ['일반의','']

# ===== PDF 파싱 =====
def parse_basic(content):
    records = []
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            for table in (page.extract_tables() or []):
                for row in table:
                    if not row or not str(row[0] or '').strip().isdigit(): continue
                    try:
                        d=str(row[1] or '').strip().replace('\n','')
                        h=str(row[2] or '').strip().replace('\n',' ')
                        dept=str(row[3] or '').strip().replace('\n','')
                        io=str(row[4] or '').strip().replace('\n','')
                        code=str(row[5] or '').strip().replace('\n','')
                        dis=str(row[6] or '').strip().replace('\n','')
                        if not re.match(r'\d{4}-\d{2}-\d{2}',d): continue
                        # 본인부담금 파싱 (컬럼 9, 10, 11 순서: 총진료비, 보험혜택, 본인부담)
                        total_fee=0; ins_fee=0; paid_fee=0
                        try:
                            if len(row)>8: total_fee=int(re.sub(r'[^0-9]','',str(row[8] or '')) or 0)
                            if len(row)>9: ins_fee=int(re.sub(r'[^0-9]','',str(row[9] or '')) or 0)
                            if len(row)>10: paid_fee=int(re.sub(r'[^0-9]','',str(row[10] or '')) or 0)
                        except: pass
                        records.append({
                            'date':d,'hospital':h,'dept':dept,'in_out':io,
                            'code':code,'disease':dname(code,dis),
                            'is_pharmacy':is_pharm(h,dept),
                            'is_inpatient':'입원' in io,
                            'total_fee':total_fee,'ins_fee':ins_fee,'paid_fee':paid_fee
                        })
                    except: continue
    return records

def parse_detail(content):
    procs = []
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            # 테이블에서 파싱
            for table in (page.extract_tables() or []):
                for row in table:
                    if not row or not str(row[0] or '').strip().isdigit(): continue
                    try:
                        d=str(row[1] or '').strip().replace('\n','')
                        h=str(row[2] or '').strip().replace('\n',' ')
                        if not re.match(r'\d{4}-\d{2}-\d{2}',d): continue
                        # 수술명 컬럼만 검색 (3번 이후 컬럼, 날짜/병원 제외)
                        # 컬럼명("처치 및 수술") 제외하고 실제 수술명 컬럼만 검색
                        detail_cols = [str(c or '').replace('\n',' ') for c in row[3:]]
                        detail_text = ' '.join(detail_cols)
                        dc = detail_text.replace(' ','')
                        # 전체 행도 참고용으로 유지
                        full = ' '.join([str(c or '').replace('\n',' ') for c in row])
                        fc = full.replace(' ','')
                        is_s = any(k in dc for k in SURGERY_KW)
                        # NOT_SURGERY_KW는 실제 수술명 컬럼에서만 체크 (컬럼명 "처치및수술" 제외)
                        is_p = any(k in dc for k in NOT_SURGERY_KW)
                        if is_s and not is_p:
                            kw=next((k for k in SURGERY_KW if k in dc),'')
                            detail=next((str(c or '').replace('\n',' ') for c in row[3:] if c and any(k in str(c).replace(' ','') for k in SURGERY_KW)),detail_text[:120])
                            procs.append({'date':d,'hospital':h,'detail':detail,'keyword':kw,'type':'surgery'})
                        elif is_p:
                            detail=next((str(c or '').replace('\n',' ') for c in row[3:] if c and any(k in str(c).replace(' ','') for k in NOT_SURGERY_KW)),detail_text[:80])
                            procs.append({'date':d,'hospital':h,'detail':detail,'type':'procedure'})
                    except: continue
            # 텍스트에서도 파싱 (테이블 미인식 대비)
            txt=page.extract_text() or ''
            for line in txt.split('\n'):
                lc=line.replace(' ','')
                dm=re.search(r'(\d{4}-\d{2}-\d{2})',line)
                if not dm: continue
                ld=dm.group(1)
                is_s=any(k in lc for k in SURGERY_KW)
                is_p=any(k in lc for k in NOT_SURGERY_KW)
                if is_s and not is_p:
                    kw=next((k for k in SURGERY_KW if k in lc),'')
                    if not any(p.get('date')==ld and p.get('keyword')==kw for p in procs):
                        procs.append({'date':ld,'hospital':'','detail':line[:120],'keyword':kw,'type':'surgery'})
    return procs

def parse_rx(content):
    """처방조제정보 파싱
    컬럼: 순번|진료시작일|병·의원&약국|처방/조제|약품명|성분명|1회투약량|1일투여횟수|총투약일수
    """
    rxs = []
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            for table in (page.extract_tables() or []):
                for row in table:
                    if not row or not str(row[0] or '').strip().isdigit(): continue
                    if len(row) < 9: continue
                    try:
                        d=str(row[1] or '').strip().replace('\n','')
                        h=str(row[2] or '').strip().replace('\n',' ')
                        drug_raw=str(row[4] or '').strip().replace('\n',' ')
                        comp=str(row[5] or '').strip().replace('\n',' ')
                        days_raw=str(row[8] or '').strip().replace('\n','')
                        if not re.match(r'\d{4}-\d{2}-\d{2}',d): continue
                        # 약품명 정제
                        drug=re.sub(r'\(.*?\)','',drug_raw).strip()
                        drug=re.sub(r'_.*','',drug).strip()
                        if not drug or len(drug)<2: continue
                        try: days=int(re.search(r'\d+',days_raw).group())
                        except: days=0
                        rx_type = str(row[3] or '').strip().replace('\n','') if len(row) > 3 else ''
                        if days>0:
                            rxs.append({'date':d,'hospital':h,'drug_name':drug,'component':comp,'days':days,'rx_type':rx_type})
                    except: continue
    return rxs

# ===== 계산 로직 =====
def get_dates(today=None):
    today=today or date.today()
    m3=today.month-3; y3=today.year
    if m3<=0: m3+=12; y3-=1
    try: d3=date(y3,m3,today.day)
    except: d3=date(y3,m3,28)
    return today, d3, date(today.year-1,today.month,today.day), date(today.year-5,today.month,today.day)

def filter_dates(records, start, end):
    result=[]
    for r in records:
        try:
            if start<=date.fromisoformat(r['date'])<=end: result.append(r)
        except: pass
    return result


def calc_cost_stats(records):
    """연도별/질병별 본인부담금 계산"""
    from collections import defaultdict
    year_data = defaultdict(lambda: {'total':0,'ins':0,'paid':0,'count':0})
    disease_data = defaultdict(lambda: {'total':0,'paid':0,'count':0,'code':''})
    for r in records:
        y = r['date'][:4]
        year_data[y]['total'] += r.get('total_fee',0)
        year_data[y]['ins'] += r.get('ins_fee',0)
        year_data[y]['paid'] += r.get('paid_fee',0)
        year_data[y]['count'] += 1
        key = r.get('disease') or '해당없음'
        disease_data[key]['total'] += r.get('total_fee',0)
        disease_data[key]['paid'] += r.get('paid_fee',0)
        disease_data[key]['count'] += 1
        if r.get('code') and r['code'] != '$':
            disease_data[key]['code'] = r['code']
    # 연도별 정렬
    year_sorted = {y: year_data[y] for y in sorted(year_data.keys())}
    # 질병별 내림차순 (상위 5개)
    disease_sorted = sorted(disease_data.items(), key=lambda x: x[1]['paid'], reverse=True)
    top5 = [(name, d) for name, d in disease_sorted if name != '해당없음'][:5]
    total_paid = sum(d['paid'] for d in year_data.values())
    avg_paid = total_paid // max(len(year_data), 1)
    total_count = sum(d['count'] for d in year_data.values())
    return {'year': year_sorted, 'top5': top5, 'total_paid': total_paid, 'avg_paid': avg_paid, 'total_count': total_count}

def calc_visits(records):
    """질병코드별 고유 방문일 계산 (약국 제외)"""
    groups=defaultdict(list)
    for r in records:
        if not r.get('is_pharmacy') and r.get('code'):
            groups[r['code']].append(r)
    result={}
    for code,recs in groups.items():
        dates=sorted(set(r['date'] for r in recs))
        result[code]={
            'dates':dates,'count':len(dates),
            'first':dates[0],'last':dates[-1],
            'disease':recs[0]['disease'],
            'hospitals':list(set(r['hospital'] for r in recs))
        }
    return result

def match_rx_to_disease(basic_records, rx_records, d5y, today):
    """처방기록을 기본진료정보와 날짜+병원으로 매칭해서 질병코드 연결"""
    # 날짜별 질병코드 맵 생성
    date_code_map=defaultdict(list)
    for r in basic_records:
        if not r['is_pharmacy'] and r['code']:
            rd=date.fromisoformat(r['date'])
            if d5y<=rd<=today:
                date_code_map[r['date']].append({'code':r['code'],'disease':r['disease'],'hospital':r['hospital']})

    # 처방기록에 질병코드 매칭
    matched=[]
    for rx in rx_records:
        try:
            rxd=date.fromisoformat(rx['date'])
            if not (d5y<=rxd<=today): continue
        except: continue

        # 당일 매칭
        codes=date_code_map.get(rx['date'],[])
        # 1~2일 전후 매칭 (약국은 다음날 갈 수 있음)
        if not codes:
            for delta in [1,-1,2,-2]:
                d2=(rxd+timedelta(days=delta)).isoformat()
                codes=date_code_map.get(d2,[])
                if codes: break

        if codes:
            # 가장 관련있는 코드 (첫번째)
            matched.append({**rx,'code':codes[0]['code'],'disease':codes[0]['disease']})
        else:
            matched.append({**rx,'code':'','disease':''})

    return matched

def calc_drug_by_disease(matched_rx):
    """질병코드 + 성분명 기준으로 투약일수 합산"""
    # 성분명 정규화 (소문자 첫 단어)
    def norm_comp(comp):
        if not comp: return ''
        return comp.lower().split()[0] if comp.strip() else ''

    # 처방조제 중복 제거: 같은 날 같은 성분이면 외래 우선
    deduped = []
    seen = {}
    for rx in matched_rx:
        comp_key = norm_comp(rx.get('component','')) or rx.get('drug_name','').lower()[:15]
        key = (rx['date'], comp_key)
        rx_type = rx.get('rx_type','')
        if key not in seen:
            seen[key] = rx_type
            deduped.append(rx)
        elif '처방조제' in seen[key] and '외래' in rx_type:
            deduped = [r for r in deduped if not (r['date']==rx['date'] and (norm_comp(r.get('component','')) or r.get('drug_name','').lower()[:15])==comp_key)]
            deduped.append(rx)
            seen[key] = rx_type

    groups=defaultdict(list)
    for rx in deduped:
        comp_key=norm_comp(rx.get('component',''))
        drug_key=rx.get('drug_name','').lower()[:15]
        code=rx.get('code','') or 'UNKNOWN'
        key=comp_key or drug_key
        groups[key].append(rx)

    result={}
    for comp,items in groups.items():
        # 같은 날 같은 성분 → 최대 일수만 (다른 날짜는 독립 합산)
        date_max={}
        code='UNKNOWN'
        for item in items:
            d=item['date']
            if d not in date_max or item['days']>date_max[d]:
                date_max[d]=item['days']
            # 질병코드 있으면 우선 사용
            if item.get('code') and item['code'] != 'UNKNOWN':
                code = item['code']

        total=sum(date_max.values())
        if total>=30:
            rep=items[0]
            # UNKNOWN 코드면 약품명으로 대체
            display_disease = rep.get('disease','') or rep.get('drug_name','')
            result[f"{comp}"]={
                'code': code if code != 'UNKNOWN' else '',
                'disease': display_disease,
                'drug_name':rep.get('drug_name',''),
                'component':rep.get('component',''),
                'total_days':total,
                'prescriptions':[{'date':d,'days':days} for d,days in sorted(date_max.items())]
            }
    return result

# ===== Claude API =====
def analyze(api_key, customer_name, structured, all_text):
    today_str=structured['today']
    d3_str=structured['d3']
    d1y_str=structured['d1y']
    d5y_str=structured['d5y']

    prompt=f"""당신은 보험 병력 데이터 정리 전문가입니다.
아래 구조화된 의료기록 데이터를 받아서, 보험 설계사가 고객 병력을 파악할 수 있도록
빠짐없이 상세하게 정리해주세요.

【중요 원칙】
- 당신은 고지 여부를 판단하지 않습니다
- 데이터를 최대한 빠짐없이 상세하게 정리하는 것이 목적입니다
- 설계사가 직접 판단할 수 있도록 모든 정보를 제공합니다

고객명: {customer_name}
분석기준일: {today_str}
3개월 기준일: {d3_str}
1년 기준일: {d1y_str}
5년 기준일: {d5y_str}

=== 구조화 데이터 ===
{json.dumps(structured, ensure_ascii=False, indent=2)}

=== 세부진료 원본 텍스트 (수술/시술 상세 파악용) ===
{all_text[:5000]}

【섹션별 정리 기준】

■ section1: 최근 3개월 이내 진료 기록
- records_3m의 모든 항목을 질병코드별로 묶어서 표시
- rx_3m에서 date 필드가 3개월 기준일({d3_str}) 이후인 처방약만 표시
  (최초처방일은 참고용으로만 표시, 필터링 기준은 처방 날짜 기준)
- 의학적으로 관련 있는 질병코드는 하나로 묶기
  예: AM501 + AM5422 → "경추 디스크 (M501, M5422)"
- 질병코드 표시 시 앞의 'A' 제거 (예: AM513 → M513)
- 부위가 다른 경우 반드시 분리 (경추 ≠ 요추 ≠ 무릎)
- 중요: section3에 이미 포함될 질병(5년 이내 병력)과 겹치면 section1에서 제외하고 section3에 "3개월이내진료" 고지항목 추가

■ section2: 최근 1년 이내 재검사/추가검사
- 기준: 검사 결과 이상 소견으로 추가 정밀검사를 받은 경우만 포함
- 반드시 실제 검사 행위(MRI, CT, X-ray, 혈액검사, 근전도, 초음파, 내시경, 심전도 등)가 있어야 함
- 포함 대상:
  · 1차 검사(X-ray 등) 후 다른 날 추가 정밀검사(MRI, 근전도 등) 받은 경우
  · 동일 질병으로 같은 검사를 다른 날 다시 받은 경우 (재검사)
- 제외 대상:
  · 단순 치료 통원 (물리치료, 주사치료, 드레싱 등)
  · 이상 없는 정기검사/추적관찰
  · 검사 없이 약만 처방받은 경우
- 최초 검사일이 반드시 1년 기준일({d1y_str}) 이후여야 함
- 세부진료 텍스트에서 실제 검사명 구체적으로 파악
- 질병코드 표시 시 앞의 'A' 제거

■ section3: 최근 5년 이내 병력 (질병별 상세)
- 아래 데이터 중 하나라도 해당되는 질병을 전부 포함:
  · visits_5y_7plus (통원 7회 이상)
  · visits_5y_all (통원 7회 미만이어도 투약/수술/입원 있으면 포함)
  · drug_by_disease_5y (30일 이상 투약)
  · surgeries_5y (수술)
  · inpatient_5y (입원)

- 질병 그룹핑 규칙:
  · 의학적으로 같은 부위, 같은 계열 질병코드는 하나로 묶기
    예: AL239(알레르기성접촉피부염) + AL309(피부염) → "피부염 (L239, L309)"
    예: AM501(경추간판장애) + AM5422(경추통증) → "경추 디스크 (M501, M5422)"
  · 부위가 다르면 반드시 분리 (경추 ≠ 요추, 무릎 ≠ 어깨)
  · 애매하면 분리

- 질병코드 표시 시 앞의 'A' 반드시 제거 (AM513 → M513, AL239 → L239)

- 초진일 규칙:
  · 초진일 = 기본진료정보(visits_5y_all)의 첫 방문일 기준
  · 수술일 ≠ 초진일 (수술일을 초진일로 쓰지 말 것)

- 각 질병별로 아래 정보 전부 포함:
  · 초진일, 최종진료일, 통원횟수
  · 입원 여부 (날짜/병원/일수, 없으면 "없음")
  · 수술 여부 (수술명 상세/날짜/병원/부위, 없으면 "없음")
  · 투약: 약품별로 처방이력 날짜+일수 전부 + 합산일수
    예: 알테렌투엑스정 (추간판변성치료) → 2024-01-30: 7일 / 2024-06-15: 7일 / 합계: 32일
  · 치료내역 (어떤 치료를 받았는지 구체적으로)

- 고지항목 규칙 (중요):
  · "7일이상치료": visits_5y_7plus에 있는 것만 (통원 7회 이상만, 절대 재계산 금지)
  · "30일이상투약": drug_by_disease_5y에 있는 것만
  · "입원": inpatient_5y에 있는 것
  · "수술": surgeries_5y에 있는 것
  · visits_5y_7plus에 없는 질병은 절대 "7일이상치료" 고지항목에 넣지 말 것

- 3개월 이내 진료와 5년 이내 병력이 같은 질병이면:
  · section3에만 표시하고 section1에서는 제외
  · 고지항목에 "3개월이내진료"도 추가

- 결과 정렬: 수술 또는 입원 있는 것을 맨 앞에 배치

■ section4: 약물 상시복용
- 혈압강하제, 신경안정제, 수면제, 마약성진통제 등
- 최초처방일, 최근처방일 반드시 표시
- 현재 복용 중 여부

■ section5: 11대 질병
- 암, 백혈병, 고혈압, 협심증, 심근경색, 심장판막증, 간경화, 뇌졸중, 당뇨, 에이즈, 항문질환
- 해당 있으면 초진일/최종진료일/통원횟수/투약/수술 상세 표시

반드시 순수 JSON만 반환. {{ 로 시작 }} 로 끝. 절대 ```json 붙이지 말 것.

{{
  "section1": [
    {{
      "질병명": "한글질병명 (코드1, 코드2)",
      "진료일": "YYYY-MM-DD",
      "최종진료일": "YYYY-MM-DD",
      "통원횟수": 0,
      "병원": "병원명",
      "입원": false,
      "수술": "",
      "투약": [
        {{"약품명": "약품명", "성분명": "성분명", "용도": "치료목적", "투약일수": 0, "최초처방일": "YYYY-MM-DD"}}
      ],
      "치료내역": "구체적인 치료 내용"
    }}
  ],
  "section2": [
    {{
      "질병명": "한글질병명 (코드)",
      "최초검사일": "YYYY-MM-DD",
      "추가검사일": "YYYY-MM-DD",
      "최초검사내용": "X-ray, 혈액검사 등",
      "추가검사내용": "MRI, 근전도 등",
      "구분": "추가검사 또는 재검사"
    }}
  ],
  "section3": [
    {{
      "질병명": "한글질병명 (코드1, 코드2)",
      "초진일": "YYYY-MM-DD",
      "최종진료일": "YYYY-MM-DD",
      "통원횟수": 0,
      "입원": [{{"날짜": "YYYY-MM-DD", "병원": "병원명", "일수": 0}}],
      "수술": [{{"수술명": "구체적인 수술명 및 부위", "날짜": "YYYY-MM-DD", "병원": "병원명"}}],
      "투약": [{{"약품명": "약품명", "성분명": "성분명", "용도": "치료목적", "처방이력": [{{"날짜": "YYYY-MM-DD", "일수": 0}}], "합산일수": 0}}],
      "치료내역": "구체적인 치료 내용",
      "고지항목": ["7일이상치료", "30일이상투약", "입원", "수술"] 
    }}
  ],
  "section4": [
    {{
      "약물분류": "혈압강하제",
      "약품명": "약품명",
      "성분명": "성분명",
      "최초처방일": "YYYY-MM-DD",
      "최근처방일": "YYYY-MM-DD",
      "복용중": true
    }}
  ],
  "section5": {{
    "해당목록": ["고혈압", "협심증"],
    "상세": [
      {{
        "질병명": "협심증 (AI209, AI2088)",
        "초진일": "YYYY-MM-DD",
        "최종진료일": "YYYY-MM-DD",
        "통원횟수": 0,
        "입원": [{{"날짜": "YYYY-MM-DD", "병원": "병원명", "일수": 0}}],
        "수술": [],
        "투약": [{{"약품명": "약품명", "용도": "치료목적", "합산일수": 0}}],
        "검사내용": "심초음파, 흉부CT 등"
      }}
    ]
  }},
  "요약": ["핵심 병력 요약 1", "핵심 병력 요약 2"]
}}"""

    client=anthropic.Anthropic(api_key=api_key)
    msg=client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=16000,
        messages=[{"role":"user","content":prompt}]
    )
    raw=msg.content[0].text.strip()
    if raw.startswith('```'):
        raw=re.sub(r'^```[a-zA-Z]*\n?','',raw)
        raw=re.sub(r'\n?```$','',raw).strip()
    js=raw.find('{'); je=raw.rfind('}')
    if js!=-1 and je!=-1: raw=raw[js:je+1]
    return json.loads(raw)


# ===== 렌더링 =====

def render(r, customer_name, today_str, cost_stats=None):
    s1=r.get('section1',[])
    s2=r.get('section2',[])
    s3=r.get('section3',[])
    s4=r.get('section4',[])
    s5=r.get('section5',{})
    summary=r.get('요약',[])

    # 상단 배너
    st.markdown(f"""
    <div class="top-banner">
        <div class="banner-title">🏥 알릴 의무 고지사항 확인서</div>
        <div class="banner-customer">👤 {customer_name} 고객님</div>
        <div class="banner-sub">분석일: {today_str} · 리치앤아이 · 글로벌금융판매</div>
    </div>
    """, unsafe_allow_html=True)

    def disease_box(title, lines, color='#1a2744'):
        """심플 병력 박스 렌더링"""
        lines_html = ''.join([f'<div style="font-size:13px;color:#374151;padding:3px 0;border-bottom:1px solid #f3f4f6;">{l}</div>' for l in lines if l])
        st.markdown(f"""
        <div style="border:1.5px solid #e8eaf0;border-radius:10px;margin-bottom:10px;overflow:hidden;">
            <div style="background:{color};padding:10px 14px;">
                <div style="color:white;font-size:14px;font-weight:800;">{title}</div>
            </div>
            <div style="padding:10px 14px;background:white;">{lines_html}</div>
        </div>""", unsafe_allow_html=True)

    # ===== 섹션 1: 최근 3개월 이내 =====
    if s1:
        st.markdown('<div class="sec-title"><span class="sec-num">1</span>최근 3개월 이내 진료 기록</div>', unsafe_allow_html=True)
        for item in s1:
            if not isinstance(item, dict): continue
            title = item.get('질병명','')
            lines = []
            lines.append(f"📅 진료일: {item.get('진료일','')} | 최종: {item.get('최종진료일','')} | 통원 {item.get('통원횟수',0)}회")
            lines.append(f"🏥 병원: {item.get('병원','')}")
            if item.get('입원'): lines.append(f"🛏️ 입원: {item.get('입원')}")
            if item.get('수술'): lines.append(f"✂️ 수술: {item.get('수술')}")
            투약 = item.get('투약',[])
            if 투약:
                lines.append('💊 투약:')
                for d in 투약:
                    if not isinstance(d, dict): continue
                    first = f" (최초처방: {d.get('최초처방일','')})" if d.get('최초처방일') else ''
                    lines.append(f"　· {d.get('약품명','')} ({d.get('성분명','')}) — {d.get('용도','')} — {d.get('투약일수',0)}일{first}")
            if item.get('치료내역'): lines.append(f"🩺 치료: {item.get('치료내역','')}")
            disease_box(title, lines)
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ===== 섹션 2: 1년 이내 재검사/추가검사 =====
    if s2:
        st.markdown('<div class="sec-title"><span class="sec-num">2</span>최근 1년 이내 재검사 / 추가검사</div>', unsafe_allow_html=True)
        for item in s2:
            if not isinstance(item, dict): continue
            구분 = item.get('구분','추가검사')
            title = f"{item.get('질병명','')} [{구분}]"
            lines = []
            lines.append(f"📅 최초검사일: {item.get('최초검사일','')} | 추가검사일: {item.get('추가검사일','')}")
            if item.get('최초검사내용'): lines.append(f"🔍 최초: {item.get('최초검사내용','')}")
            if item.get('추가검사내용'): lines.append(f"🔎 추가: {item.get('추가검사내용','')}")
            disease_box(title, lines, '#0891b2')
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ===== 섹션 3: 5년 이내 병력 (수술/입원 먼저) =====
    if s3:
        st.markdown('<div class="sec-title"><span class="sec-num">3</span>최근 5년 이내 병력</div>', unsafe_allow_html=True)
        # 수술 또는 입원 있는 것 먼저, 나머지는 뒤에
        def has_inop(item):
            if not isinstance(item, dict): return False
            고지 = item.get('고지항목',[])
            return '입원' in 고지 or '수술' in 고지
        s3_sorted = sorted(s3, key=lambda x: (0 if has_inop(x) else 1))
        for item in s3_sorted:
            if not isinstance(item, dict): continue
            고지항목 = item.get('고지항목',[])
            고지str = ' · '.join([f'⚠️{g}' for g in 고지항목]) if 고지항목 else ''
            title = f"{item.get('질병명','')}{'  '+고지str if 고지str else ''}"
            lines = []
            lines.append(f"📅 초진: {item.get('초진일','')} | 최종: {item.get('최종진료일','')} | 통원 {item.get('통원횟수',0)}회")

            # 입원
            입원목록 = item.get('입원',[])
            if 입원목록:
                for h in 입원목록:
                    if isinstance(h, dict):
                        lines.append(f"🛏️ 입원: {h.get('날짜','')} · {h.get('병원','')} · {h.get('일수',0)}일")
                    elif h:
                        lines.append(f"🛏️ 입원: {h}")
            else:
                lines.append("🛏️ 입원: 없음")

            # 수술
            수술목록 = item.get('수술',[])
            if 수술목록:
                for s in 수술목록:
                    if isinstance(s, dict):
                        lines.append(f"✂️ 수술: {s.get('수술명','')} · {s.get('날짜','')} · {s.get('병원','')}")
                    elif s:
                        lines.append(f"✂️ 수술: {s}")
            else:
                lines.append("✂️ 수술: 없음")

            # 투약
            투약목록 = item.get('투약',[])
            if 투약목록:
                lines.append('💊 투약:')
                for d in 투약목록:
                    if not isinstance(d, dict): continue
                    lines.append(f"　· {d.get('약품명','')} ({d.get('성분명','')}) — {d.get('용도','')}")
                    처방이력 = d.get('처방이력',[])
                    if 처방이력:
                        for p in 처방이력:
                            if isinstance(p, dict):
                                lines.append(f"　　{p.get('날짜','')}: {p.get('일수',0)}일")
                    lines.append(f"　　합계: {d.get('합산일수',0)}일")

            # 치료내역
            if item.get('치료내역'):
                lines.append(f"🩺 치료: {item.get('치료내역','')}")

            color = '#dc2626' if any(k in 고지항목 for k in ['입원','수술']) else '#1a2744'
            disease_box(title, lines, color)
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ===== 섹션 4: 약물 상시복용 =====
    if s4:
        st.markdown('<div class="sec-title"><span class="sec-num">4</span>약물 상시복용</div>', unsafe_allow_html=True)
        for item in s4:
            if not isinstance(item, dict): continue
            복용상태 = '현재 복용 중 🔴' if item.get('복용중') else '과거 복용'
            title = f"💊 {item.get('약물분류','')} — {item.get('약품명','')}"
            lines = []
            lines.append(f"성분명: {item.get('성분명','')}")
            lines.append(f"최초처방일: {item.get('최초처방일','')} | 최근처방일: {item.get('최근처방일','')}")
            lines.append(f"복용 상태: {복용상태}")
            disease_box(title, lines, '#7c3aed')
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ===== 섹션 5: 11대 질병 =====
    st.markdown('<div class="sec-title"><span class="sec-num">5</span>최근 5년 이내 11대 질병</div>', unsafe_allow_html=True)
    diseases_11=['암','백혈병','고혈압','협심증','심근경색','심장판막증','간경화증','뇌졸중','당뇨','에이즈HIV','항문질환']
    해당목록 = s5.get('해당목록',[]) if isinstance(s5, dict) else []
    미해당 = [d for d in diseases_11 if d not in 해당목록]

    if 해당목록:
        st.markdown(f"<div style='margin-bottom:8px;'><b style='color:#dc2626;font-size:14px;'>⚠️ 해당 있음:</b></div>", unsafe_allow_html=True)
        st.markdown('<div class="d5-row">'+''.join([f'<span class="d5-bad">⚠️ {d}</span>' for d in 해당목록])+'</div>', unsafe_allow_html=True)
        상세목록 = s5.get('상세',[]) if isinstance(s5, dict) else []
        for item in 상세목록:
            if not isinstance(item, dict): continue
            title = item.get('질병명','')
            lines = []
            lines.append(f"📅 초진: {item.get('초진일','')} | 최종: {item.get('최종진료일','')} | 통원 {item.get('통원횟수',0)}회")
            for h in item.get('입원',[]):
                if isinstance(h, dict): lines.append(f"🛏️ 입원: {h.get('날짜','')} · {h.get('병원','')} · {h.get('일수',0)}일")
            for s in item.get('수술',[]):
                if isinstance(s, dict): lines.append(f"✂️ 수술: {s.get('수술명','')}")
                elif s: lines.append(f"✂️ 수술: {s}")
            for d in item.get('투약',[]):
                if isinstance(d, dict): lines.append(f"💊 {d.get('약품명','')} ({d.get('용도','')}) — {d.get('합산일수',0)}일")
            if item.get('검사내용'): lines.append(f"🔬 검사: {item.get('검사내용','')}")
            disease_box(title, lines, '#dc2626')

    st.markdown(f"<div style='margin:10px 0 6px;'><b style='color:#16a34a;font-size:14px;'>✅ 해당 없음:</b></div>", unsafe_allow_html=True)
    st.markdown('<div class="d5-row">'+''.join([f'<span class="d5-ok">✅ {d}</span>' for d in 미해당])+'</div>', unsafe_allow_html=True)

    # 인쇄 버튼 (Streamlit 방식 - React 충돌 방지)
    st.markdown("""
    <div class="no-print" style="text-align:right;margin:16px 0;">
        <button id="print-btn" style="background:#1a2744;color:#c9a84c;border:none;border-radius:10px;padding:10px 24px;font-size:14px;font-weight:700;cursor:pointer;font-family:inherit;">
            🖨️ 인쇄 / PDF 저장
        </button>
    </div>
    <script>
        setTimeout(function() {
            var btn = document.getElementById('print-btn');
            if (btn) btn.addEventListener('click', function() { window.print(); });
        }, 500);
    </script>
    """, unsafe_allow_html=True)

    # 요약
    if summary:
        summary_html=''.join([f'<div class="summary-item"><span class="summary-arrow">▶</span><span class="summary-text">{s}</span></div>' for s in summary])
        st.markdown(f'<div class="summary-box"><div class="summary-title">📋 핵심 병력 요약</div>{summary_html}</div>', unsafe_allow_html=True)


    # ===== 의료비 섹션 (인쇄 포함) =====
    if cost_stats:
        render_cost(cost_stats)


def render_cost(stats):
    """연도별/질병별 의료비 렌더링"""
    if not stats: return
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    year_data = stats['year']
    top5 = stats['top5']
    total_paid = stats['total_paid']
    avg_paid = stats['avg_paid']
    total_count = stats['total_count']

    # 요약 박스
    st.markdown(f"""
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:18px;">
        <div class="stat-box"><div class="stat-label">총 본인부담금</div><div class="stat-value">{total_paid:,}원</div></div>
        <div class="stat-box"><div class="stat-label">연평균 본인부담금</div><div class="stat-value stat-blue">{avg_paid:,}원</div></div>
        <div class="stat-box"><div class="stat-label">총 진료 건수</div><div class="stat-value">{total_count}건</div></div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="sec-title"><span class="sec-num">6</span>연도별 본인부담 의료비</div>', unsafe_allow_html=True)
        for y, d in year_data.items():
            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border:1px solid #e8eaf0;border-radius:10px;margin-bottom:8px;background:white;">
                <div>
                    <div style="font-size:15px;font-weight:800;color:#1a2744;">{y}년</div>
                    <div style="font-size:12px;color:#9ca3af;margin-top:2px;">{d['count']}건 진료</div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:16px;font-weight:900;color:#1D9E75;">{d['paid']:,}원</div>
                    <div style="font-size:11px;color:#9ca3af;">보험혜택 {d['ins']:,}원</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="sec-title"><span class="sec-num">7</span>질병별 의료비 상위 5개</div>', unsafe_allow_html=True)
        colors = ['#E24B4A','#378ADD','#1D9E75','#BA7517','#534AB7']
        for i, (name, d) in enumerate(top5):
            c = colors[i % len(colors)]
            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border:1px solid #e8eaf0;border-radius:10px;margin-bottom:8px;background:white;">
                <div style="display:flex;align-items:center;gap:10px;">
                    <div style="width:22px;height:22px;border-radius:50%;background:{c};color:white;font-size:11px;font-weight:900;display:flex;align-items:center;justify-content:center;flex-shrink:0;">{i+1}</div>
                    <div>
                        <div style="font-size:13px;font-weight:800;color:#1a2744;">{name}</div>
                        <div style="font-size:11px;color:#9ca3af;">{d['code']} · {d['count']}회</div>
                    </div>
                </div>
                <div style="font-size:15px;font-weight:900;color:#1a2744;">{d['paid']:,}원</div>
            </div>
            """, unsafe_allow_html=True)

def make_pdf(r, customer_name, today_str):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os

    buf=BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=15*mm,leftMargin=15*mm,topMargin=15*mm,bottomMargin=15*mm)

    fn='Helvetica'
    import os as _os
    _base = _os.path.dirname(_os.path.abspath(__file__))
    font_paths = [
        _os.path.join(_base, 'NanumGothic.ttf'),
        _os.path.join(_base, 'fonts', 'NanumGothic.ttf'),
        '/usr/share/fonts/truetype/nanum/NanumGothic.ttf',
        '/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf',
        'C:/Windows/Fonts/malgun.ttf',
        'C:/Windows/Fonts/NanumGothic.ttf',
    ]
    for fp in font_paths:
        try:
            if _os.path.exists(fp):
                pdfmetrics.registerFont(TTFont('K', fp))
                fn = 'K'
                break
        except: pass
    if False:
        try:
            url = 'https://github.com/googlefonts/nanum-fonts/raw/main/NanumGothic/NanumGothic-Regular.ttf'
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.ttf')
            urllib.request.urlretrieve(url, tmp.name)
            pdfmetrics.registerFont(TTFont('K', tmp.name))
            fn = 'K'
        except:
            pass

    def ps(n,sz,c='#1a2744',sb=0,sa=3):
        return ParagraphStyle(n,fontName=fn,fontSize=sz,textColor=colors.HexColor(c),spaceBefore=sb,spaceAfter=sa)

    story=[]
    i1=r.get('item1',{}); i2=r.get('item2',{}); i3=r.get('item3',{})
    i4=r.get('item4',{}); i5=r.get('item5',{}); signal=r.get('signal',{})

    story.append(Paragraph(f"알릴 의무 고지사항 확인서 — {customer_name} 고객님",ps('t',16,sa=2)))
    story.append(Paragraph(f"분석일: {today_str}  |  리치앤아이 · 글로벌금융판매",ps('s',10,'#6b7280',sa=4)))
    sig=signal.get('status','green')
    sig_t={'red':'🔴 인수 거절 가능성','yellow':'🟡 조건부 가입 가능','green':'🟢 일반심사 가능'}.get(sig,'🟢 일반심사 가능')
    story.append(Paragraph(f"가입 가능 여부: {sig_t}",ps('sg',11,sa=6)))
    story.append(HRFlowable(width="100%",thickness=3,color=colors.HexColor('#c9a84c'),spaceAfter=8))

    def sec(title): story.append(Paragraph(title,ps('h',12,'#1a2744',sb=10,sa=4)))
    def row(txt,c='#374151'): story.append(Paragraph(txt,ps('n',10,c,sa=2)))

    # 1번 - 해당 있는 항목만
    items1=[(k,i1.get(k,{})) for k in ["질병확정진단","질병의심소견","치료","입원","수술","투약"] if i1.get(k,{}).get('해당')]
    if items1:
        sec("1. 최근 3개월 이내 의료행위")
        for key,data in items1:
            row(f"  [{key}]")
            for item in data.get('목록',[]):
                if key=="투약": row(f"    · {item.get('약품명','')} ({item.get('성분명','')}) — {item.get('용도','')} — {item.get('투약일수',0)}일")
                elif key=="수술": row(f"    · ✂ {item.get('수술명','')} — {item.get('날짜','')} — {item.get('병원','')}","#dc2626")
                else: row(f"    · {item.get('질병','')} ({item.get('코드','')}) — {item.get('날짜','')} — {item.get('병원','')} {'— '+item.get('내용','') if item.get('내용') else ''}")

    # 2번
    items2=[(k,i2.get(k,{})) for k in ["마약성진통제","혈압강하제","신경안정제","수면제","각성제","진통제"] if i2.get(k,{}).get('해당')]
    if items2:
        sec("2. 최근 3개월 약물 상시복용")
        for key,data in items2:
            row(f"  [{key}]")
            for item in data.get('목록',[]): row(f"    · {item.get('약물명','')} ({item.get('성분명','')}) — {'복용 중' if item.get('복용중') else '과거 복용'} — {item.get('복용시작','')}")

    # 3번
    if i3.get('해당'):
        sec("3. 최근 1년 이내 재검사/추가검사")
        for d in i3.get('목록',[]):
            row(f"  [{d.get('질병','')} ({d.get('코드','')})]")
            row(f"    · 최초: {d.get('최초진료일','')} | 마지막: {d.get('마지막진료일','')} | 통원: {d.get('총방문횟수',0)}회")
            if d.get('검사내용'): row(f"    · 검사내용: {d['검사내용']}","#92400e")
            if d.get('고지사유'): row(f"    · 고지사유: {d['고지사유']}","#1a2744")
            if d.get('수술명'): row(f"    · 수술: {', '.join(d['수술명'])}","#dc2626")

    # 4번 - 해당 있는 것만
    items4=[(k,i4.get(k,{})) for k in ["입원","수술","치료7일","투약30일"] if i4.get(k,{}).get('해당')]
    lmap={"입원":"입원","수술":"수술(제왕절개 포함)","치료7일":"계속하여 7일 이상 치료","투약30일":"계속하여 30일 이상 투약"}
    if items4:
        sec("4. 최근 5년 이내 의료행위")
        for key,data in items4:
            row(f"  [{lmap[key]}]")
            for item in data.get('목록',[]):
                if isinstance(item,dict):
                    if key=="수술": row(f"    · ✂ {item.get('수술명','')} — {item.get('질병','')} — {item.get('날짜','')} — {item.get('병원','')}","#dc2626")
                    elif key=="투약30일":
                        row(f"    · {item.get('약품명','')} ({item.get('성분명','')}) — {item.get('용도','')}")
                        for p in item.get('처방내역',[]): row(f"      {p.get('날짜','')} : {p.get('투약일수',0)}일","#6b7280")
                        row(f"      합계: {item.get('합산일수',0)}일","#dc2626")
                    elif key=="치료7일": row(f"    · {item.get('질병','')} ({item.get('코드','')}) — {item.get('최초진료일','')}~{item.get('마지막진료일','')} — {item.get('총방문횟수',0)}회")
                    elif key=="입원": row(f"    · {item.get('질병','')} — {item.get('입원일','')}~{item.get('퇴원일','')} — {item.get('병원','')} — {item.get('일수',0)}일")

    # 5번
    sec("5. 최근 5년 이내 10대 질병")
    diseases_5=['암','백혈병','고혈압','협심증','심근경색','심장판막증','간경화증','뇌졸중','당뇨','에이즈HIV','항문질환']
    d5map=i5.get('목록',{})
    bad=[d for d in diseases_5 if '해당없음' not in str(d5map.get(d,'해당없음')) and '없음' not in str(d5map.get(d,'해당없음'))]
    ok=[d for d in diseases_5 if d not in bad]
    if bad: row(f"  ⚠ 해당 있음: {', '.join(bad)}","#dc2626")
    row(f"  ✓ 해당 없음: {', '.join(ok)}","#16a34a")

    summary=r.get('요약',[])
    if summary:
        story.append(HRFlowable(width="100%",thickness=2,color=colors.HexColor('#c9a84c'),spaceBefore=10,spaceAfter=6))
        story.append(Paragraph("고지 필요 핵심 요약",ps('sh',12,sb=0,sa=5)))
        for s in summary: row(f"▶ {s}")

    doc.build(story)
    buf.seek(0)
    return buf


# ===== 메인 =====
if 'result' not in st.session_state: st.session_state.result=None
if 'customer' not in st.session_state: st.session_state.customer=""
if 'today_str' not in st.session_state: st.session_state.today_str=""
if 'basic_records' not in st.session_state: st.session_state.basic_records=[]
if 'cost_stats' not in st.session_state: st.session_state.cost_stats=None

with st.sidebar:
    st.markdown("### ⚙️ 설정")
    api_key=st.text_input("Claude API Key",type="password",placeholder="sk-ant-...")

    # URL 파라미터에서 고객 정보 읽기
    url_uid, url_cid, url_name = get_url_params()
    if url_uid and url_cid:
        st.markdown('<div style="background:#f0fdf4;border:1px solid #86efac;border-radius:6px;padding:6px 10px;font-size:12px;color:#166534;margin-bottom:4px;">✅ 리치앤아이 고객 연동됨</div>', unsafe_allow_html=True)

    customer_name=st.text_input("고객 이름", value=url_name if url_name else "", placeholder="홍길동")
    st.markdown("### 📄 PDF 업로드")
    pdf_b=st.file_uploader("📋 기본진료정보",type="pdf",key="p1")
    pdf_d=st.file_uploader("🔬 세부진료정보",type="pdf",key="p2")
    pdf_r=st.file_uploader("💊 처방조제정보",type="pdf",key="p3")
    uploaded=[(f,l) for f,l in [(pdf_b,"기본진료정보"),(pdf_d,"세부진료정보"),(pdf_r,"처방조제정보")] if f]
    st.markdown(f"**{len(uploaded)}/3** 파일 업로드됨")
    btn=st.button("🔍 AI 분석 시작",type="primary",disabled=(not api_key or not customer_name or not pdf_b),use_container_width=True)

    if st.session_state.result:
        st.markdown("---")
        st.markdown("### 💾 PDF 저장")
        try:
            pb=make_pdf(st.session_state.result,st.session_state.customer,st.session_state.today_str)
            st.download_button("📋 전체 상세 보고서",data=pb,
                file_name=f"상세보고서_{st.session_state.customer}_{date.today().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",use_container_width=True)
        except Exception as e: st.error(f"PDF 오류: {e}")
        try:
            cost=st.session_state.cost_stats
            pb2=make_pdf_summary(st.session_state.result,st.session_state.customer,st.session_state.today_str,cost)
            st.download_button("👤 고객용 요약본",data=pb2,
                file_name=f"고객요약_{st.session_state.customer}_{date.today().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",use_container_width=True)
        except Exception as e: st.error(f"요약본 오류: {e}")

        # 리치앤아이 연동 저장 버튼
        if url_uid and url_cid:
            st.markdown("---")
            st.markdown("### 🔗 리치앤아이 저장")
            if st.button("💾 병력사항 탭에 저장", use_container_width=True, type="primary"):
                with st.spinner("저장 중..."):
                    ok = save_to_firestore(
                        url_uid, url_cid,
                        st.session_state.result,
                        st.session_state.customer,
                        st.session_state.today_str,
                        st.session_state.cost_stats
                    )
                    if ok:
                        st.success("✅ 저장완료! 리치앤아이 병력사항 탭에서 확인하세요.")
                    else:
                        st.error("저장 실패. 다시 시도해주세요.")

if btn:
    if not api_key.startswith('sk-ant-'):
        st.error("올바른 Claude API 키를 입력해주세요.")
    else:
        today,d3,d1y,d5y=get_dates()
        today_str=today.strftime('%Y년 %m월 %d일')
        st.markdown("### 📄 추출 현황")

        basic=[]; detail=[]; rx=[]; all_text=[]

        if pdf_b:
            c=pdf_b.read()
            basic=parse_basic(c)
            st.markdown(f'<div class="extract-box"><span class="extract-label">✅ 기본진료정보</span><span class="extract-count">{len(basic)}개 레코드</span></div>',unsafe_allow_html=True)
            with pdfplumber.open(BytesIO(c)) as pdf:
                for pg in pdf.pages:
                    t=pg.extract_text()
                    if t: all_text.append(t[:2000])

        if pdf_d:
            c=pdf_d.read()
            detail=parse_detail(c)
            surgs=len([p for p in detail if p['type']=='surgery'])
            st.markdown(f'<div class="extract-box"><span class="extract-label">✅ 세부진료정보</span><span class="extract-count">수술 {surgs}건 감지</span></div>',unsafe_allow_html=True)
            with pdfplumber.open(BytesIO(c)) as pdf:
                for pg in pdf.pages:
                    t=pg.extract_text()
                    if t: all_text.append(t[:2000])

        if pdf_r:
            c=pdf_r.read()
            rx=parse_rx(c)
            st.markdown(f'<div class="extract-box"><span class="extract-label">✅ 처방조제정보</span><span class="extract-count">{len(rx)}개 처방</span></div>',unsafe_allow_html=True)

        # 날짜 기준 계산
        r3m=filter_dates(basic,d3,today)
        r1y=filter_dates(basic,d1y,today)
        r5y=filter_dates(basic,d5y,today)

        visits1y=calc_visits(r1y)
        visits5y=calc_visits(r5y)

        # 처방기록 + 기본진료정보 매칭
        matched_rx=match_rx_to_disease(basic,rx,d5y,today)
        drug5y=calc_drug_by_disease(matched_rx)

        surgs5y=[p for p in filter_dates(detail,d5y,today) if p['type']=='surgery']
        procs5y=[p for p in filter_dates(detail,d5y,today) if p['type']=='procedure']
        inpat5y=[r for r in r5y if r.get('is_inpatient')]

        # 3개월 이내 처방약 (최초처방일 포함)
        rx_3m_list=[]
        for rx_item in rx:
            if rx_item.get('date','') >= d3.isoformat():
                # 해당 약품의 최초 처방일 찾기
                first_rx = min((r['date'] for r in rx if r.get('drug_name')==rx_item.get('drug_name')), default=rx_item['date'])
                rx_3m_list.append({
                    'date':rx_item['date'],
                    'drug_name':rx_item['drug_name'],
                    'component':rx_item['component'],
                    'days':rx_item['days'],
                    'hospital':rx_item['hospital'],
                    'first_prescription':first_rx
                })

        structured={
            'today':today_str,
            'd3':d3.isoformat(),'d1y':d1y.isoformat(),'d5y':d5y.isoformat(),
            # 3개월 이내 진료 (약국 제외, 전체)
            'records_3m':[{
                'date':r['date'],'hospital':r['hospital'],
                'code':r['code'],'disease':r['disease'],
                'in_out':r.get('in_out','')
            } for r in r3m if not r['is_pharmacy']],
            # 3개월 이내 처방약 (최초처방일 포함)
            'rx_3m': rx_3m_list,
            # 1년 이내 2회 이상 방문 (재검사 판단용)
            'visits_1y_2plus':{
                code:{'disease':v['disease'],'count':v['count'],'first':v['first'],'last':v['last'],'hospitals':v['hospitals'][:3]}
                for code,v in visits1y.items() if v['count']>=2
            },
            # 1년 이내 전체 방문
            'visits_1y_all':{
                code:{'disease':v['disease'],'count':v['count'],'first':v['first'],'last':v['last']}
                for code,v in visits1y.items()
            },
            # 5년 이내 7회 이상 방문 (7일이상 치료 판단용)
            'visits_5y_7plus':{
                code:{'disease':v['disease'],'count':v['count'],'first':v['first'],'last':v['last']}
                for code,v in visits5y.items() if v['count']>=7
            },
            # 5년 이내 전체 방문 (표시용 - 7회 미만 포함, 단 7일이상치료 고지항목엔 넣지 않음)
            'visits_5y_all':{
                code:{'disease':v['disease'],'count':v['count'],'first':v['first'],'last':v['last']}
                for code,v in visits5y.items()
            },
            # 5년 이내 30일 이상 투약
            'drug_by_disease_5y':{
                k:{'code':v['code'],'disease':v['disease'],'drug_name':v['drug_name'],
                   'component':v['component'],'total_days':v['total_days'],
                   'prescriptions':v['prescriptions']}
                for k,v in drug5y.items()
            },
            # 5년 이내 수술 (상세 포함)
            'surgeries_5y':[{'date':p['date'],'hospital':p['hospital'],'keyword':p['keyword'],'detail':p['detail'][:120]} for p in surgs5y[:20]],
            # 5년 이내 시술/처치
            'procedures_5y':[{'date':p['date'],'hospital':p['hospital'],'detail':p['detail'][:80]} for p in procs5y[:30]],
            # 5년 이내 입원
            'inpatient_5y':[{'date':r['date'],'hospital':r['hospital'],'disease':r['disease'],'in_out':r.get('in_out','')} for r in inpat5y],
        }

        with st.spinner("🤖 Claude AI 분석 중... (30초~1분 소요)"):
            try:
                result=analyze(api_key,customer_name,structured,'\n'.join(all_text[:5]))
                st.session_state.result=result
                st.session_state.customer=customer_name
                st.session_state.today_str=today_str
                st.session_state.basic_records=basic
                st.session_state.cost_stats=calc_cost_stats(basic)
                st.rerun()
            except json.JSONDecodeError:
                st.error("JSON 파싱 오류. 다시 시도해주세요.")
            except Exception as e:
                st.error(f"분석 오류: {str(e)}")

if st.session_state.result:
    render(st.session_state.result,st.session_state.customer,st.session_state.today_str,st.session_state.cost_stats)
else:
    st.info("왼쪽에서 API 키, 고객 이름, PDF 업로드 후 분석 버튼을 눌러주세요.")
    st.markdown("""
    **분석 항목:**
    - **1번**: 최근 3개월 — 질병확정진단/질병의심소견/치료/입원/수술/투약
    - **2번**: 최근 3개월 — 약물 상시복용
    - **3번**: 최근 1년 — 재검사/추가검사 (검사내용+고지사유 포함)
    - **4번**: 최근 5년 — 입원/수술/7일이상치료/30일이상투약
    - **5번**: 최근 5년 — 11대 질병
    """)
