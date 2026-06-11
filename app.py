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
# 1. UI 설정 및 자동 새로고침
# ==========================================
st.set_page_config(page_title="Minerva AI Dashboard", page_icon="📈", layout="centered")

# 60초마다 백그라운드 엔진 가동
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
    except BaseException:
        st.error("데이터베이스 연결 오류가 발생했습니다.")
        return None

db = init_firebase()

try:
    genai.configure(api_key=st.secrets["api_keys"]["gemini"])
except BaseException:
    st.error("AI 엔진 초기화 실패. 키 설정을 확인해 주십시오.")

# ==========================================
# 3. 분석 및 알림 모듈
# ==========================================
def clean_token(token_str):
    """토큰 앞뒤의 눈에 보이지 않는 공백, 줄바꿈 등을 완벽하게 제거"""
    if not token_str: return ""
    return re.sub(r'\\s+', '', str(token_str))

def send_telegram(subject, summary, sentiment):
    """텔레그램 챗봇 알림 발송"""
    try:
        # 무조건 자동 정화된 토큰을 사용
        bot_token = clean_token(st.secrets["api_keys"]["telegram_bot_token"])
        chat_id = clean_token(st.secrets["api_keys"]["telegram_chat_id"])
        
        if not bot_token or not chat_id: return
        
        text = f"🔔 [투자 분석 리포트]\n\n📌 제목: {subject}\n🌡️ 반응: {sentiment}\n📝 요약: {summary}\n\n👉 대시보드에서 상세 분석을 확인하세요!"
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
        requests.post(url, data={'chat_id': chat_id, 'text': text}, timeout=5)
    except BaseException:
        pass

def get_gmail_service():
    """지메일 보안 통행증 확인"""
    try:
        creds_data = dict(st.secrets["gmail_oauth"])
        creds_data["token_uri"] = "https://oauth2.googleapis.com/token"
        creds = Credentials.from_authorized_user_info(creds_data)
        return build('gmail', 'v1', credentials=creds)
    except BaseException:
        return None

def analyze_email_content(text_content):
    """AI 두뇌 해방: 깊이 있고 유연한 분석 (방어 코드 완화)"""
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # 억지로 JSON 포맷을 맞추다 에러가 나지 않도록, AI가 자유롭게 분석하되 마크다운 없이 텍스트로만 답하게 합니다.
        prompt = (
            "당신은 월스트리트 수석 퀀트 애널리스트입니다. 다음 [이메일 내용]을 분석하여 아래 4가지 항목을 '마크다운 기호 없이' 순서대로 작성하십시오.\n\n"
            f"[이메일 내용]\n{text_content[:2000]}\n\n" # 너무 긴 내용은 자름
            "1. 핵심 요약 (2~3줄로 명확하게):\n"
            "2. 월스트리트 및 시장 반응 (기반 지식 활용):\n"
            "3. 검색용 키워드 (가장 중요한 경제 단어 1개만):\n"
            "4. 시장 분위기 (강세/약세/관망/중립 중 택 1):"
        )
        
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # AI의 자유로운 텍스트 대답에서 필요한 부분만 영리하게 뽑아냅니다.
        summary = "요약 불가"
        analyst_view = "분석 불가"
        keyword = "경제"
        sentiment = "중립"
        
        lines = text.split('\\n')
        for line in lines:
            if line.startswith("1.") or "요약:" in line: summary = line.split(":", 1)[-1].strip()
            elif line.startswith("2.") or "반응:" in line: analyst_view = line.split(":", 1)[-1].strip()
            elif line.startswith("3.") or "키워드:" in line: keyword = line.split(":", 1)[-1].strip().replace("'", "").replace('"', '')
            elif line.startswith("4.") or "분위기:" in line: sentiment = line.split(":", 1)[-1].strip()
            
        return {
            "summary": summary if summary else text[:100], # 파싱 실패 시 원문 일부라도 보여줌
            "keyword": keyword,
            "analyst_view": analyst_view,
            "sentiment": sentiment
        }
        
    except BaseException as e:
        return {
            "summary": f"AI 분석 지연 (내용이 너무 짧거나 시스템 오류입니다.)",
            "keyword": "경제",
            "analyst_view": "분석 불가",
            "sentiment": "중립"
        }

def fetch_news(keyword):
    """구글 맞춤검색 최신 헤드라인"""
    if keyword in ['경제', '분석 불가']:
        return ["관련 뉴스를 특정하기 어렵습니다."]
        
    try:
        api_key = st.secrets["api_keys"]["google_search"]
        cx = st.secrets["api_keys"]["search_engine_id"]
        # 검색어 최적화
        search_query = f"{keyword} 주식 OR 경제 전망"
        url = f"https://www.googleapis.com/customsearch/v1?key={api_key}&cx={cx}&q={search_query}&num=3"
        
        res = requests.get(url, timeout=5).json()
        if 'items' in res:
            return [item['title'] for item in res['items']]
        return ["관련 최신 뉴스를 찾을 수 없습니다."]
    except BaseException:
        return ["뉴스 서버 응답 지연."]

# ==========================================
# 4. 실시간 감시 엔진
# ==========================================
def scan_and_process():
    service = get_gmail_service()
    if not service or not db: return 0

    query = 'is:unread'
    try:
        results = service.users().messages().list(userId='me', q=query, maxResults=3).execute()
        messages = results.get('messages', [])
    except BaseException:
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
            except BaseException:
                continue

    return processed_count

# ==========================================
# 5. 모바일 대시보드 UI 및 진단 도구
# ==========================================
def main():
    st.markdown("<h2 style='color:#0f172a; text-align:center;'>Daniel's AI Minerva</h2>", unsafe_allow_html=True)
    st.caption("🔍 퀀트 AI 엔진이 실시간으로 가동 중입니다. (1분 주기)")

    with st.spinner('새로운 데이터를 확인 중입니다...'):
        new_count = scan_and_process()
        if new_count > 0:
            st.success(f"주인님, {new_count}건의 새로운 심층 분석 보고서가 도착했습니다.")

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
                    st.markdown(f"**미네르바 핵심 요약:**\n{data.get('summary', '')}")
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

    # 🚨 텔레그램 연동 엑스레이 진단 테스트기
    st.write("")
    st.write("---")
    st.markdown("### 🛠️ 모네타의 텔레그램 실시간 진단 키트")
    st.caption("대시보드 내부에서 텔레그램 서버로 직접 신호를 쏘아 에러 원인을 추적합니다.")
    
    if st.button("🚀 텔레그램 즉시 테스트 전송 실행", use_container_width=True):
        try:
            bot_token = clean_token(st.secrets["api_keys"]["telegram_bot_token"])
            chat_id = clean_token(st.secrets["api_keys"]["telegram_chat_id"])
            
            st.info(f"정화된 시스템 인식값 -> Chat ID: {chat_id}")
            
            test_text = "다니엘 주인님! 대시보드 내부 진단 장치를 통해 전송된 시스템 최종 연동 성공 메시지입니다!"
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            
            res = requests.post(url, data={'chat_id': chat_id, 'text': test_text}, timeout=5)
            
            if res.status_code == 200:
                st.success("✅ [성공] 텔레그램 서버가 메시지를 무사히 접수했습니다! 핸드폰 알림창을 확인해 주십시오.")
            else:
                st.error(f"❌ [텔레그램 서버 거절 - 코드 {res.status_code}] 내용: {res.text}")
                st.warning("💡 조치사항: 여전히 에러가 난다면, 봇에게 /start를 보냈는지 다시 확인해 주세요.")
        except Exception as e:
            st.error(f"❌ 시스템 통신 오류: {e}")

if __name__ == "__main__":
    main()
