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

# 2. 쿠폰 코드가 절대 될 수 없는 상단 메뉴 / 시스템 단어 차단 리스트 (Blacklist)
EXCLUDED_CODES = {
    "OVERVIEW", "JOURNEY", "FEATURED", "CHARACTERS", "TIERLIST", "PATCH",
    "NOTES", "NEWS", "EVENTS", "DATABASES", "TERMS", "PRIVACY", "DISCORD",
    "REDDIT", "GLOBAL", "AFKJOURNEY", "REDEMPTION", "GUIDES", "DATABASE",
    "MODES", "RESOURCES", "COOKIES", "POLICY", "RIGHTS", "RESERVED", "SEARCH",
    "ACTIVE", "EXPIRED", "SHOW", "MORE", "LESS", "READ", "CLICK", "COPY",
    "REDEEM", "GAME", "CODE", "CODES", "LATEST", "BUILD", "UPDATE", "HOME",
    "CONTACT", "ABOUT", "ALL", "TIER", "LIST", "ITEM", "ITEMS", "HERO", "HEROES",
    "HTTPS", "WWW", "AFK", "LILITH", "GAMES", "COMMUNITY", "SUMMON", "TICKETS"
}

# 3. 영문 보상 ➔ 한국 공식 서비스 명칭 단어 사전
ITEM_TRANSLATIONS = {
    "Epic Invite Letters": "에픽 초대장",
    "Epic Invite Letter": "에픽 초대장",
    "Invite Letters": "일반 초대장",
    "Invite Letter": "일반 초대장",
    "Stellar Crystals": "별의 결정",
    "Stellar Crystal": "별의 결정",
    "Summon Tickets": "소환권",
    "Summon Ticket": "소환권",
    "Diamonds": "다이아",
    "Diamond": "다이아",
    "Gold": "골드",
    "Hero Essence": "영웅의 정수",
    "Soulstones": "영웅 영혼석",
    "Soulstone": "영웅 영혼석",
    "Hamsters": "햄스터",
    "Hamster": "햄스터"
}

def extract_and_translate_rewards(text):
    """텍스트에서 실제 인게임 보상 항목만 정밀하게 추출하여 한국어로 변환"""
    if not text:
        return "게임 아이템 보상"
        
    found_rewards = []
    
    items_pattern = r'(?:Epic Invite Letters?|Invite Letters?|Stellar Crystals?|Hero Essence|Soulstones?|Diamonds?|Gold|Summon Tickets?|Hamsters?)'
    
    # 패턴 1: 아이템 x수량 (예: Diamonds x500, Gold x50k, Epic Invite Letters x5)
    pattern1 = re.compile(rf'({items_pattern})\s*x\s*(\d+k?)', re.IGNORECASE)
    # 패턴 2: 수량 아이템 (예: 10 Summon Tickets)
    pattern2 = re.compile(rf'(\d+)\s*({items_pattern})', re.IGNORECASE)
    
    for match in pattern1.finditer(text):
        item_raw, qty_raw = match.group(1), match.group(2)
        translated_item = "아이템"
        for eng, kor in ITEM_TRANSLATIONS.items():
            if eng.lower() == item_raw.lower():
                translated_item = kor
                break
        
        qty_str = qty_raw.lower().replace('k', '만개')
        if not qty_str.endswith('만개'):
            qty_str += '개'
        found_rewards.append(f"{translated_item} {qty_str}")
        
    for match in pattern2.finditer(text):
        qty_raw, item_raw = match.group(1), match.group(2)
        translated_item = "아이템"
        for eng, kor in ITEM_TRANSLATIONS.items():
            if eng.lower() == item_raw.lower():
                translated_item = kor
                break
        found_rewards.append(f"{translated_item} {qty_raw}개")
        
    if found_rewards:
        # 중복 제거 및 깔끔한 출력
        unique_rewards = list(dict.fromkeys(found_rewards))
        return ", ".join(unique_rewards)
    
    return "게임 아이템 보상"

def process_game_coupons(game_key, config):
    print(f"[{config['name']}] 쿠폰 정밀 수집 시작...")
    file_name = config["file_name"]
    url = config["url"]
    
    # 기존 데이터 불러오기
    existing_data = []
    if os.path.exists(file_name):
        try:
            with open(file_name, "r", encoding="utf-8") as f:
                raw_existing = json.load(f)
                # 기존 데이터 중 메뉴 단어나 쓰레기 데이터 즉시 정화(삭제)
                for item in raw_existing:
                    code = item.get("code", "")
                    rewards = item.get("rewards", "")
                    if code in EXCLUDED_CODES or len(code) < 5 or len(code) > 20:
                        continue
                    if any(noise in rewards.lower() for noise in ["overview", "patch notes", "privacy", "lilith"]):
                        continue
                    existing_data.append(item)
        except Exception:
            existing_data = []

    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    
    scraped_coupons = {}
    
    try:
        res = scraper.get(url, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            
            # 1단계: HTML 카드 및 요소 탐색
            candidates = soup.find_all(['div', 'tr', 'li', 'td', 'p', 'span'])
            
            for cand in candidates:
                text = cand.get_text(separator=" ").strip()
                
                # 대문자 영문+숫자 5~20자리 쿠폰 코드 찾기
                codes = re.findall(r'\b[A-Z0-9]{5,20}\b', text)
                
                for code in codes:
                    # 차단 단어 제외
                    if code in EXCLUDED_CODES:
                        continue
                    
                    # 보상 추출
                    reward = extract_and_translate_rewards(text)
                    
                    # 더 구체적인 보상 정보로 업데이트
                    if code not in scraped_coupons or (scraped_coupons[code] == "게임 아이템 보상" and reward != "게임 아이템 보상"):
                        scraped_coupons[code] = reward

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

    # B. 사라진 쿠폰 만료 처리 및 7일 후 삭제
    scraped_set = set(scraped_coupons.keys())
    updated_data = []

    for code, item in list(coupon_dict.items()):
        if code not in scraped_set and item["status"] == "ACTIVE":
            item["status"] = "EXPIRED"
            item["expired_at"] = today_str

        # 만료된 지 7일 경과 여부 확인
        if item["status"] == "EXPIRED" and item.get("expired_at"):
            try:
                expired_date = datetime.strptime(item["expired_at"], "%Y-%m-%d")
                if (today - expired_date).days > 7:
                    continue # 7일 경과 시 완전 삭제
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
