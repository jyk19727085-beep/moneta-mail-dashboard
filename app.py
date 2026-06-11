import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import requests
import json
import datetime
from streamlit_autorefresh import st_autorefresh

# ==========================================
# 1. UI 설정 및 자동 새로고침
# ==========================================
st.set_page_config(page_title="Minerva AI Dashboard", page_icon="📈", layout="centered")
st_autorefresh(interval=60000, limit=None, key="auto_scanner")

# ==========================================
# 2. API 및 DB 초기화
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
    except Exception as e:
        st.error(f"🚨 [DB 연결 실패] {e}")
        return None

db = init_firebase()

try:
    genai.configure(api_key=st.secrets["api_keys"]["gemini"])
except Exception as e:
    st.error(f"🚨 [AI 엔진 오류] {e}")

# ==========================================
# 3. 비서 미네르바 분석 및 알림 모듈
# ==========================================
def send_telegram(subject, summary):
    try:
        bot_token = st.secrets["api_keys"]["telegram_bot_token"]
        chat_id = st.secrets["api_keys"]["telegram_chat_id"]
        if not bot_token or not chat_id: return
        
        text = f"🔔 [새로운 투자 분석 보고서]\n\n📌 제목: {subject}\n📝 요약: {summary}\n\n주인님, 대시보드에 접속하여 확인해 주십시오."
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(url, data={'chat_id': chat_id, 'text': text}, timeout=5)
    except Exception as e:
        st.error(f"🚨 [텔레그램 전송 실패] {e}")

def get_gmail_service():
    try:
        creds_data = dict(st.secrets["gmail_oauth"])
        creds_data["token_uri"] = "https://oauth2.googleapis.com/token"
        creds = Credentials.from_authorized_user_info(creds_data)
        return build('gmail', 'v1', credentials=creds)
    except Exception as e:
        st.error(f"🚨 [이메일 권한 거부됨] {e}")
        return None

def analyze_email_content(text_content):
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"""
        주인님(Daniel, 59세 남성)은 경제, 주식, 신기술, 스포츠에 관심이 많습니다.
        철저히 냉철하고 객관적인 데이터(가중치 55% 이상)를 선호하십니다.
        다음 텍스트를 분석하여 반드시 아래 형태의 JSON으로만 반환하십시오. 다른 설명은 생략합니다.
        "{text_content}"
        형식: {{"summary": "요약", "keyword": "키워드", "analyst_view": "전문가 의견", "sentiment": "시장 반응"}}
        """
        response = model.generate_content(prompt)
        raw_text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(raw_text)
    except Exception as e:
        return {"summary": f"AI 분석 지연: {e}", "keyword": "경제", "analyst_view": "판정 불가", "sentiment": "중립"}

def fetch_news(keyword):
    try:
        api_key = st.secrets["api_keys"]["google_search"]
        cx = st.secrets["api_keys"]["search_engine_id"]
        url = f"https://www.googleapis.com/customsearch/v1?key={api_key}&cx={cx}&q={keyword} 주식 OR 전망&num=3"
        res = requests.get(url, timeout=5).json()
        if 'items' in res:
            return [item['title'] for item in res['items']]
        return ["관련 뉴스를 찾을 수 없습니다."]
    except Exception as e:
        return [f"뉴스 서버 응답 오류: {e}"]

# ==========================================
# 4. 실시간 감시 엔진 (엑스레이 디버그 장착)
# ==========================================
def scan_and_process():
    service = get_gmail_service()
    if not service: return 0, "❌ 지메일 API 서비스에 접속할 수 없습니다. (토큰 오류 가능성)"
    if not db: return 0, "❌ 데이터베이스가 준비되지 않았습니다."

    # [핵심] 현재 모네타가 접속한 계정이 무엇인지 강제 확인
    try:
        profile = service.users().getProfile(userId='me').execute()
        connected_email = profile.get('emailAddress', '알 수 없음')
    except Exception as e:
        return 0, f"❌ 접속 계정 확인 실패: {e}"

    query = 'is:unread'
    try:
        results = service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])
    except Exception as e:
        st.error(f"🚨 [지메일 스캔 중 오류] {e}")
        return 0, f"❌ 메일함 읽기 실패: {e}"

    # 디버그 보고서 생성
    debug_info = f"✅ **연결된 계정:** `{connected_email}`\n✅ **발견된 새 메일 개수:** `{len(messages)}`개"

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
                send_telegram(subject, analysis.get('summary'))
                processed_count += 1
            except Exception as e:
                st.error(f"🚨 [메일 처리 중 상세 오류] 메일 제목: {subject} / 에러: {e}")

    return processed_count, debug_info

# ==========================================
# 5. 모바일 대시보드 UI
# ==========================================
def main():
    st.markdown("<h2 style='color:#0f172a; text-align:center;'>Daniel's AI Minerva</h2>", unsafe_allow_html=True)
    st.caption("🔍 실시간 클라우드 감시 모듈이 가동 중입니다. (1분 주기)")

    debug_msg = "대기 중..."
    with st.spinner('새로운 데이터를 확인 중입니다...'):
        new_count, debug_msg = scan_and_process()
        if new_count > 0:
            st.success(f"주인님, {new_count}건의 새로운 분석 보고서가 도착했습니다.")

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

    # ----------------------------------------------------
    # 모네타의 특별 진단 시스템 (원인 규명용)
    # ----------------------------------------------------
    st.divider()
    with st.expander("🛠 모네타의 시스템 진단 리포트 (엑스레이 모드)"):
        st.markdown(debug_msg)
        st.caption("※ 만약 위 '연결된 계정'이 주인님이 생각하시는 계정과 다르다면, 다른 계정의 토큰이 입력된 것입니다.")
        st.caption("※ 만약 발견된 메일이 0개라면, 해당 계정의 편지함이 비어있거나 구글이 외부 접근을 막은 상태입니다.")

if __name__ == "__main__":
    main()
