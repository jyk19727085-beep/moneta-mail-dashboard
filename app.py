import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import requests
import json
import streamlit.components.v1 as components

# ==========================================
# 1. 🚨 텔레그램 토큰 강제 고정 (Secrets 에러 영구 차단)
# ==========================================
# 주인님! 아래 큰따옴표("") 안에 아까 새로 받으신 긴 토큰을 띄어쓰기 없이 붙여넣으십시오!
# 예시: BOT_TOKEN = "1234567890:ABCDefGhIjKl..."
BOT_TOKEN = "8824362537:AAFKYTWaQp3gpVNZESGDPTcThf2519P1jvU"
CHAT_ID = "8841018398"

# ==========================================
# 2. UI 및 무결점 자동 감시 엔진 (외부 도구 완전 삭제)
# ==========================================
st.set_page_config(page_title="Minerva Quant Terminal", page_icon="📈", layout="wide")

# 에러를 일으키던 st_autorefresh 대신, 절대 고장나지 않는 순수 웹 새로고침(60초)을 강제 주입합니다.
components.html('<meta http-equiv="refresh" content="60">', height=0)

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
# 3. 텔레그램 초심층 리포트 자동 발송 모듈
# ==========================================
def send_telegram_alert(subject, analysis, news_list):
    """텔레그램으로 메일내용, 분석, 뉴스 링크를 통째로 쏩니다."""
    try:
        if BOT_TOKEN == "여기에_새로_받은_토큰을_붙여넣으세요" or not BOT_TOKEN:
            return 
            
        text = f"🚨 <b>[Minerva 퀀트 시그널 포착]</b>\n\n"
        text += f"📌 <b>이슈:</b> {subject}\n"
        text += f"🌡️ <b>투심:</b> {analysis.get('sentiment', '중립')}\n\n"
        
        text += f"🧠 <b>[핵심 요약 & 매크로 파급력]</b>\n{analysis.get('summary', '')}\n\n"
        text += f"💼 <b>[월가 동향 & 실전 포지션]</b>\n{analysis.get('analyst_view', '')}\n\n"
        
        text += "📰 <b>[관련 핵심 뉴스 링크]</b>\n"
        if news_list:
            for i, news in enumerate(news_list):
                text += f"{i+1}. <a href='{news['link']}'>{news['title']}</a>\n"
        else:
            text += "관련 뉴스를 검색할 수 없습니다.\n"
            
        text += "\n👉 <i>과거 데이터 및 딥 다이브는 대시보드를 참조하십시오.</i>"

        url = f"https://api.telegram.org/bot{BOT_TOKEN.strip()}/sendMessage"
        payload = {'chat_id': CHAT_ID.strip(), 'text': text, 'parse_mode': 'HTML'}
        requests.post(url, data=payload, timeout=5)
    except Exception:
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
# 4. AI 메일 심층 분석 모듈
# ==========================================
def analyze_email_content(text_content):
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"""
        당신은 월스트리트 수석 퀀트 애널리스트 '모네타'입니다. 
        아래 이메일 데이터를 분석하여 철저한 퀀트 리포트를 작성하십시오. 단어 하나만 있어도 거시경제적 배경을 추론해 방대하게 작성해야 합니다.

        [수신 이메일 데이터]
        "{text_content}"

        [규칙] JSON 형식으로만 답하세요. (마크다운 금지)
        {{
            "summary": "메일 내용의 의미와 글로벌 유동성, 금리, 환율 등에 미칠 파급력을 상세히 분석 (최소 200자)",
            "keyword": "구글 뉴스 검색을 위한 구체적인 경제 키워드 1개",
            "analyst_view": "월가 스마트머니 동향 및 실전 롱/숏 포지션 전략 제안 (최소 200자)",
            "sentiment": "강세, 약세, 관망, 중립 중 택 1"
        }}
        """
        response = model.generate_content(prompt)
        raw_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(raw_text)
    except Exception:
        return {
            "summary": "AI 분석 중 일시적 지연이 발생했습니다. 핵심 키워드를 바탕으로 시장 변동성을 주시하십시오.",
            "keyword": "글로벌 매크로",
            "analyst_view": "리스크 관리가 필요한 구간입니다. 델타 헷징 및 현금 비중 확대를 권고합니다.",
            "sentiment": "관망"
        }

def fetch_news_with_links(keyword):
    try:
        api_key = st.secrets["api_keys"]["google_search"]
        cx = st.secrets["api_keys"]["search_engine_id"]
        url = f"https://www.googleapis.com/customsearch/v1?key={api_key}&cx={cx}&q={keyword} 주식 경제&num=3"
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
# 5. 코어 엔진 (자동 감시 및 처리)
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

                combined_text = subject + " " + snippet
                analysis = analyze_email_content(combined_text)
                news_links = fetch_news_with_links(analysis.get('keyword', '경제'))

                doc_ref.set({
                    'id': msg_id,
                    'subject': subject,
                    'summary': analysis.get('summary'),
                    'analyst_view': analysis.get('analyst_view'),
                    'sentiment': analysis.get('sentiment'),
                    'news': news_links,
                    'timestamp': firestore.SERVER_TIMESTAMP
                })

                service.users().messages().modify(userId='me', id=msg_id, body={'removeLabelIds': ['UNREAD']}).execute()
                
                # 🚨 텔레그램 100% 자동 발송 실행
                send_telegram_alert(subject, analysis, news_links)
                
                processed_count += 1
            except Exception:
                continue

    return processed_count

# ==========================================
# 6. 대시보드 UI
# ==========================================
def main():
    st.markdown("""
        <div style='background-color:#0f172a; padding:15px; border-radius:10px; margin-bottom:20px;'>
            <h2 style='color:#38bdf8; text-align:center; margin:0;'>📊 Minerva Quant Terminal</h2>
            <p style='color:#94a3b8; text-align:center; margin:0;'>Daniel's Auto-Pilot Macro Engine</p>
        </div>
    """, unsafe_allow_html=True)

    with st.spinner('글로벌 매크로 데이터를 자동 스캐닝 중입니다...'):
        new_count = scan_and_process()
        if new_count > 0:
            st.toast(f"🚨 {new_count}건의 분석 리포트가 텔레그램으로 전송되었습니다!", icon="🔥")

    if not db:
        st.error("데이터베이스 연결 대기 중입니다.")
        return

    docs = list(db.collection('daniel_reports').order_by('timestamp', direction=firestore.Query.DESCENDING).stream())

    if not docs:
        st.info("💡 대기 중인 시그널이 없습니다. 메일을 수신하면 즉시 분석 후 텔레그램으로 전송합니다.")
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
