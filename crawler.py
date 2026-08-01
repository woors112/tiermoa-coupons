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

# 2. 쿠폰 코드가 절대 될 수 없는 사이트 메뉴 단어 차단 리스트 (Blacklist)
EXCLUDED_CODES = {
    "OVERVIEW", "JOURNEY", "FEATURED", "CHARACTERS", "TIERLIST", "PATCH",
    "NOTES", "NEWS", "EVENTS", "DATABASES", "TERMS", "PRIVACY", "DISCORD",
    "REDDIT", "GLOBAL", "AFKJOURNEY", "REDEMPTION", "GUIDES", "DATABASE",
    "MODES", "RESOURCES", "COOKIES", "POLICY", "RIGHTS", "RESERVED", "SEARCH",
    "ACTIVE", "EXPIRED", "SHOW", "MORE", "LESS", "READ", "CLICK", "COPY",
    "REDEEM", "GAME", "CODE", "CODES", "LATEST", "BUILD", "UPDATE", "HOME",
    "CONTACT", "ABOUT", "ALL", "TIER", "LIST", "ITEM", "ITEMS", "HERO", "HEROES",
    "HTTPS", "WWW", "AFK", "LILITH", "GAMES", "COMMUNITY", "SUMMON", "TICKETS",
    "ARENA", "MOBILE", "ANDROID", "APPLE", "GOOGLE", "STORE", "PLAY", "ONLINE"
}

# 3. 한국 서비스 공식 아이템 명칭 단어 사전
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

def extract_and_translate_rewards(text):
    """텍스트에서 실제 인게임 보상 항목만 정밀 추출하여 한국어로 변환"""
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
    print(f"[{config['name']}] 정밀 구역 분리 수집 시작...")
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
    
    active_coupons = {}
    expired_coupons = {}
    
    try:
        res = scraper.get(url, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            html_content = str(soup)
            
            # Active codes 구역과 Expired codes 구역 정밀 분리
            active_section = ""
            expired_section = ""
            
            active_match = re.search(r'Active\s*codes.*?(?=Expired\s*codes|Show\s*expired|How\s*to\s*redeem|$)', html_content, re.IGNORECASE | re.DOTALL)
            if active_match:
                active_section = active_match.group(0)
            else:
                active_section = html_content

            expired_match = re.search(r'(?:Expired\s*codes|Show\s*expired).*', html_content, re.IGNORECASE | re.DOTALL)
            if expired_match:
                expired_section = expired_match.group(0)

            # 1. 활성 쿠폰 구역 파싱
            active_soup = BeautifulSoup(active_section, "html.parser")
            for cand in active_soup.find_all(['div', 'tr', 'li', 'td', 'p']):
                text = cand.get_text(separator=" ").strip()
                if len(text) > 250:
                    continue
                codes = re.findall(r'\b[A-Z0-9]{5,20}\b', text)
                for code in codes:
                    if code in EXCLUDED_CODES:
                        continue
                    reward = extract_and_translate_rewards(text)
                    if code not in active_coupons or (active_coupons[code] == "게임 아이템 보상" and reward != "게임 아이템 보상"):
                        active_coupons[code] = reward

            # 2. 만료 쿠폰 구역 파싱
            if expired_section:
                expired_soup = BeautifulSoup(expired_section, "html.parser")
                for cand in expired_soup.find_all(['div', 'tr', 'li', 'td', 'p']):
                    text = cand.get_text(separator=" ").strip()
                    if len(text) > 250:
                        continue
                    codes = re.findall(r'\b[A-Z0-9]{5,20}\b', text)
                    for code in codes:
                        if code in EXCLUDED_CODES or code in active_coupons:
                            continue
                        reward = extract_and_translate_rewards(text)
                        if code not in expired_coupons:
                            expired_coupons[code] = reward

    except Exception as e:
        print(f"[{config['name']}] 크롤링 오류: {e}")

    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    coupon_dict = {}

    # A. 활성 쿠폰 반영
    for code, reward in active_coupons.items():
        coupon_dict[code] = {
            "code": code,
            "rewards": reward,
            "status": "ACTIVE",
            "created_at": today_str,
            "expired_at": None
        }

    # B. 타겟 사이트에서 만료로 분류된 쿠폰 반영
    for code, reward in expired_coupons.items():
        coupon_dict[code] = {
            "code": code,
            "rewards": reward,
            "status": "EXPIRED",
            "created_at": today_str,
            "expired_at": today_str
        }

    # C. 기존 데이터 중 사이트에서 완전히 사라진 쿠폰 만료 처리
    for old_item in existing_data:
        code = old_item.get("code")
        if not code or code in EXCLUDED_CODES:
            continue
        if code not in coupon_dict:
            if old_item.get("status") == "EXPIRED":
                coupon_dict[code] = old_item
            else:
                old_item["status"] = "EXPIRED"
                if not old_item.get("expired_at"):
                    old_item["expired_at"] = today_str
                coupon_dict[code] = old_item

    # D. 만료 후 7일 경과 데이터 삭제
    final_list = []
    for code, item in coupon_dict.items():
        if item["status"] == "EXPIRED" and item.get("expired_at"):
            try:
                exp_dt = datetime.strptime(item["expired_at"], "%Y-%m-%d")
                if (today - exp_dt).days > 7:
                    continue # 7일 경과 시 목록에서 완전 삭제
            except Exception:
                pass
        final_list.append(item)

    # JSON 저장
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
    print(f"[{config['name']}] 활성 {len(active_coupons)}개, 만료 {len(expired_coupons)}개 완벽 분류 완료!")

if __name__ == "__main__":
    for game_key, config in GAMES_CONFIG.items():
        process_game_coupons(game_key, config)
