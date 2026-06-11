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

# 60초(60000ms)마다 백그라운드 엔진 가동 (무한 루프 방지)
st_autorefresh(interval=60000, limit=None, key="auto_scanner")

# ==========================================
# 2. API 및 DB 초기화
# ==========================================
@st.cache_resource
def init_firebase():
    """Firebase DB 연결 (중복 연결 충돌 완벽 방지)"""
    try:
        if not firebase_admin._apps:
            cred_dict = dict(st.secrets["firebase"])
            # 프라이빗 키 줄바꿈 오류 원천 차단
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
    """텔레그램 챗봇 알림 발송 (확실한 검증 로직)"""
    try:
        bot_token = st.secrets["api_keys"]["telegram_bot_token"]
        chat_id = st.secrets["api_keys"]["telegram_chat_id"]
        if not bot_token or not chat_id: return
        
        # 스마트폰에서 보기 좋게 이모지와 함께 정렬된 알림 메시지
        text = f"🔔 [새로운 투자 분석 보고서 도착]\n\n📌 제목: {subject}\n🌡️ 시장 반응: {sentiment}\n📝 요약: {summary}\n\n👉 주인님, 대시보드에 접속하여 심층 분석을 확인해 주십시오."
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
        # 텔레그램 서버로 쏘아 올림
        response = requests.post(url, data={'chat_id': chat_id, 'text': text}, timeout=5)
        response.raise_for_status() # 전송 실패 시 예외 발생
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
    """강력하게 통제된 AI 분석 로직 (에러 원천 차단)"""
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"""
        당신은 냉철한 AI 금융 비서입니다. 아래 [이메일 내용]을 분석하여 정확히 JSON 형식으로만 대답하십시오.
        어떤 경우에도 부연 설명이나 마크다운 기호(```json)를 넣지 마십시오. 오직 순수 JSON 데이터만 출력해야 합니다.

        [이메일 내용]
        "{text_content}"

        [출력 JSON 구조]
        {{
            "summary": "메일의 핵심 1~2줄 요약 (내용이 짧으면 그대로 요약)",
            "keyword": "검색용 핵심 경제 단어 1개 (예: 반도체, 금리, 테스트 등)",
            "analyst_view": "내용에 기반한 시장/전문가 예상 반응 (내용이 너무 짧으면 '단순 알림이므로 판단 보류'로 기재)",
            "sentiment": "강세/약세/관망/중립 중 1개만 택일"
        }}
        """
        response = model.generate_content(prompt)
        
        # AI가 규칙을 어겼을 경우를 대비한 강력한 찌꺼기 제거 필터
        raw_text = response.text.strip()
        if raw_text.startswith('
