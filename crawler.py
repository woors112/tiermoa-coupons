import json
import os
import re
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup

# 1. 게임별 타겟 URL 및 저장 파일 설정
GAMES_CONFIG = {
    "afk-journey": {
        "name": "AFK 새로운 여정",
        "url": "https://www.afk.global/afk-journey/codes",
        "file_name": "afk_journey.json"
    }
}

# 2. 절대 쿠폰 코드가 아닌 상단 메뉴 / 시스템 단어 차단 리스트 (Blacklist)
EXCLUDED_CODES = {
    "OVERVIEW", "JOURNEY", "FEATURED", "CHARACTERS", "TIERLIST", "PATCH",
    "NOTES", "NEWS", "EVENTS", "DATABASES", "TERMS", "PRIVACY", "DISCORD",
    "REDDIT", "GLOBAL", "AFKJOURNEY", "REDEMPTION", "GUIDES", "DATABASE",
    "MODES", "RESOURCES", "COOKIES", "POLICY", "RIGHTS", "RESERVED", "SEARCH",
    "ACTIVE", "EXPIRED", "SHOW", "MORE", "LESS", "READ", "CLICK", "COPY",
    "REDEEM", "GAME", "CODE", "CODES", "LATEST", "BUILD", "UPDATE", "HOME",
    "CONTACT", "ABOUT", "ALL", "TIER", "LIST", "ITEM", "ITEMS", "HERO", "HEROES"
}

# 3. 영문 보상 ➔ 한국 공식 서비스 명칭 자동 변환 매핑
ITEM_TRANSLATIONS = {
    "Diamonds": "다이아",
    "Diamond": "다이아",
    "Gold": "골드",
    "Epic Invite Letters": "에픽 초대장",
    "Epic Invite Letter": "에픽 초대장",
    "Invite Letters": "일반 초대장",
    "Invite Letter": "일반 초대장",
    "Summon Tickets": "소환권",
    "Summon Ticket": "소환권",
    "Stellar Crystals": "별의 결정",
    "Stellar Crystal": "별의 결정",
    "Hero Essence": "영웅의 정수",
    "Soulstones": "영웅 영혼석",
    "Soulstone": "영웅 영혼석",
    "Hamsters": "햄스터",
    "Hamster": "햄스터"
}

def clean_and_translate_rewards(raw_text):
    """보상 텍스트 정제 및 한국어 공식 명칭 변환"""
    if not raw_text:
        return "게임 아이템 보상"
    
    # 날짜(예: 01.06.2026, 28.05.2026 등) 및 불필요한 단어 제거
    text = re.sub(r'\b\d{2}\.\d{2}\.\d{4}\b', '', raw_text)
    text = re.sub(r'(Copy|Copied|Active|Expired|Show expired codes)', '', text, flags=re.IGNORECASE)
    
    # 영문 아이템 한국어로 치환
    for eng, kor in ITEM_TRANSLATIONS.items():
        pattern = re.compile(re.escape(eng), re.IGNORECASE)
        text = pattern.sub(kor, text)
        
    # 수량 단위 예쁘게 정리 (x50k -> 5만개, x500 -> 500개)
    text = re.sub(r'x(\d+)k', r'\1만개', text, flags=re.IGNORECASE)
    text = re.sub(r'x(\d+)', r'\1개', text, flags=re.IGNORECASE)
    
    # 공백 및 구문 기호 정리
    text = re.sub(r'\s+', ' ', text).strip(', ')
    return text if len(text) > 0 and len(text) < 100 else "게임 아이템 보상"

def process_game_coupons(game_key, config):
    print(f"[{config['name']}] 쿠폰 수집 시작...")
    file_name = config["file_name"]
    url = config["url"]
    
    # 기존 데이터 불러오기
    if os.path.exists(file_name):
        try:
            with open(file_name, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except Exception:
            existing_data = []
    else:
        existing_data = []

    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    
    scraped_coupons = {}
    
    try:
        res = scraper.get(url, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            
            # 텍스트 길이가 250자 이하인 개별 카드/행 상자만 정밀 타겟팅
            candidates = soup.find_all(['div', 'tr', 'li', 'td'])
            
            for cand in candidates:
                text = cand.get_text(separator=" ").strip()
                
                # 자식 요소가 너무 많거나 200자 이상인 큰 틀(전체 메뉴/페이지)은 스킵
                if len(text) > 200:
                    continue
                
                # 5~20자 영문 대문자+숫자 쿠폰 패턴 추출
                codes = re.findall(r'\b[A-Z0-9]{5,20}\b', text)
                
                for code in codes:
                    # 차단 리스트에 포함된 메뉴 이름이면 제외
                    if code in EXCLUDED_CODES:
                        continue
                    
                    # 보상 텍스트 정제
                    raw_reward = text.replace(code, "").strip()
                    translated_reward = clean_and_translate_rewards(raw_reward)
                    
                    if code not in scraped_coupons:
                        scraped_coupons[code] = translated_reward

    except Exception as e:
        print(f"[{config['name']}] 크롤링 오류: {e}")

    print(f"수집된 진짜 쿠폰 개수: {len(scraped_coupons)}개")

    # 3단계 라이프사이클 처리
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    coupon_dict = {item['code']: item for item in existing_data if 'code' in item}

    # A. 신규 및 활성 쿠폰 반영
    for code, rewards in scraped_coupons.items():
        if code not in coupon_dict:
            coupon_dict[code] = {
                "code": code,
                "rewards": rewards,
                "status": "ACTIVE",
                "created_at": today_str,
                "expired_at": None
            }
        else:
            coupon_dict[code]["rewards"] = rewards
            if coupon_dict[code]["status"] == "EXPIRED":
                coupon_dict[code]["status"] = "ACTIVE"
                coupon_dict[code]["expired_at"] = None

    # B. 만료 처리 및 7일 후 삭제
    scraped_set = set(scraped_coupons.keys())
    updated_data = []

    for code, item in list(coupon_dict.items()):
        if code not in scraped_set and item["status"] == "ACTIVE":
            item["status"] = "EXPIRED"
            item["expired_at"] = today_str

        if item["status"] == "EXPIRED" and item.get("expired_at"):
            try:
                expired_date = datetime.strptime(item["expired_at"], "%Y-%m-%d")
                if (today - expired_date).days > 7:
                    continue # 7일 경과 시 삭제
            except Exception:
                pass

        updated_data.append(item)

    # JSON 저장
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(updated_data, f, ensure_ascii=False, indent=2)
    print(f"[{config['name']}] 정밀 수집 완료!")

if __name__ == "__main__":
    for game_key, config in GAMES_CONFIG.items():
        process_game_coupons(game_key, config)
