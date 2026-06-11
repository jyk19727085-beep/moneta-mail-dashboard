import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import requests
import json
from streamlit_autorefresh import st_autorefresh

# ==========================================
# 1. UI 설정 및 자동 새로고침 (클라우드 감시)
# ==========================================
st.set_page_config(page_title="Minerva AI Dashboard", page_icon="📈", layout="centered")

# 60초(60000ms)마다 백그라운드 엔진 가동
st_autorefresh(interval=60000, limit=None, key="auto_scanner")

# ==========================================
# 2. API 및 DB 초기화
# ==========================================
@st.cache_resource
def init_firebase():
    """Firebase DB 연결"""
    try:
        if not firebase_admin._apps:
            cred_dict = dict(st.secrets["firebase"])
            cred_dict["private_key"] = cred_dict["private_key"].replace('\\n', '\n')
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        st.error(f"데이터베이스 연결 오류: {e}")
        return None

db = init_firebase()

try:
    genai.configure(api_key=st.secrets["api_keys"]["gemini"])
except Exception as e:
    st.error("AI 엔진 초기화 실패. 키 설정을 확인해 주십시오.")

# ==========================================
# 3. 비서 미네르바의 분석 및 알림 모듈
# ==========================================
def send_telegram(subject, summary, sentiment):
    """텔레그램 챗봇 알림 발송"""
    try:
        bot_token = st.secrets["api_keys"]["telegram_bot_token"]
        chat_id = st.secrets["api_keys"]["telegram_chat_id"]
        if not bot_token or not chat_id: return
        
        text = f"🔔 [새로운 투자 분석 보고서 도착]\n\n📌 제목: {subject}\n🌡️ 시장 반응: {sentiment}\n📝 요약: {summary}\n\n👉 주인님, 대시보드에 접속하여 심층 분석을 확인해 주십시오."
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
        requests.post(url, data={'chat_id': chat_id, 'text': text}, timeout=5)
    except Exception as e:
        print(f"텔레그램 발송 오류: {e}")

def get_gmail_service():
    """지메일 보안 통행증 확인"""
    try:
        creds_data = dict(st.secrets["gmail_oauth"])
        creds_data["token_uri"] = "https://oauth2.googleapis.com/token"
        creds = Credentials.from_authorized_user_info(creds_data)
        return build('gmail', 'v1', credentials=creds)
    except Exception as e:
        return None

def analyze_email_content(text_content):
    """안전한 AI 분석 로직 (에러 원천 차단)"""
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = (
            "당신은 냉철한 AI 금융 비서입니다. 아래 [이메일 내용]을 분석하여 정확히 JSON 형식으로만 대답하십시오.\n"
            "어떤 경우에도 부연 설명이나 마크다운 기호를 넣지 마십시오. 오직 순수 JSON 데이터만 출력해야 합니다.\n\n"
            f"[이메일 내용]\n{text_content}\n\n"
            "[출력 JSON 구조]\n"
            "{\n"
            '  "summary": "메일의 핵심 1~2줄 요약 (내용이 짧으면 그대로 요약)",\n'
            '  "keyword": "검색용 핵심 경제 단어 1개 (예: 반도체, 금리, 테스트 등)",\n'
            '  "analyst_view": "내용에 기반한 시장/전문가 예상 반응 (내용이 너무 짧으면 단순 알림이므로 판단 보류로 기재)",\n'
            '  "sentiment": "강세/약세/관망/중립 중 1개만 택일"\n'
            "}"
        )
        
        response = model.generate_content(prompt)
        
        raw_text = response.text.strip()
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()
        
        return json.loads(raw_text)
        
    except Exception as e:
        return {
            "summary": "내용이 너무 짧거나 시스템 알림 메일입니다.",
            "keyword": "기타",
            "analyst_view": "데이터 부족으로 판정 보류",
            "sentiment": "중립"
        }

def fetch_news(keyword):
    """구글 맞춤검색을 통한 최신 헤드라인 스캐닝"""
    if keyword in ['기타', '테스트', '분석 불가']:
        return ["관련 뉴스를 검색할 수 없는 내용입니다."]
        
    try:
        api_key = st.secrets["api_keys"]["google_search"]
        cx = st.secrets["api_keys"]["search_engine_id"]
        url = f"https://www.googleapis.com/customsearch/v1?key={api_key}&cx={cx}&q={keyword} 주식 OR 전망&num=3"
        res = requests.get(url, timeout=5).json()
        if 'items' in res:
            return [item['title'] for item in res['items']]
        return ["관련 최신 뉴스를 찾을 수 없습니다."]
    except:
        return ["뉴스 서버 응답 지연."]

# ==========================================
# 4. 실시간 감시 엔진 (Core Loop)
# ==========================================
def scan_and_process():
    service = get_gmail_service()
    if not service or not db: return 0

    query = 'is:unread'
    try:
        results = service.users().messages().list(userId='me', q=query, maxResults=3).execute()
        messages = results.get('messages', [])
    except Exception as e:
        return 0

    processed_count = 0
    for msg in messages:
        msg_id = msg['id']
        doc_ref = db.collection('daniel_reports').document(msg_id)
        
        if not doc_ref.get().exists:
            try:
                msg_data = service.users().messages().get(userId='me', id=msg_id).execute()
                headers = msg_data['payload']['headers']
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '제목 없음')
                snippet = msg_data.get('snippet', '')

                if not snippet.strip():
                    snippet = "내용이 없는 메일입니다."

                analysis = analyze_email_content(snippet)
                news_list = fetch_news(analysis.get('keyword', '경제'))

                doc_ref.set({
                    'id': msg_id,
                    'subject': subject,
                    'summary': analysis.get('summary'),
                    'analyst_view': analysis.get('analyst_view'),
                    'sentiment': analysis.get('sentiment'),
                    'news': news_list,
                    'timestamp': firestore.SERVER_TIMESTAMP
                })

                service.users().messages().modify(userId='me', id=msg_id, body={'removeLabelIds': ['UNREAD']}).execute()
                
                send_telegram(subject, analysis.get('summary'), analysis.get('sentiment'))
                
                processed_count += 1
            except Exception as e:
                continue

    return processed_count

# ==========================================
# 5. 모바일 대시보드 UI
# ==========================================
def main():
    st.markdown("<h2 style='color:#0f172a; text-align:center;'>Daniel's AI Minerva</h2>", unsafe_allow_html=True)
    st.caption("🔍 실시간 클라우드 감시 모듈이 가동 중입니다. (1분 주기, 안전 모드)")

    with st.spinner('새로운 데이터를 확인 중입니다...'):
        new_count = scan_and_process()
        if new_count > 0:
            st.success(f"주인님, {new_count}건의 새로운 텔레그램 알림 및 분석 보고서가 도착했습니다.")

    st.divider()

    if db:
        docs = db.collection('daniel_reports').order_by('timestamp', direction=firestore.Query.DESCENDING).stream()
        doc_list = list(docs)

        if not doc_list:
            st.info("현재 대기 중인 보고서가 없습니다. 평안한 시간 보내십시오, 주인님.")
        else:
            for doc in doc_list:
                data = doc.to_dict()
                with st.expander(f"📁 {data.get('subject', '제목 없음')} | 반응: {data.get('sentiment', '분석중')}"):
                    st.markdown(f"**미네르바 종합 요약:**\n{data.get('summary', '')}")
                    st.markdown(f"**월스트리트 & 애널리스트 동향:**\n{data.get('analyst_view', '')}")
                    
                    st.markdown("**관련 최신 헤드라인:**")
                    for idx, n in enumerate(data.get('news', [])):
                        st.markdown(f"{idx+1}. {n}")
                    
                    st.write("")
                    if st.button("✔️ 확인 완료 및 영구 파기", key=f"del_{data['id']}", use_container_width=True):
                        db.collection('daniel_reports').document(data['id']).delete()
                        st.rerun()
    else:
        st.warning("데이터베이스(Firebase) 연결 대기 중입니다.")

if __name__ == "__main__":
    main()
