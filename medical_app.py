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
        doc_ref.set({
            'result': result,
            'customerName': customer_name,
            'analyzedAt': fs.SERVER_TIMESTAMP,
            'today_str': today_str,
            'cost_stats': {
                'total_paid': cost_stats.get('total_paid', 0) if cost_stats else 0,
                'avg_paid': cost_stats.get('avg_paid', 0) if cost_stats else 0,
                'total_count': cost_stats.get('total_count', 0) if cost_stats else 0,
            } if cost_stats else {}
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
    .main .block-container { padding: 0 !important; max-width: 100% !important; }
    @page { margin: 10mm; size: A4; }
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

SURGERY_KW = ['절제술','적출술','봉합술','발치술','임플란트식립','치조골절제','편도절제술',
    '충수절제술','용종절제술','관절경','복강경','절개배농','낭종제거술','피부절제술',
    '피판술','치핵절제술','자궁절제술','제왕절개','종양절제','산립종절개','피부양성종양적출']
NOT_SURGERY_KW = ['단순처치','염증성처치','드레싱','창상처치','신경차단','관절천자',
    '관절강내주사','히알루론산','스테로이드주사','물리치료','표층열','심층열',
    '초음파치료','전기자극','견인치료','스케일링','치주소파','치근활택',
    '충치치료','신경치료','크라운','보철','주사치료','재활저출력','간헐적견인','경피적전기']
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
                        full=' '.join([str(c or '').replace('\n',' ') for c in row])
                        fc=full.replace(' ','')
                        is_s=any(k in fc for k in SURGERY_KW)
                        is_p=any(k in fc for k in NOT_SURGERY_KW)
                        if is_s and not is_p:
                            kw=next((k for k in SURGERY_KW if k in fc),'')
                            detail=next((str(c or '').replace('\n',' ') for c in row if c and any(k in str(c).replace(' ','') for k in SURGERY_KW)),full[:80])
                            procs.append({'date':d,'hospital':h,'detail':detail,'keyword':kw,'type':'surgery'})
                        elif is_p:
                            detail=next((str(c or '').replace('\n',' ') for c in row if c and any(k in str(c).replace(' ','') for k in NOT_SURGERY_KW)),full[:80])
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
                        procs.append({'date':ld,'hospital':'','detail':line[:100],'keyword':kw,'type':'surgery'})
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
    # 약 이름에서 잡다한 글자(정, 캡슐, 공백)를 다 지우고 글자만 비교
    def clean_k(text): return re.sub(r'[^가-힣a-zA-Z0-9]', '', str(text or '')).lower()

    groups = defaultdict(list)
    for rx in matched_rx:
        # 성분명 우선, 없으면 약 이름 앞 5글자로 묶음
        key = clean_k(rx.get('component')) if rx.get('component') else clean_k(rx.get('drug_name'))[:5]
        groups[key].append(rx)

    result = {}
    for key, items in groups.items():
        # 같은 날 중복 처방은 하루치만 계산 (정확한 합산)
        date_map = {it['date']: it['days'] for it in items}
        total = sum(date_map.values())
        
        # 20일 이상이면 누락 방지를 위해 AI에게 전달
        if total >= 20: 
            rep = items[0]
            result[key] = {
                'code': rep.get('code', ''),
                'disease': rep.get('disease', '관련 질환 확인 필요'),
                'drug_name': rep.get('drug_name', ''),
                'total_days': total,
                'prescriptions': [{'date':d, 'days':v} for d,v in sorted(date_map.items())]
            }
    return result

# ===== Claude API =====
def analyze(api_key, customer_name, structured, all_text):
    today_str=structured['today']
    d3_str=structured['d3']
    d1y_str=structured['d1y']
    d5y_str=structured['d5y']

    # ── 시스템 프롬프트 (심사관 역할) ──
    system_prompt = """# Role: 대용량 데이터 전용 보험 고지의무 분석 엔진 (Expert Underwriter)
너는 260페이지 이상의 방대한 의무기록을 분석하여 보험 고지사항을 추출하는 전문가다. 데이터 과부하로 인한 출력 끊김을 방지하고, 보험사의 고지의무 위반 조사를 원천 차단하기 위해 다음 '심사관 관점의 통합 로직'을 절대 준수하라.

# 1. 수술 및 시술 정밀 판별 (Surgical Detection - CRITICAL)
다음 항목은 '수술' 명칭이 없어도 반드시 [수술/시술]로 분류하고 개별 고지하라:
- 치과 수술 분리: [발치술]과 [임플란트 식립]은 별개의 수술이다. 동일 부위라도 각각 독립된 항목으로 추출하라.
- 숨겨진 수술: 성형술(골시멘트 주입 포함), 소작술(약물/레이저), 용종 절제(SNARE 사용), 조직검사(FORCEPS 사용/생검), 봉합, 배농, 천자.
- 간접 증거: 세부내역서상 '마취료', '수술실 사용료', '재료대(Fixture, Snare 등)'가 확인되면 관련 상병을 수술로 판정하라.

# 2. 신체 부위 및 원인별 통합 로직 (Anatomical Grouping)
보험사의 '동일 원인 합산' 기준에 따라 다음을 실행하라:
- 부위별 통합: 코드가 미세하게 다르거나(AM759, AM751), 병원 종류(한방 B코드, 양방 A코드)가 달라도 '동일 부위(어깨, 발목, 허리 등)' 치료라면 하나의 질병군으로 묶어 [총 통원 횟수]를 합산하라.
- 위장약 필터링: 진통제 등과 세트로 처방된 위장약은 독립 질환이 아닌 주상병(근골격계 등)의 보조 치료로 묶어라.
- 질병코드 정제: 앞의 알파벳(A, B, C)은 제거하고 코드 앞 3자리로 그룹화하라. '$' 약국 기록은 당일 방문 병원 코드를 적용하라.

# 3. 만성 질환 '뿌리' 역추적 (Chronic Disease Rooting)
- 실질 진단일 찾기: 특정 상병코드(I20 등)가 찍히기 전이라도, 해당 질환의 전용 핵심 약물(예: 니트로글리세린, 항혈전제, 고지혈증제 등)이 최초 처방된 날을 '실질적 치료 시작일'로 간주하여 타임라인을 작성하라.

# 4. 고지 대상 우선순위 및 필터링
아래 기준에 부합하지 않는 단순 진료는 생략하여 토큰을 절약하라:
1) [3개월 이내] 진단, 의심소견, 입원, 수술, 투약 전체
2) [5년 이내] 11대 중대질환(암, 뇌졸중, 당뇨, 혈압, 협심증 등) 기록 전체
3) [5년 이내] 입원 및 모든 수술/시술 (발치, 용종절제 포함)
4) [5년 이내] 통합 질병군 기준 [7일 이상 치료] 또는 [30일 이상 투약]
5) [1년 이내] 재검사 또는 추가검사 소견 (F/U, 추적관찰 포함)

# 5. 출력 형식 (Strict JSONL Format)
- 서론, 결론, 부연 설명 없이 데이터만 출력하라. 한 줄에 하나의 JSON 객체만 출력(JSONL).
- 끊김 방지를 위해 중요 고지사항(3개월/중대질환/수술)부터 우선 출력하라.
- 반드시 아래 양식만 사용하라. 다른 형식 절대 금지.

[결과 양식 - 이 형식만 출력]
{"type": "고지유형", "date": "날짜/기간", "disease": "질병명(코드)", "count": "총 n일/n회", "summary": "고지 문구 요약"}"""

    # ── 사용자 프롬프트 (구조화 데이터 전달) ──
    prompt = f"""고객명: {customer_name}
분석기준일: {today_str}
3개월 기준: {d3_str} ~ {today_str}
1년 기준: {d1y_str} ~ {today_str}
5년 기준: {d5y_str} ~ {today_str}

=== 구조화 데이터 (Python 정밀 계산 완료) ===
{json.dumps(structured, ensure_ascii=False, indent=2)}

=== 원본 텍스트 (수술/검사 판별용) ===
{all_text[:50000]}

위 시스템 지침에 따라 고지의무 대상 항목을 JSONL 형식으로 출력하라."""

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = msg.content[0].text.strip()

    # ── JSONL 파싱 로직 ──
    # 방법1: 한 줄씩 읽어서 유효한 JSON만 수집
    items = []
    for line in raw.split('\n'):
        line = line.strip()
        if not line:
            continue
        # 코드블록 마커 제거
        if line.startswith('```') or line.startswith('#'):
            continue
        # JSON 객체인 줄만 처리
        if line.startswith('{') and line.endswith('}'):
            try:
                obj = json.loads(line)
                items.append(obj)
            except json.JSONDecodeError:
                # 끊긴 줄 복구 시도
                try:
                    obj = json.loads(line + '}')
                    items.append(obj)
                except:
                    pass

    # JSONL 파싱 성공 시 기존 구조로 변환
    if items:
        return _jsonl_to_structured(items, structured)

    # 방법2: 기존 JSON 방식 폴백 (혹시 JSON으로 응답한 경우)
    raw_clean = raw
    if raw_clean.startswith('```'):
        raw_clean = re.sub(r'^```[a-z]*\n?', '', raw_clean).rstrip('`').strip()
    js = raw_clean.find('{')
    je = raw_clean.rfind('}')
    if js != -1 and je != -1:
        try:
            return json.loads(raw_clean[js:je+1])
        except:
            pass

    # 방법3: 빈 결과 반환 (오류 방지)
    return _empty_result()


def _jsonl_to_structured(items, structured):
    """지점장님 원본 로직 유지 + 입원일수/30일투약/재검사 합산 및 상세표기 완벽 교정"""
    result = _empty_result()

    for item in items:
        t = item.get('type', '')
        date_val = item.get('date', '')
        disease = item.get('disease', '')
        count_val = str(item.get('count', '0'))
        summary = item.get('summary', '')

        # 숫자 추출 로직 (입원일수, 투약일수, 통원횟수 공통 사용)
        try:
            num_val = int(re.search(r'\d+', count_val).group())
        except:
            num_val = 0

        # T11/L4 같은 부위는 거르고 진짜 질병 코드만 추출 [cite: 65]
        code_match = re.search(r'\(([A-Z][0-9]{2,})\)', disease)
        code = code_match.group(1) if code_match else ''
        disease_name = re.sub(r'\([^)]+\)', '', disease).strip()

        # 1. 최근 3개월 이내 의료행위 (item1) [cite: 66]
        if '3개월' in t:
            if '투약' in t or '투약' in summary:
                result['item1']['투약']['해당'] = True
                result['item1']['투약']['목록'].append({
                    '질병': disease_name, '코드': code, '날짜': date_val,
                    '약품명': summary[:30], '성분명': '', '용도': summary, '투약일수': num_val
                })
            elif any(k in t+summary for k in ['수술', '시술']):
                result['item1']['수술']['해당'] = True
                result['item1']['수술']['목록'].append({
                    '질병': disease_name, '수술명': summary, '날짜': date_val, '병원': ''
                })
            elif '입원' in t:
                result['item1']['입원']['해당'] = True
                result['item1']['입원']['목록'].append({
                    '질병': disease_name, '코드': code, '날짜': date_val, '병원': ''
                })
            else:
                result['item1']['질병확정진단']['해당'] = True
                result['item1']['질병확정진단']['목록'].append({
                    '질병': disease_name, '코드': code, '날짜': date_val, '병원': '', '주의': False
                })

        # 2. [지점장님 요청] 1년 이내 재검사/추적관찰 (item3) 
        # 병원이 달라도 동일 질병코드로 합산된 방문 횟수와 상세 검사 내용을 표기합니다.
        elif any(k in t for k in ['재검사', '추가검사', '1년']):
            result['item3']['해당'] = True
            result['item3']['목록'].append({
                '질병': disease_name, '코드': code,
                '최초진료일': date_val, '마지막진료일': date_val,
                '총방문횟수': num_val, '입원횟수': 0, '수술횟수': 0,
                '수술명': [], 
                '검사내용': summary if summary else "상세 기록 확인 필요", # 어떤 검사를 했는지 상세 표기
                '고지사유': f"{disease_name} 관련 추가 검사 및 추적 관찰", 
                '주의': False
            })

        # 3. 최근 5년 이내 의료행위 (item4) [cite: 71]
        elif any(k in t for k in ['수술', '시술']):
            result['item4']['수술']['해당'] = True
            result['item4']['수술']['목록'].append({
                '질병': disease_name, '수술명': summary, '날짜': date_val, '병원': ''
            })
        elif '입원' in t:
            result['item4']['입원']['해당'] = True
            result['item4']['입원']['목록'].append({
                '질병': disease_name, '입원일': date_val, '퇴원일': '', '병원': '', '일수': num_val # [해결] 0 대신 실제 일수
            })
        elif '30일' in t or '투약' in t:
            result['item4']['투약30일']['해당'] = True
            result['item4']['투약30일']['목록'].append({
                '질병': disease_name, '코드': code, '약품명': disease_name, 
                '합산일수': num_val, '용도': summary, '처방내역': [{'날짜': date_val, '투약일수': num_val}]
            })
        elif '7일' in t or '치료' in t:
            result['item4']['치료7일']['해당'] = True
            result['item4']['치료7일']['목록'].append({
                '질병': disease_name, '코드': code,
                '최초진료일': date_val.split('~')[0].strip() if '~' in date_val else date_val,
                '마지막진료일': date_val.split('~')[-1].strip() if '~' in date_val else date_val,
                '총방문횟수': num_val
            })

        # 4. 10대 중대질환 (item5) [cite: 70]
        elif '중대' in t or '중대질환' in t:
            result['item5']['해당'] = True
            for k in ['암','백혈병','고혈압','협심증','심근경색','심장판막증','간경화증','뇌졸중','당뇨','에이즈HIV','항문질환']:
                if k in disease or k in summary:
                    result['item5']['목록'][k] = f"{date_val} / {summary}"

    # 요약 및 신호등 설정 [cite: 78]
    result['요약'] = [item.get('summary', '') for item in items[:7] if item.get('summary')]
    result['signal'] = {'status': 'yellow' if items else 'green', 'reason': f'총 {len(items)}건 고지 대상 확인'}

    return result


def _empty_result():
    """빈 결과 구조 반환"""
    return {
        'item1': {
            '질병확정진단': {'해당': False, '목록': []},
            '질병의심소견': {'해당': False, '목록': []},
            '치료': {'해당': False, '목록': []},
            '입원': {'해당': False, '목록': []},
            '수술': {'해당': False, '목록': []},
            '투약': {'해당': False, '목록': []}
        },
        'item2': {
            '마약성진통제': {'해당': False, '목록': []},
            '혈압강하제': {'해당': False, '목록': []},
            '신경안정제': {'해당': False, '목록': []},
            '수면제': {'해당': False, '목록': []},
            '각성제': {'해당': False, '목록': []},
            '진통제': {'해당': False, '목록': []}
        },
        'item3': {'해당': False, '목록': []},
        'item4': {
            '입원': {'해당': False, '목록': []},
            '수술': {'해당': False, '목록': []},
            '시술처치': {'해당': False, '목록': []},
            '치료7일': {'해당': False, '목록': []},
            '투약30일': {'해당': False, '목록': []}
        },
        'item5': {
            '해당': False,
            '목록': {
                '암': '해당없음', '백혈병': '해당없음', '고혈압': '해당없음',
                '협심증': '해당없음', '심근경색': '해당없음', '심장판막증': '해당없음',
                '간경화증': '해당없음', '뇌졸중': '해당없음', '당뇨': '해당없음',
                '에이즈HIV': '해당없음', '항문질환': '해당없음'
            }
        },
        'signal': {'status': 'green', 'reason': '분석 완료'},
        '요약': []
    }


# ===== 렌더링 =====

def make_pdf_summary(r, customer_name, today_str, cost_stats):
    """고객용 요약본 PDF 생성"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        rightMargin=15*mm, leftMargin=15*mm,
        topMargin=15*mm, bottomMargin=15*mm)

    fn = 'Helvetica'
    import os as _os
    # 폰트 경로 우선순위: 레포 내 폰트 → 시스템 폰트
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
                fn = 'K'; break
        except: pass

    def ps(n, sz, c='#1a2744', sb=0, sa=3):
        return ParagraphStyle(n, fontName=fn, fontSize=sz,
            textColor=colors.HexColor(c), spaceBefore=sb, spaceAfter=sa)

    story = []
    i1=r.get('item1',{}); i2=r.get('item2',{}); i3=r.get('item3',{})
    i4=r.get('item4',{}); i5=r.get('item5',{}); signal=r.get('signal',{})
    summary=r.get('요약',[])

    sig = signal.get('status','green')
    sig_t = {'red':'인수 거절 가능성','yellow':'조건부 가입 가능','green':'일반심사 가능'}.get(sig,'일반심사 가능')

    def row(txt, c='#374151', sz=10, sb=0, sa=2):
        story.append(Paragraph(txt, ps('r', sz, c, sb, sa)))
    def sec(title, sb=8):
        story.append(Paragraph(title, ps('h', 12, '#1a2744', sb, 4)))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e5e7eb'), spaceAfter=4))
    def none_row():
        story.append(Paragraph('해당 없음', ps('n', 10, '#16a34a', 0, 4)))

    # 헤더
    story.append(Paragraph(f'알릴 의무 고지사항 확인서', ps('t', 18, '#1a2744', 0, 3)))
    story.append(Paragraph(f'{customer_name} 고객님   |   분석일: {today_str}   |   {sig_t}', ps('s', 10, '#6b7280', 0, 6)))
    story.append(HRFlowable(width="100%", thickness=3, color=colors.HexColor('#1a2744'), spaceAfter=10))

    # 1번 - 3개월
    has1 = any(i1.get(k,{}).get('해당') for k in ["질병확정진단","질병의심소견","치료","입원","수술","투약"])
    sec("1. 최근 3개월 이내 의료행위")
    if has1:
        for key in ["질병확정진단","치료","수술","투약"]:
            data = i1.get(key,{})
            if not data.get('해당'): continue
            for item in data.get('목록',[]):
                if key == "투약":
                    row(f'  · {item.get("약품명","")} — {item.get("용도","")} — {item.get("투약일수",0)}일', '#dc2626')
                elif key == "수술":
                    row(f'  · {item.get("수술명","")} — {item.get("날짜","")}', '#dc2626')
                else:
                    row(f'  · {item.get("질병","")} ({item.get("코드","")}) — {item.get("날짜","")} — {item.get("병원","")}', '#dc2626')
    else:
        none_row()

    # 2번
    has2 = any(i2.get(k,{}).get('해당') for k in ["마약성진통제","혈압강하제","신경안정제","수면제"])
    sec("2. 최근 3개월 약물 상시복용", 6)
    if has2:
        for key in ["마약성진통제","혈압강하제","신경안정제","수면제","각성제","진통제"]:
            data = i2.get(key,{})
            if not data.get('해당'): continue
            for item in data.get('목록',[]):
                row(f'  · {item.get("약물명","")} ({item.get("성분명","")}) — {"복용 중" if item.get("복용중") else "과거 복용"}', '#dc2626')
    else:
        none_row()

    # 3번
    sec("3. 최근 1년 이내 재검사/추가검사", 6)
    if i3.get('해당'):
        for d in i3.get('목록',[]):
            row(f'  · {d.get("질병","")} ({d.get("코드","")}) — {d.get("총방문횟수",0)}회 — {d.get("검사내용","")}', '#dc2626')
    else:
        none_row()

    # 4번 - 카테고리별
    sec("4. 최근 5년 이내 의료행위", 6)
    cats = [
        ("입원", i4.get('입원',{})),
        ("수술 (제왕절개 포함)", i4.get('수술',{})),
        ("계속하여 7일 이상 치료", i4.get('치료7일',{})),
        ("계속하여 30일 이상 투약", i4.get('투약30일',{})),
    ]
    for cat_name, data in cats:
        has = data.get('해당', False)
        if has:
            row(f'  [{cat_name}]', '#991b1b', 10, 2, 1)
            for item in data.get('목록', []):
                if not isinstance(item, dict): continue
                if '수술' in cat_name:
                    row(f'    · {item.get("수술명","")} — {item.get("날짜","")} — {item.get("병원","")}', '#dc2626')
                elif '투약' in cat_name:
                    row(f'    · {item.get("약품명","")} ({item.get("성분명","")}) — 합계 {item.get("합산일수",0)}일', '#dc2626')
                elif '입원' in cat_name:
                    row(f'    · {item.get("질병","")} — {item.get("입원일","")}~{item.get("퇴원일","")} — {item.get("일수",0)}일', '#dc2626')
                else:
                    row(f'    · {item.get("질병","")} ({item.get("코드","")}) — {item.get("총방문횟수",0)}회', '#dc2626')
        else:
            row(f'  [{cat_name}] 해당 없음', '#16a34a', 10, 2, 1)

    # 5번
    sec("5. 최근 5년 이내 10대 질병", 6)
    diseases_5=['암','백혈병','고혈압','협심증','심근경색','심장판막증','간경화증','뇌졸중','당뇨','에이즈HIV','항문질환']
    d5map=i5.get('목록',{})
    bad=[d for d in diseases_5 if '해당없음' not in str(d5map.get(d,'해당없음')) and '없음' not in str(d5map.get(d,'해당없음'))]
    ok=[d for d in diseases_5 if d not in bad]
    if bad: row(f'  해당 있음: {", ".join(bad)}', '#dc2626')
    row(f'  해당 없음: {", ".join(ok)}', '#16a34a')

    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#e5e7eb'), spaceBefore=10, spaceAfter=6))

    # 의료비 섹션
    if cost_stats:
        sec("6. 연도별 본인부담 의료비", 4)
        row(f'  총 본인부담금: {cost_stats["total_paid"]:,}원   |   연평균: {cost_stats["avg_paid"]:,}원   |   총 진료: {cost_stats["total_count"]}건', '#1a2744', 10, 0, 4)
        for y, d in cost_stats['year'].items():
            row(f'  {y}년  {d["count"]}건  →  본인부담 {d["paid"]:,}원  (보험혜택 {d["ins"]:,}원)', '#374151', 10, 0, 2)

        story.append(Spacer(1, 4*mm))
        sec("7. 질병별 의료비 상위 5개", 4)
        for i, (name, d) in enumerate(cost_stats['top5']):
            row(f'  {i+1}. {name} ({d["code"]})  {d["count"]}회  →  {d["paid"]:,}원', '#374151', 10, 0, 2)

    # 요약
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#c9a84c'), spaceBefore=10, spaceAfter=6))
    story.append(Paragraph('고지 필요 핵심 요약', ps('sh', 12, '#1a2744', 0, 5)))
    for s in summary:
        row(f'  ▶ {s}', '#1a2744', 10, 0, 3)

    story.append(Spacer(1, 6*mm))
    story.append(Paragraph('본 자료는 심평원 기본진료정보를 기반으로 AI가 분석한 참고용 자료입니다.   리치앤아이 · 글로벌금융판매',
        ps('f', 8, '#9ca3af', 0, 0)))

    doc.build(story)
    buf.seek(0)
    return buf

def render(r, customer_name, today_str):
    i1=r.get('item1',{}); i2=r.get('item2',{})
    i3=r.get('item3',{}); i4=r.get('item4',{})
    i5=r.get('item5',{}); signal=r.get('signal',{})
    summary=r.get('요약',[])

    alerts=[]
    for k in ["질병확정진단","질병의심소견","치료","입원","수술","투약"]:
        if i1.get(k,{}).get('해당'): alerts.append(k)
    for k in ["마약성진통제","혈압강하제","신경안정제","수면제","각성제","진통제"]:
        if i2.get(k,{}).get('해당'): alerts.append(k)
    if i3.get('해당'): alerts.append("재검사")
    for k in ["입원","수술","치료7일","투약30일"]:
        if i4.get(k,{}).get('해당'): alerts.append(k)
    if i5.get('해당'): alerts.append("10대질병")

    sig=signal.get('status','green')
    sig_map={'red':('🔴','인수 거절 가능성','#fef2f2','#dc2626'),
             'yellow':('🟡','조건부 가입 가능','#fffbeb','#f59e0b'),
             'green':('🟢','일반심사 가능','#f0fdf4','#16a34a')}
    si,st2,sbg,sfc=sig_map.get(sig,sig_map['green'])

    st.markdown(f"""
    <div class="top-banner">
        <div class="banner-title">🏥 알릴 의무 고지사항 확인서</div>
        <div class="banner-customer">👤 {customer_name} 고객님</div>
        <div class="banner-sub">분석일: {today_str} · 리치앤아이 · 글로벌금융판매</div>
        <div>
            {'<span class="badge-alert">🚨 고지 필요 '+str(len(alerts))+'가지</span>' if alerts else '<span class="badge-ok">✅ 고지 필요 없음</span>'}
            <span class="badge-signal" style="background:{sbg};color:{sfc};">{si} {st2}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ===== 1번 =====
    has1=any(i1.get(k,{}).get('해당') for k in ["질병확정진단","질병의심소견","치료","입원","수술","투약"])
    if has1:
        st.markdown('<div class="sec-title"><span class="sec-num">1</span>최근 3개월 이내 의료행위</div>', unsafe_allow_html=True)
        for key in ["질병확정진단","질병의심소견","치료","입원","수술","투약"]:
            data=i1.get(key,{}); has=data.get('해당',False)
            if not has: continue
            st.markdown(f"<div class='item-title'>{key}</div>", unsafe_allow_html=True)
            for item in data.get('목록',[]):
                if key=="투약":
                    days=item.get('투약일수',0)
                    cb=f'<span class="code-badge">{item.get("코드","")}</span>' if item.get('코드') else ''
                    st.markdown(f"""<div class="drug-card {'drug-card-alert' if days>=30 else ''}">
                        <div class="drug-name">{item.get('약품명','')} {cb}</div>
                        <div class="drug-comp">성분: {item.get('성분명','')}</div>
                        <div class="drug-purpose">💊 {item.get('용도','')}</div>
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <div style="font-size:13px;color:#6b7280;">{item.get('질병','')} · {item.get('날짜','')}</div>
                            <div class="{'drug-days-red' if days>=30 else 'drug-days-ok'}">{days}일</div>
                        </div></div>""", unsafe_allow_html=True)
                elif key=="수술":
                    st.markdown(f"""<div class="surgery-card"><div style="font-size:26px;">✂️</div>
                        <div><div class="surgery-name">{item.get('수술명','')}</div>
                        <div class="surgery-info">{item.get('질병','')} · {item.get('날짜','')} · {item.get('병원','')}</div>
                        </div></div>""", unsafe_allow_html=True)
                else:
                    crit=item.get('주의',False) or is_critical(item.get('코드',''),item.get('질병',''))
                    cb=f'<span class="code-badge">{item.get("코드","")}</span>' if item.get('코드') else ''
                    wb='<span class="warn-badge">⚠ 주의</span>' if crit else ''
                    extra=f'· {item.get("내용","")}' if item.get('내용') else ''
                    st.markdown(f"""<div class="disease-card {'disease-card-warn' if crit else ''}">
                        <div class="dname">{item.get('질병','')} {cb} {wb}</div>
                        <div style="font-size:13px;color:#6b7280;">{item.get('날짜','')} · {item.get('병원','')} {extra}</div>
                        </div>""", unsafe_allow_html=True)
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ===== 2번 =====
    has2=any(i2.get(k,{}).get('해당') for k in ["마약성진통제","혈압강하제","신경안정제","수면제","각성제","진통제"])
    if has2:
        st.markdown('<div class="sec-title"><span class="sec-num">2</span>최근 3개월 약물 상시복용</div>', unsafe_allow_html=True)
        for key in ["마약성진통제","혈압강하제","신경안정제","수면제","각성제","진통제"]:
            data=i2.get(key,{}); has=data.get('해당',False)
            if not has: continue
            st.markdown(f"<div class='item-title'>{key}</div>", unsafe_allow_html=True)
            for item in data.get('목록',[]):
                st.markdown(f"""<div class="drug-card drug-card-alert">
                    <div class="drug-name">💊 {item.get('약물명','')}</div>
                    <div class="drug-comp">성분: {item.get('성분명','')}</div>
                    <div style="font-size:13px;color:#6b7280;">{'복용 중' if item.get('복용중') else '과거 복용'} · 시작일: {item.get('복용시작','')}</div>
                    </div>""", unsafe_allow_html=True)
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ===== 3번 =====
    if i3.get('해당'):
        st.markdown('<div class="sec-title"><span class="sec-num">3</span>최근 1년 이내 재검사/추가검사</div>', unsafe_allow_html=True)
        acc_colors=['#1a2744','#2563eb','#7c3aed','#0891b2','#059669','#dc2626']
        for idx,d in enumerate(i3.get('목록',[])):
            code=d.get('코드',''); name=d.get('질병','')
            crit=d.get('주의',False) or is_critical(code,name)
            acc='#dc2626' if crit else acc_colors[idx%len(acc_colors)]
            cb=f'<span class="code-badge">{code}</span>' if code else ''
            wb='<span class="warn-badge">⚠ 주의</span>' if crit else ''
            surg_names=d.get('수술명',[])
            surg_val=', '.join(surg_names) if surg_names else '없음'
            surg_cls='stat-red' if surg_names else ''
            recheck=f'<div class="recheck-box">🔍 검사 내용: {d.get("검사내용","")}<br>📌 고지 사유: {d.get("고지사유","")}</div>' if d.get('검사내용') else ''
            st.markdown(f"""
            <div class="disease-card {'disease-card-warn' if crit else ''}" style="border-left:5px solid {acc};">
                <div class="dname">{name} {cb} {wb}</div>
                <div class="stats-grid">
                    <div class="stat-box"><div class="stat-label">최초 진단일</div><div class="stat-value" style="font-size:13px;">{d.get('최초진료일','-')}</div></div>
                    <div class="stat-box"><div class="stat-label">마지막 진료일</div><div class="stat-value" style="font-size:13px;">{d.get('마지막진료일','-')}</div></div>
                    <div class="stat-box"><div class="stat-label">통원 횟수</div><div class="stat-value stat-blue">{d.get('총방문횟수',0)}회</div></div>
                    <div class="stat-box"><div class="stat-label">수술</div><div class="stat-value {surg_cls}" style="font-size:12px;">{surg_val}</div></div>
                </div>
                {recheck}
            </div>""", unsafe_allow_html=True)
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ===== 4번 =====
    has4=any(i4.get(k,{}).get('해당') for k in ["입원","수술","치료7일","투약30일"])
    if has4:
        st.markdown('<div class="sec-title"><span class="sec-num">4</span>최근 5년 이내 의료행위</div>', unsafe_allow_html=True)

        if i4.get('입원',{}).get('해당'):
            st.markdown("<div class='item-title'>입원</div>", unsafe_allow_html=True)
            for item in i4['입원'].get('목록',[]):
                st.markdown(f"""<div class="disease-card disease-card-warn">
                    <div class="dname">🏥 {item.get('질병','')}</div>
                    <div style="font-size:13px;color:#6b7280;">{item.get('입원일','')} ~ {item.get('퇴원일','')} · {item.get('병원','')} · {item.get('일수',0)}일</div>
                    </div>""", unsafe_allow_html=True)

        if i4.get('수술',{}).get('해당'):
            st.markdown("<div class='item-title'>수술 (제왕절개 포함)</div>", unsafe_allow_html=True)
            for item in i4['수술'].get('목록',[]):
                st.markdown(f"""<div class="surgery-card"><div style="font-size:26px;">✂️</div>
                    <div><div class="surgery-name">{item.get('수술명','')}</div>
                    <div class="surgery-info">{item.get('질병','')} · {item.get('날짜','')} · {item.get('병원','')}</div>
                    </div></div>""", unsafe_allow_html=True)

        if i4.get('치료7일',{}).get('해당'):
            st.markdown("<div class='item-title'>계속하여 7일 이상 치료</div>", unsafe_allow_html=True)
            for item in i4['치료7일'].get('목록',[]):
                if isinstance(item,dict):
                    cb=f'<span class="code-badge">{item.get("코드","")}</span>' if item.get('코드') else ''
                    st.markdown(f"""<div class="disease-card">
                        <div class="dname">{item.get('질병','')} {cb}</div>
                        <div class="stats-grid">
                            <div class="stat-box"><div class="stat-label">최초 진료일</div><div class="stat-value" style="font-size:13px;">{item.get('최초진료일','-')}</div></div>
                            <div class="stat-box"><div class="stat-label">마지막 진료일</div><div class="stat-value" style="font-size:13px;">{item.get('마지막진료일','-')}</div></div>
                            <div class="stat-box"><div class="stat-label">통원 횟수</div><div class="stat-value stat-blue">{item.get('총방문횟수',0)}회</div></div>
                        </div></div>""", unsafe_allow_html=True)

        if i4.get('투약30일',{}).get('해당'):
            st.markdown("<div class='item-title'>계속하여 30일 이상 투약</div>", unsafe_allow_html=True)
            for item in i4['투약30일'].get('목록',[]):
                if isinstance(item,dict):
                    total=item.get('합산일수',0)
                    cb=f'<span class="code-badge">{item.get("코드","")}</span>' if item.get('코드') else ''
                    st.markdown(f"""<div class="drug-card drug-card-alert">
                        <div class="drug-name">{item.get('약품명','')} {cb}</div>
                        <div class="drug-comp">성분: {item.get('성분명','')}</div>
                        <div class="drug-purpose">💊 {item.get('용도','')}</div>
                        <div style="background:#fff0f0;border-radius:8px;padding:8px 12px;margin:8px 0;">""", unsafe_allow_html=True)
                    for p in item.get('처방내역',[]):
                        st.markdown(f"<div style='display:flex;justify-content:space-between;font-size:13px;padding:2px 0;'><span style='color:#374151;'>{p.get('날짜','')}</span><span style='font-weight:700;color:#dc2626;'>{p.get('투약일수',0)}일</span></div>", unsafe_allow_html=True)
                    st.markdown(f"</div><div style='text-align:right;font-size:18px;font-weight:900;color:#dc2626;'>합계: {total}일</div></div>", unsafe_allow_html=True)

        proc=i4.get('시술처치',{})
        if proc.get('해당') and proc.get('목록'):
            st.markdown('<div class="proc-box"><div class="proc-title">⚠️ 시술·처치 (고지 권장)</div>', unsafe_allow_html=True)
            for p in proc.get('목록',[]):
                c=p.get('내용','') if isinstance(p,dict) else str(p)
                st.markdown(f'<div class="proc-item"><span>•</span><span>{c}</span></div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ===== 5번 =====
    st.markdown('<div class="sec-title"><span class="sec-num">5</span>최근 5년 이내 10대 질병</div>', unsafe_allow_html=True)
    diseases_5=['암','백혈병','고혈압','협심증','심근경색','심장판막증','간경화증','뇌졸중','당뇨','에이즈HIV','항문질환']
    d5map=i5.get('목록',{})
    ok_list=[d for d in diseases_5 if '해당없음' in str(d5map.get(d,'해당없음')) or '없음' in str(d5map.get(d,'해당없음'))]
    bad_list=[d for d in diseases_5 if d not in ok_list]
    if bad_list:
        st.markdown(f"<div style='margin-bottom:6px;'><b style='color:#dc2626;font-size:14px;'>⚠️ 해당 있음:</b></div>", unsafe_allow_html=True)
        st.markdown('<div class="d5-row">'+''.join([f'<span class="d5-bad">⚠️ {d}</span>' for d in bad_list])+'</div>', unsafe_allow_html=True)
    st.markdown(f"<div style='margin:10px 0 6px;'><b style='color:#16a34a;font-size:14px;'>✅ 해당 없음:</b></div>", unsafe_allow_html=True)
    st.markdown('<div class="d5-row">'+''.join([f'<span class="d5-ok">✅ {d}</span>' for d in ok_list])+'</div>', unsafe_allow_html=True)

    # ===== 인쇄 버튼 =====
    st.markdown('<div style="text-align:right;margin:16px 0;"><button onclick="window.print()" style="background:#1a2744;color:#c9a84c;border:none;border-radius:10px;padding:10px 24px;font-size:14px;font-weight:700;cursor:pointer;">🖨️ 인쇄 / PDF 저장</button></div>', unsafe_allow_html=True)

    # ===== 요약 =====
    if summary:
        st.markdown(f"""<div class="summary-box">
            <div class="summary-title">📋 고지 필요 핵심 요약</div>
            {''.join([f'<div class="summary-item"><span class="summary-arrow">▶</span><span class="summary-text">{s}</span></div>' for s in summary])}
        </div>""", unsafe_allow_html=True)



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
                    if t: all_text.append(t)

        if pdf_d:
            c=pdf_d.read()
            detail=parse_detail(c)
            surgs=len([p for p in detail if p['type']=='surgery'])
            st.markdown(f'<div class="extract-box"><span class="extract-label">✅ 세부진료정보</span><span class="extract-count">수술 {surgs}건 감지</span></div>',unsafe_allow_html=True)
            with pdfplumber.open(BytesIO(c)) as pdf:
                for pg in pdf.pages:
                    t=pg.extract_text()
                    if t: all_text.append(t)

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

        structured={
            'today':today_str,
            'd3':d3.isoformat(),'d1y':d1y.isoformat(),'d5y':d5y.isoformat(),
            'records_3m':[{'date':r['date'],'hospital':r['hospital'],'code':r['code'],'disease':r['disease']} for r in r3m if not r['is_pharmacy']],
            'visits_1y_2plus':{
                code:{'disease':v['disease'],'count':v['count'],'first':v['first'],'last':v['last'],'hospitals':v['hospitals'][:3]}
                for code,v in visits1y.items() if v['count']>=2
            },
            'visits_1y_all':{
                code:{'disease':v['disease'],'count':v['count'],'first':v['first'],'last':v['last']}
                for code,v in visits1y.items()
            },
            'visits_5y_7plus':{
                code:{'disease':v['disease'],'count':v['count'],'first':v['first'],'last':v['last']}
                for code,v in visits5y.items() if v['count']>=7
            },
'drug_by_disease_5y':{
    k:{'code':v.get('code',''), 'disease':v.get('disease',''), 'drug_name':v.get('drug_name',''),
       'component':v.get('component',''), 'total_days':v.get('total_days',0), 
       'prescriptions':v.get('prescriptions',[])}
    for k,v in drug5y.items()
},
            'surgeries_5y':[{'date':p['date'],'hospital':p['hospital'],'keyword':p['keyword'],'detail':p['detail'][:80]} for p in surgs5y],
            'procedures_5y':[{'date':p['date'],'hospital':p['hospital'],'detail':p['detail'][:60]} for p in procs5y],
            'inpatient_5y':[{'date':r['date'],'hospital':r['hospital'],'disease':r['disease']} for r in inpat5y],
            'rx_3m':[{
                'date':rx['date'],
                'drug_name':rx['drug_name'],
                'component':rx['component'],
                'days':rx['days'],
                'hospital':rx['hospital']
            } for rx in rx if rx.get('date','') >= d3.isoformat()]
        }

        with st.spinner("🤖 Claude AI 분석 중... (30초~1분 소요)"):
            try:
                result=analyze(api_key,customer_name,structured,'\n'.join(all_text))
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
    render(st.session_state.result,st.session_state.customer,st.session_state.today_str)
    # 의료비 탭
    if st.session_state.cost_stats:
        render_cost(st.session_state.cost_stats)
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
