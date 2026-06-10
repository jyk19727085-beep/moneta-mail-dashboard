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
# 1. UI 설정 및 자동 새로고침 (클라우드 감시)
# ==========================================
st.set_page_config(page_title="Minerva AI Dashboard", page_icon="📈", layout="centered")

# 60초(60000ms)마다 백그라운드 엔진 가동 (최소 간격)
st_autorefresh(interval=60000, limit=None, key="auto_scanner")

# ==========================================
# 2. 3중 검증된 API 및 DB 초기화
# ==========================================
@st.cache_resource
def init_firebase():
    """Firebase DB 연결 (이미 연결되어 있다면 재사용하여 충돌 방지)"""
    try:
        if not firebase_admin._apps:
            cred_dict = dict(st.secrets["firebase"])
            # Streamlit secrets의 줄바꿈 문자 처리 (오류 방지 핵심)
            cred_dict["private_key"] = cred_dict["private_key"].replace('\\n', '\n')
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initializeApp(cred)
        return firestore.client()
    except Exception as e:
        st.error(f"데이터베이스 연결 오류: {e}")
        return None

db = init_firebase()

# Gemini AI 초기화
try:
    genai.configure(api_key=st.secrets["api_keys"]["gemini"])
except Exception as e:
    st.error("AI 엔진 초기화 실패. 키 설정을 확인해 주십시오.")

# ==========================================
# 3. 비서 미네르바의 분석 및 알림 모듈
# ==========================================
def send_telegram(subject, summary):
    """모바일 즉시 푸시 알림 전송 (오류 발생 시에도 대시보드는 멈추지 않음)"""
    try:
        bot_token = st.secrets["api_keys"]["telegram_bot_token"]
        chat_id = st.secrets["api_keys"]["telegram_chat_id"]
        if not bot_token or not chat_id: return
        
        text = f"🔔 [새로운 투자 분석 보고서]\n\n📌 제목: {subject}\n📝 요약: {summary}\n\n주인님, 대시보드에 접속하여 확인해 주십시오."
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(url, data={'chat_id': chat_id, 'text': text}, timeout=5)
    except Exception as e:
        print(f"알림 전송 실패 (무시됨): {e}")

def get_gmail_service():
    """OAuth 토큰을 이용한 Gmail 서비스 연결"""
    try:
        creds_data = dict(st.secrets["gmail_oauth"])
        creds_data["token_uri"] = "https://oauth2.googleapis.com/token"
        creds = Credentials.from_authorized_user_info(creds_data)
        return build('gmail', 'v1', credentials=creds)
    except Exception as e:
        st.error(f"이메일 서버 연결 실패: {e}")
        return None

def analyze_email_content(text_content):
    """냉철하고 객관적인 AI 분석 로직 (가중치 55% 객관성)"""
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"""
        주인님(Daniel, 59세 남성)은 경제, 주식, 신기술, 스포츠에 관심이 많습니다.
        철저히 냉철하고 객관적인 데이터(가중치 55% 이상)를 선호하십니다.
        다음 텍스트를 분석하여 반드시 아래 형태의 JSON으로만 반환하십시오. 다른 설명은 생략합니다.
        
        "{text_content}"
        
        형식:
        {{
            "summary": "객관적 사실 위주의 핵심 요약 (2문장 이내)",
            "keyword": "주요 검색 키워드 1개 (예: 엔비디아, 연준 금리)",
            "analyst_view": "관련 월가/전문가들의 객관적 컨센서스 (알 수 없으면 '판단 보류')",
            "sentiment": "시장 반응 (강세/약세/관망/중립 중 택 1)"
        }}
        """
        response = model.generate_content(prompt)
        raw_text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(raw_text)
    except Exception as e:
        return {"summary": "AI 분석 지연 (데이터 복잡성)", "keyword": "경제", "analyst_view": "데이터 부족으로 판정 불가", "sentiment": "중립"}

def fetch_news(keyword):
    """구글 맞춤검색을 통한 관련 뉴스 수집"""
    try:
        api_key = st.secrets["api_keys"]["google_search"]
        cx = st.secrets["api_keys"]["search_engine_id"]
        url = f"https://www.googleapis.com/customsearch/v1?key={api_key}&cx={cx}&q={keyword} 주식 OR 전망&num=3"
        res = requests.get(url, timeout=5).json()
        if 'items' in res:
            return [item['title'] for item in res['items']]
        return ["관련 뉴스를 찾을 수 없습니다."]
    except:
        return ["뉴스 서버 응답 지연."]

# ==========================================
# 4. 실시간 감시 엔진 (Core Loop)
# ==========================================
def scan_and_process():
    service = get_gmail_service()
    if not service or not db: return 0

    # 읽지 않은 새 메일 중 두 계정 수신 메일만 추출
    query = 'is:unread (to:jyk19727085@gmail.com OR to:gmaster7085@gmail.com)'
    try:
        results = service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])
    except Exception as e:
        return 0

    processed_count = 0
    for msg in messages:
        msg_id = msg['id']
        doc_ref = db.collection('daniel_reports').document(msg_id)
        
        # 중복 처리 방지
        if not doc_ref.get().exists:
            try:
                # 1. 메일 내용 가져오기
                msg_data = service.users().messages().get(userId='me', id=msg_id).execute()
                headers = msg_data['payload']['headers']
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '제목 없음')
                snippet = msg_data.get('snippet', '')

                # 2. 미네르바 AI 분석 & 뉴스 매칭
                analysis = analyze_email_content(snippet)
                news_list = fetch_news(analysis.get('keyword', '경제'))

                # 3. DB 저장
                doc_ref.set({
                    'id': msg_id,
                    'subject': subject,
                    'summary': analysis.get('summary'),
                    'analyst_view': analysis.get('analyst_view'),
                    'sentiment': analysis.get('sentiment'),
                    'news': news_list,
                    'timestamp': firestore.SERVER_TIMESTAMP
                })

                # 4. 읽음 처리 (UNREAD 라벨 제거)
                service.users().messages().modify(userId='me', id=msg_id, body={'removeLabelIds': ['UNREAD']}).execute()

                # 5. 모바일 알림 전송
                send_telegram(subject, analysis.get('summary'))
                processed_count += 1
            except Exception as e:
                print(f"메일 처리 중 오류 발생: {e}")
                continue # 한 메일에서 오류가 나도 다음 메일을 계속 처리하도록 보장

    return processed_count

# ==========================================
# 5. 모바일 대시보드 UI
# ==========================================
def main():
    st.markdown("<h2 style='color:#0f172a; text-align:center;'>Daniel's AI Minerva</h2>", unsafe_allow_html=True)
    st.caption("🔍 실시간 클라우드 감시 모듈이 가동 중입니다. (1분 주기)")

    # 시스템 스캔 실행 (화면이 새로고침 될 때마다 실행됨)
    with st.spinner('새로운 데이터를 확인 중입니다...'):
        new_count = scan_and_process()
        if new_count > 0:
            st.success(f"주인님, {new_count}건의 새로운 분석 보고서가 도착했습니다.")

    st.divider()

    # DB에서 분석된 데이터 불러오기
    if db:
        docs = db.collection('daniel_reports').order_by('timestamp', direction=firestore.Query.DESCENDING).stream()
        doc_list = list(docs)

        if not doc_list:
            st.info("현재 대기 중인 보고서가 없습니다. 평안한 시간 보내십시오, 주인님.")
        else:
            for doc in doc_list:
                data = doc.to_dict()
                # 아코디언 스타일로 접었다 펼치는 직관적인 모바일 UI
                with st.expander(f"📁 {data.get('subject', '제목 없음')} | 반응: {data.get('sentiment', '분석중')}"):
                    st.markdown(f"**미네르바 종합 요약:**\n{data.get('summary', '')}")
                    st.markdown(f"**월스트리트 & 애널리스트 동향:**\n{data.get('analyst_view', '')}")
                    
                    st.markdown("**관련 최신 헤드라인:**")
                    for idx, n in enumerate(data.get('news', [])):
                        st.markdown(f"{idx+1}. {n}")
                    
                    st.write("") # 여백
                    # 주인님 요청: 확인 후 즉시 삭제 (보안 파기) 기능
                    if st.button("✔️ 확인 완료 및 영구 파기", key=f"del_{data['id']}", use_container_width=True):
                        db.collection('daniel_reports').document(data['id']).delete()
                        st.rerun() # 삭제 직후 화면 강제 새로고침
    else:
        st.warning("데이터베이스(Firebase) 연결 대기 중입니다. 키 설정을 완료해 주십시오.")

if __name__ == "__main__":
    main()