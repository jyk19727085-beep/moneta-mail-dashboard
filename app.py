import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import requests
import json
import re
from streamlit_autorefresh import st_autorefresh

# ==========================================
# 1. 터미널 UI 및 자동 감시 설정 (1분 주기)
# ==========================================
st.set_page_config(page_title="Minerva Quant Terminal", page_icon="📈", layout="wide")
st_autorefresh(interval=60000, limit=None, key="auto_scanner")

# ==========================================
# 2. 토큰 및 챗방 ID 설정 (안전한 자동 정화)
# ==========================================
def clean_token(token_str):
    """보이지 않는 공백이나 줄바꿈을 완벽히 제거하여 401 에러를 방지합니다."""
    if not token_str: return ""
    return re.sub(r'\s+', '', str(token_str))

# ==========================================
# 3. API 및 DB 초기화
# ==========================================
@st.cache_resource
def init_firebase():
    try:
        if not firebase_admin._apps:
            cred_dict = dict(st.secrets["firebase"])
            cred_dict["private_key"] = cred_dict["private_key"].replace('\\n', '\n')
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception:
        return None

db = init_firebase()

try:
    genai.configure(api_key=st.secrets["api_keys"]["gemini"])
except Exception:
    pass

# ==========================================
# 4. 텔레그램 자동 발송 모듈 (풀버전 전송)
# ==========================================
def send_telegram_alert(subject, analysis, news_list):
    """대시보드를 켤 필요 없이 텔레그램으로 완벽한 브리핑을 쏩니다."""
    try:
        bot_token = clean_token(st.secrets["api_keys"]["telegram_bot_token"])
        # 주인님의 챗방 ID는 고정이므로 하드코딩 처리하여 에러 차단
        chat_id = "8841018398"
        
        if not bot_token: return
            
        text = f"🚨 <b>[Minerva 퀀트 시그널 포착]</b>\n\n"
        text += f"📌 <b>이슈:</b> {subject}\n"
        text += f"🌡️ <b>투심:</b> {analysis.get('sentiment', '중립')}\n\n"
        
        text += f"🧠 <b>[매크로 파급력 & 인사이트]</b>\n{analysis.get('summary', '')}\n\n"
        text += f"💼 <b>[월가 스마트머니 동향 & 포지션]</b>\n{analysis.get('analyst_view', '')}\n\n"
        
        text += "📰 <b>[관련 핵심 뉴스 원문 링크]</b>\n"
        if news_list:
            for i, news in enumerate(news_list):
                text += f"{i+1}. <a href='{news['link']}'>{news['title']}</a>\n"
        else:
            text += "관련 뉴스를 검색할 수 없습니다.\n"

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
        requests.post(url, data=payload, timeout=5)
    except Exception as e:
        pass

def get_gmail_service():
    try:
        creds_data = dict(st.secrets["gmail_oauth"])
        creds_data["token_uri"] = "https://oauth2.googleapis.com/token"
        creds = Credentials.from_authorized_user_info(creds_data)
        return build('gmail', 'v1', credentials=creds)
    except Exception:
        return None

# ==========================================
# 5. AI 메일 심층 분석 모듈 (거품 제거형 퀀트 두뇌)
# ==========================================
def analyze_email_content(text_content):
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"""
        당신은 월스트리트 수석 퀀트 애널리스트 '모네타'입니다. 
        아래 이메일 데이터를 분석하여 철저한 퀀트 리포트를 작성하십시오. 
        짧은 단어만 있어도 글로벌 거시경제(금리, 환율, 유동성)와의 인과관계를 추론해 방대하게 작성해야 합니다.

        [수신 이메일 데이터]
        "{text_content}"

        [규칙] JSON 형식으로만 답하세요. (대괄호나 마크다운 기호 절대 금지)
        {{
            "summary": "메일 내용이 글로벌 유동성과 매크로 시장에 미칠 파급력을 상세히 분석 (최소 200자 이상)",
            "keyword": "구글 뉴스 검색을 위한 구체적인 경제 키워드 1개",
            "analyst_view": "월가 스마트머니 동향 및 실전 롱/숏 포지션 전략 제안 (최소 200자 이상)",
            "sentiment": "강세, 약세, 관망, 중립 중 택 1"
        }}
        """
        response = model.generate_content(prompt)
        raw_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(raw_text)
    except Exception:
        return {
            "summary": "AI 분석 중 일시적 지연이 발생했습니다. 변동성이 확대되는 구간이므로 국채 금리 스프레드를 주시하십시오.",
            "keyword": "글로벌 매크로",
            "analyst_view": "리스크 관리가 필요한 구간입니다. 델타 헷징 및 현금 비중 확대를 권고합니다.",
            "sentiment": "관망"
        }

def fetch_news_with_links(keyword):
    try:
        api_key = st.secrets["api_keys"]["google_search"]
        cx = st.secrets["api_keys"]["search_engine_id"]
        url = f"https://www.googleapis.com/customsearch/v1?key={api_key}&cx={cx}&q={keyword} 경제 OR 증시&num=3"
        res = requests.get(url, timeout=5).json()
        
        news_data = []
        if 'items' in res:
            for item in res['items']:
                news_data.append({"title": item['title'], "link": item['link']})
            return news_data
        return []
    except Exception:
        return []

# ==========================================
# 6. 코어 엔진 (수동 버튼 없이 100% 자동 실행)
# ==========================================
def scan_and_process():
    service = get_gmail_service()
    if not service or not db: return 0

    try:
        results = service.users().messages().list(userId='me', q='is:unread', maxResults=2).execute()
        messages = results.get('messages', [])
    except Exception:
        return 0

    processed_count = 0
    for msg in messages:
        msg_id = msg['id']
        doc_ref = db.collection('daniel_reports').document(msg_id)
        
        if not doc_ref.get().exists:
            try:
                msg_data = service.users().messages().get(userId='me', id=msg_id).execute()
                headers = msg_data['payload']['headers']
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '새로운 시그널')
                snippet = msg_data.get('snippet', '')

                # 1. 메일 내용 병합 및 심층 분석
                combined_text = subject + " " + snippet
                analysis = analyze_email_content(combined_text)
                
                # 2. 관련 뉴스 찾기 (클릭 가능한 링크 포함)
                news_links = fetch_news_with_links(analysis.get('keyword', '경제'))

                # 3. DB 저장
                doc_ref.set({
                    'id': msg_id,
                    'subject': subject,
                    'summary': analysis.get('summary'),
                    'analyst_view': analysis.get('analyst_view'),
                    'sentiment': analysis.get('sentiment'),
                    'news': news_links,
                    'timestamp': firestore.SERVER_TIMESTAMP
                })

                # 4. 메일 읽음 처리
                service.users().messages().modify(userId='me', id=msg_id, body={'removeLabelIds': ['UNREAD']}).execute()
                
                # 5. 🚨 대망의 텔레그램 자동 발송 (모든 리포트를 통째로 전송!)
                send_telegram_alert(subject, analysis, news_links)
                
                processed_count += 1
            except Exception:
                continue

    return processed_count

# ==========================================
# 7. 대시보드 UI (깔끔한 뷰어 역할)
# ==========================================
def main():
    st.markdown("""
        <div style='background-color:#0f172a; padding:15px; border-radius:10px; margin-bottom:20px;'>
            <h2 style='color:#38bdf8; text-align:center; margin:0;'>📊 Minerva Quant Terminal</h2>
            <p style='color:#94a3b8; text-align:center; margin:0;'>Daniel's Auto-Pilot Macro Engine</p>
        </div>
    """, unsafe_allow_html=True)

    # 대시보드를 켜두기만 하면 알아서 스캐닝하고 텔레그램으로 보냅니다.
    with st.spinner('글로벌 매크로 데이터를 자동 스캐닝 중입니다...'):
        new_count = scan_and_process()
        if new_count > 0:
            st.toast(f"🚨 {new_count}건의 분석 리포트가 텔레그램으로 전송되었습니다!", icon="🔥")

    if not db:
        st.error("데이터베이스 연결 대기 중입니다.")
        return

    docs = list(db.collection('daniel_reports').order_by('timestamp', direction=firestore.Query.DESCENDING).stream())

    if not docs:
        st.info("💡 대기 중인 시그널이 없습니다. 메일을 수신하면 즉시 딥러닝 분석 후 텔레그램으로 전송합니다.")
    else:
        for doc in docs:
            data = doc.to_dict()
            sentiment = data.get('sentiment', '중립')
            color = "#ef4444" if sentiment == "강세" else "#3b82f6" if sentiment == "약세" else "#f59e0b" if sentiment == "관망" else "#64748b"
            
            with st.container():
                st.markdown(f"""
                <div style='border-left: 5px solid {color}; background-color: #f8fafc; padding: 15px; border-radius: 5px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05); margin-bottom: 10px;'>
                    <h4 style='margin-top:0; color:#1e293b;'>📡 시그널: {data.get('subject', '제목 없음')}</h4>
                """, unsafe_allow_html=True)
                
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.markdown("**🧠 퀀트 매크로 인사이트**")
                    st.info(data.get('summary', ''))
                    
                    st.markdown("**💼 월가 스마트머니 동향 & 실전 포지션**")
                    st.success(data.get('analyst_view', ''))
                
                with col2:
                    st.metric(label="시장 투심 (Sentiment)", value=sentiment)
                    
                    st.markdown("**🔗 근거 자료 및 원문 뉴스**")
                    news_items = data.get('news', [])
                    if news_items and isinstance(news_items[0], dict):
                        for n in news_items:
                            # 하이퍼링크가 대시보드에서도 완벽하게 클릭되도록 설정
                            st.markdown(f"👉 <a href='{n['link']}' target='_blank' style='text-decoration:none;'>{n['title']}</a>", unsafe_allow_html=True)
                    else:
                        st.caption("관련 뉴스를 찾지 못했습니다.")
                    
                    st.write("")
                    if st.button("🗑️ 리포트 파기", key=f"del_{data['id']}", use_container_width=True):
                        db.collection('daniel_reports').document(data['id']).delete()
                        st.rerun()
                
                st.markdown("</div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
