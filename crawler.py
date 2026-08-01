import json
import os
import re
import urllib.parse
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

# 2. 차단 키워드 리스트
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

# 3. 한국 공식 아이템 번역 사전
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
    "Hamsters": "종이접기 햄스터",
    "Hamster": "종이접기 햄스터"
}

def search_web_for_coupon_status(scraper, code):
    """실시간 웹 검색을 통해 한국 커뮤니티/블로그 반응 분석 (만료 여부 & 한국어 보상)"""
    query = f"AFK 새로운 여정 {code}"
    encoded_query = urllib.parse.quote(query)
    search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
    
    is_expired = False
    korean_reward_text = ""
    
    try:
        res = scraper.get(search_url, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            snippets = soup.select(".result__snippet")
            
            combined_snippet = " ".join([s.get_text() for s in snippets])
            
            # 만료 감지 키워드 검사
            expired_keywords = ["만료", "종료", "사용불가", "사용 불가", "기간 지남", "지나서 안됨", "안되네요"]
            if any(kw in combined_snippet for kw in expired_keywords):
                # 단, '만료 안됨', '사용 가능' 문구가 같이 있는 경우 재검증
                if not ("만료 안됨" in combined_snippet or "사용 가능" in combined_snippet):
                    is_expired = True
                    
            # 한국어 보상 텍스트 패턴 추출 시도
            reward_matches = re.findall(r'(다이아|골드|에픽 초대장|일반 초대장|소환권|영웅의 정수|종이접기 햄스터)\s*\d+개?', combined_snippet)
            if reward_matches:
                korean_reward_text = ", ".join(list(dict.fromkeys(reward_matches)))
                
    except Exception as e:
        print(f"[{code}] 웹 검색 중 예외 발생: {e}")
        
    return is_expired, korean_reward_text

def translate_rewards_basic(text):
    """기본 영문 보상을 공식 한국어로 변환"""
    if not text:
        return "게임 아이템 보상"
        
    found_rewards = []
    items_pattern = r'(?:Epic Invite Letters?|Invite Letters?|Stellar Crystals?|Hero Essence|Soulstones?|Diamonds?|Gold|Summon Tickets?|Hamsters?)'
    
    pattern1 = re.compile(rf'({items_pattern})\s*x\s*(\d+k?)', re.IGNORECASE)
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
        return ", ".join(list(dict.fromkeys(found_rewards)))
        
    return "게임 아이템 보상"

def process_game_coupons(game_key, config):
    print(f"[{config['name']}] 실시간 웹 검색 기반 쿠폰 수집 시작...")
    file_name = config["file_name"]
    url = config["url"]
    
    existing_data = []
    if os.path.exists(file_name):
        try:
            with open(file_name, "r", encoding="utf-8") as f:
                raw_existing = json.load(f)
                for item in raw_existing:
                    code = item.get("code", "")
                    if code not in EXCLUDED_CODES and 5 <= len(code) <= 20:
                        existing_data.append(item)
        except Exception:
            existing_data = []

    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    
    raw_coupons = {}
    
    try:
        res = scraper.get(url, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            candidates = soup.find_all(['div', 'tr', 'li', 'td', 'p', 'span'])
            
            for cand in candidates:
                text = cand.get_text(separator=" ").strip()
                if len(text) > 250:
                    continue
                    
                codes = re.findall(r'\b[A-Z0-9]{5,20}\b', text)
                for code in codes:
                    if code in EXCLUDED_CODES:
                        continue
                    reward = translate_rewards_basic(text)
                    if code not in raw_coupons or (raw_coupons[code] == "게임 아이템 보상" and reward != "게임 아이템 보상"):
                        raw_coupons[code] = reward

    except Exception as e:
        print(f"[{config['name']}] 기본 수집 오류: {e}")

    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    coupon_dict = {item['code']: item for item in existing_data if 'code' in item}

    # 4. 각 쿠폰 코드별 실시간 웹 검색 수행
    for code, base_reward in raw_coupons.items():
        print(f"🔍 [{code}] 웹 검색으로 만료 여부 및 한국어 정보 확인 중...")
        is_expired, searched_reward = search_web_for_coupon_status(scraper, code)
        
        final_reward = searched_reward if searched_reward else base_reward
        
        if is_expired:
            # 웹 검색 결과 만료된 쿠폰
            if code in coupon_dict:
                coupon_dict[code]["status"] = "EXPIRED"
                if not coupon_dict[code].get("expired_at"):
                    coupon_dict[code]["expired_at"] = today_str
            else:
                coupon_dict[code] = {
                    "code": code,
                    "rewards": final_reward,
                    "status": "EXPIRED",
                    "created_at": today_str,
                    "expired_at": today_str
                }
        else:
            # 웹 검색 결과 사용 가능한 쿠폰
            if code not in coupon_dict:
                coupon_dict[code] = {
                    "code": code,
                    "rewards": final_reward,
                    "status": "ACTIVE",
                    "created_at": today_str,
                    "expired_at": None
                }
            else:
                coupon_dict[code]["rewards"] = final_reward
                coupon_dict[code]["status"] = "ACTIVE"
                coupon_dict[code]["expired_at"] = None

    # 5. 만료 후 7일 경과 데이터 완전 삭제
    updated_data = []
    for code, item in list(coupon_dict.items()):
        if item["status"] == "EXPIRED" and item.get("expired_at"):
            try:
                exp_dt = datetime.strptime(item["expired_at"], "%Y-%m-%d")
                if (today - exp_dt).days > 7:
                    continue # 7일 경과 시 목록에서 완전 삭제
            except Exception:
                pass
        updated_data.append(item)

    # JSON 저장
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(updated_data, f, ensure_ascii=False, indent=2)
    print(f"[{config['name']}] 웹 검색 검증 및 자동화 완료!")

if __name__ == "__main__":
    for game_key, config in GAMES_CONFIG.items():
        process_game_coupons(game_key, config)
