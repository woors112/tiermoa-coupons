import json
import os
import re
import urllib.request
import urllib.parse
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup

# 1. 게임 수집 대상 및 커뮤니티 설정
GAMES_CONFIG = {
    "afk-journey": {
        "name": "AFK 새로운 여정",
        "global_db_url": "https://www.afk.global/afk-journey/codes",
        "lounge_id": "AFK_Journey",
        "file_name": "afk_journey.json"
    }
}

# 2. 크롤링 노이즈 방지 차단 단어 목록 (Blacklist)
EXCLUDED_CODES = {
    "OVERVIEW", "JOURNEY", "FEATURED", "CHARACTERS", "TIERLIST", "PATCH",
    "NOTES", "NEWS", "EVENTS", "DATABASES", "TERMS", "PRIVACY", "DISCORD",
    "REDDIT", "GLOBAL", "AFKJOURNEY", "REDEMPTION", "GUIDES", "DATABASE",
    "MODES", "RESOURCES", "RESOURCE", "AFFILIATED", "AFFILIATE", "COOKIES",
    "POLICY", "RIGHTS", "RESERVED", "SEARCH", "ACTIVE", "EXPIRED", "SHOW",
    "MORE", "LESS", "READ", "CLICK", "COPY", "REDEEM", "GAME", "CODE",
    "CODES", "LATEST", "BUILD", "UPDATE", "HOME", "CONTACT", "ABOUT",
    "ALL", "TIER", "LIST", "ITEM", "ITEMS", "HERO", "HEROES", "HTTPS",
    "WWW", "AFK", "LILITH", "GAMES", "COMMUNITY", "SUMMON", "TICKETS"
}

# 3. 한국어 서비스 공식 아이템 보상 명칭 사전
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

def translate_english_rewards(text):
    """영문 보상 정보를 한국 공식 명칭으로 정밀 치환"""
    if not text:
        return "게임 아이템 보상"
        
    found_rewards = []
    items_pattern = r'(?:Epic Invite Letters?|Invite Letters?|Stellar Crystals?|Hero Essence|Soulstones?|Diamonds?|Gold|Summon Tickets?|Hamsters?)'
    
    pattern1 = re.compile(rf'({items_pattern})\s*x\s*(\d+k?)', re.IGNORECASE)
    pattern2 = re.compile(rf'(\d+)\s*({items_pattern})', re.IGNORECASE)
    
    for match in pattern1.finditer(text):
        item_raw, qty_raw = match.group(1), match.group(2)
        translated = "아이템"
        for eng, kor in ITEM_TRANSLATIONS.items():
            if eng.lower() == item_raw.lower():
                translated = kor
                break
        
        qty_str = qty_raw.lower().replace('k', '만개')
        if not qty_str.endswith('만개'):
            qty_str += '개'
        found_rewards.append(f"{translated} {qty_str}")
        
    for match in pattern2.finditer(text):
        qty_raw, item_raw = match.group(1), match.group(2)
        translated = "아이템"
        for eng, kor in ITEM_TRANSLATIONS.items():
            if eng.lower() == item_raw.lower():
                translated = kor
                break
        found_rewards.append(f"{translated} {qty_raw}개")
        
    if found_rewards:
        return ", ".join(list(dict.fromkeys(found_rewards)))
        
    return "게임 아이템 보상"

def check_buffhub_global_db(url):
    """1. BuffHub / 글로벌 DB 아카이브(Active vs Expired) 구역 역추적"""
    active_codes = {}
    expired_codes = set()
    
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    try:
        res = scraper.get(url, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            
            # 1-1. DB 내 Expired(만료 아카이브) 구역 감지
            expired_elements = soup.find_all(class_=re.compile(r'expired', re.I)) + soup.find_all(id=re.compile(r'expired', re.I))
            for elem in expired_elements:
                found_expired = re.findall(r'\b[A-Z0-9]{5,20}\b', elem.get_text())
                for code in found_expired:
                    if code not in EXCLUDED_CODES:
                        expired_codes.add(code)

            # 1-2. DB 내 Active 구역 추출
            for cand in soup.find_all(['tr', 'li', 'div', 'p']):
                text = cand.get_text(separator=" ").strip()
                if len(text) > 220:
                    continue
                codes = re.findall(r'\b[A-Z0-9]{5,20}\b', text)
                for code in codes:
                    if code not in EXCLUDED_CODES and code not in expired_codes:
                        reward = translate_english_rewards(text)
                        if code not in active_codes or (active_codes[code] == "게임 아이템 보상" and reward != "게임 아이템 보상"):
                            active_codes[code] = reward

    except Exception as e:
        print(f"BuffHub/글로벌 DB 파싱 예외: {e}")
        
    return active_codes, expired_codes

def fetch_developer_official_logs(lounge_id):
    """2. 릴리스/파라이트 게임즈 공식 커뮤니티 GM 공지 로그 역추적"""
    official_expired_codes = set()
    encoded_query = urllib.parse.quote("쿠폰")
    url = f"https://game.naver.com/api/v2/lounge/{lounge_id}/board/search?query={encoded_query}&limit=15"
    
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            if res.getcode() == 200:
                data = json.loads(res.read().decode('utf-8'))
                posts = data.get("content", {}).get("list", [])
                
                for post in posts:
                    title = post.get("title", "")
                    content = post.get("content", "")
                    full_text = f"{title} {content}"
                    
                    # 개발사 공지에 '만료', '종료', '사용 불가' 명시 로그 감지
                    if any(kw in full_text for kw in ["만료", "종료", "사용불가", "사용 불가"]):
                        codes = re.findall(r'\b[A-Z0-9]{5,20}\b', full_text)
                        for code in codes:
                            if code not in EXCLUDED_CODES:
                                official_expired_codes.add(code)
    except Exception as e:
        print(f"개발사 공식 라운지 로그 역추적 예외: {e}")
        
    return official_expired_codes

def process_game_coupons(game_key, config):
    print(f"[{config['name']}] DB 아카이브 & 개발사 공식 로그 정밀 팩트체크 시작...")
    file_name = config["file_name"]
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    
    # 1. BuffHub / 글로벌 DB 구역 스캔
    active_from_db, expired_from_db = check_buffhub_global_db(config["global_db_url"])
    
    # 2. 개발사 공식 라운지 로그 역추적
    official_expired_logs = fetch_developer_official_logs(config["lounge_id"])
    
    # 3. 팩트체크 교차 검증
    final_list = []
    
    for code, reward in active_from_db.items():
        # 상시 영구 쿠폰 예외
        if code == "AFKJ10":
            status = "ACTIVE"
            reward = "일반 전체 소환권 10개"
        elif code == "HQC0ZFSC6QYTX":
            reward = "다이아 500개, 종이접기 햄스터 5개, 골드 5만개"
            status = "ACTIVE"
        else:
            # DB 만료 구역에 속하거나, 개발사 공식 로그에서 만료로 판명된 경우
            is_expired = (code in expired_from_db) or (code in official_expired_logs)
            status = "EXPIRED" if is_expired else "ACTIVE"

        final_list.append({
            "code": code,
            "rewards": reward,
            "status": status,
            "created_at": today_str,
            "expired_at": today_str if status == "EXPIRED" else None
        })

    # JSON 저장
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
        
    print(f"[{config['name']}] 팩트체크 완료! (최종 수집: {len(final_list)}개)")

if __name__ == "__main__":
    for game_key, config in GAMES_CONFIG.items():
        process_game_coupons(game_key, config)
