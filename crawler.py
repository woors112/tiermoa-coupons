import json
import os
import re
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup

# 1. 게임별 설정
GAMES_CONFIG = {
    "afk-journey": {
        "name": "AFK 새로운 여정",
        "url": "https://www.afk.global/afk-journey/codes",
        "file_name": "afk_journey.json"
    }
}

# 2. 쿠폰 코드가 아닌 메인 메뉴/시스템 단어 완벽 차단 리스트
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

# 3. 2026년 8월 기준 국내 검증 완료된 만료 쿠폰 강제 판별 목록
FORCE_EXPIRED_CODES = {
    "E8BESLBQZLZUD": "다이아 500개, 종이접기 햄스터 10개, 골드 5만개",
    "B52F8N5OPOG7K": "다이아 500개, 종이접기 햄스터 10개, 골드 5만개",
    "H7PDTYNR61": "다이아 1000개, 에픽 초대장 5개, 골드 2만개",
    "ZC1JJ3UU0N": "다이아 1000개, 에픽 초대장 5개, 골드 2만개",
    "4IYTSNBDXC": "다이아 1000개, 에픽 초대장 5개, 골드 2만개"
}

# 4. 한국 서비스 공식 아이템 명칭 변환 사전
ITEM_TRANSLATIONS = {
    "Epic Invite Letters": "에픽 초대장",
    "Epic Invite Letter": "에픽 초대장",
    "Invite Letters": "일반 초대장",
    "Invite Letter": "일반 초대장",
    "Stellar Crystals": "별의 결정",
    "Stellar Crystal": "별의 결정",
    "Summon Tickets": "일반 전체 소환권",
    "Summon Ticket": "일반 전체 소환권",
    "Diamonds": "다이아",
    "Diamond": "다이아",
    "Gold": "골드",
    "Hero Essence": "영웅의 정수",
    "Soulstones": "영웅 영혼석",
    "Soulstone": "영웅 영혼석",
    "Hamsters": "종이접기 햄스터",
    "Hamster": "종이접기 햄스터"
}

def extract_and_translate_rewards(code, text):
    """쿠폰별 한국 공식 아이템명 정밀 치환 함수"""
    if code == "AFKJ10":
        return "일반 전체 소환권 10개"
    if code == "HQC0ZFSC6QYTX":
        return "다이아 500개, 종이접기 햄스터 5개, 골드 5만개"
        
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
    print(f"[{config['name']}] 정밀 크롤링 수집 시작...")
    file_name = config["file_name"]
    url = config["url"]
    
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    
    raw_coupons = {}
    
    try:
        res = scraper.get(url, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            candidates = soup.find_all(['div', 'tr', 'li', 'td', 'p'])
            
            for cand in candidates:
                text = cand.get_text(separator=" ").strip()
                if len(text) > 250:
                    continue
                codes = re.findall(r'\b[A-Z0-9]{5,20}\b', text)
                for code in codes:
                    if code in EXCLUDED_CODES:
                        continue
                    reward = extract_and_translate_rewards(code, text)
                    if code not in raw_coupons or (raw_coupons[code] == "게임 아이템 보상" and reward != "게임 아이템 보상"):
                        raw_coupons[code] = reward

    except Exception as e:
        print(f"[{config['name']}] 크롤링 오류: {e}")

    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    coupon_dict = {}

    # 1. 수집된 쿠폰 정밀 상태 분류
    for code, reward in raw_coupons.items():
        if code in FORCE_EXPIRED_CODES:
            coupon_dict[code] = {
                "code": code,
                "rewards": FORCE_EXPIRED_CODES[code],
                "status": "EXPIRED",
                "created_at": today_str,
                "expired_at": today_str
            }
        else:
            coupon_dict[code] = {
                "code": code,
                "rewards": reward,
                "status": "ACTIVE",
                "created_at": today_str,
                "expired_at": None
            }

    # 2. 만료 쿠폰 강제 보완
    for exp_code, exp_reward in FORCE_EXPIRED_CODES.items():
        if exp_code not in coupon_dict:
            coupon_dict[exp_code] = {
                "code": exp_code,
                "rewards": exp_reward,
                "status": "EXPIRED",
                "created_at": today_str,
                "expired_at": today_str
            }

    # 3. 만료 7일 경과 데이터 완전 삭제
    final_list = []
    for code, item in coupon_dict.items():
        if item["status"] == "EXPIRED" and item.get("expired_at"):
            try:
                exp_dt = datetime.strptime(item["expired_at"], "%Y-%m-%d")
                if (today - exp_dt).days > 7:
                    continue
            except Exception:
                pass
        final_list.append(item)

    # JSON 저장
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
    print(f"[{config['name']}] 최종 검증 완료!")

if __name__ == "__main__":
    for game_key, config in GAMES_CONFIG.items():
        process_game_coupons(game_key, config)
