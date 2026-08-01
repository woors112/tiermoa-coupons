import json
import os
import re
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import cloudscraper
from bs4 import BeautifulSoup

# 1. 게임 및 수집 타겟 설정
GAMES_CONFIG = {
    "afk-journey": {
        "name": "AFK 새로운 여정",
        "global_db_url": "https://www.afk.global/afk-journey/codes",
        "lounge_id": "AFK_Journey",
        "file_name": "afk_journey.json"
    }
}

# 2. 크롤링 차단 시스템 노이즈 키워드 (Blacklist)
EXCLUDED_CODES = {
    "OVERVIEW", "JOURNEY", "FEATURED", "CHARACTERS", "TIERLIST", "PATCH",
    "NOTES", "NEWS", "EVENTS", "DATABASES", "TERMS", "PRIVACY", "DISCORD",
    "REDDIT", "GLOBAL", "AFKJOURNEY", "REDEMPTION", "GUIDES", "DATABASE",
    "MODES", "RESOURCES", "COOKIES", "POLICY", "RIGHTS", "RESERVED", "SEARCH",
    "ACTIVE", "EXPIRED", "SHOW", "MORE", "LESS", "READ", "CLICK", "COPY",
    "REDEEM", "GAME", "CODE", "CODES", "LATEST", "BUILD", "UPDATE", "HOME",
    "CONTACT", "ABOUT", "ALL", "TIER", "LIST", "ITEM", "ITEMS", "HERO", "HEROES",
    "HTTPS", "WWW", "AFK", "LILITH", "GAMES", "COMMUNITY", "SUMMON", "TICKETS",
    "ARENA", "MOBILE", "ANDROID", "APPLE", "GOOGLE", "STORE", "PLAY", "ONLINE",
    "NAVER", "LOUNGE", "LOUNGEID", "NOTICE", "BOARD", "BUFFHUB"
}

# 3. 상시 유지 영구 쿠폰 예외 목록
PERMANENT_CODES = {"AFKJ10"}

# 4. 한국 공식 보상 명칭 사전
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

def parse_expiry_date(text, base_date):
    """텍스트 내 유효기간(~2026.08.31, ~8월 31일 등) 정밀 추출"""
    curr_year = base_date.year
    
    # 패턴 A: YYYY.MM.DD / YYYY-MM-DD / YYYY/MM/DD
    match_full = re.search(r'20\d{2}[.-/](\d{1,2})[.-/](\d{1,2})', text)
    if match_full:
        m, d = int(match_full.group(1)), int(match_full.group(2))
        try:
            return datetime(curr_year, m, d).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 패턴 B: ~M월 D일 / ~MM월 DD일
    match_kor = re.search(r'(?:~\s*|까지\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일', text)
    if match_kor:
        m, d = int(match_kor.group(1)), int(match_kor.group(2))
        try:
            return datetime(curr_year, m, d).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 패턴 C: ~M/D / ~MM/DD
    match_slash = re.search(r'(?:~\s*|까지\s*)(\d{1,2})/(\d{1,2})', text)
    if match_slash:
        m, d = int(match_slash.group(1)), int(match_slash.group(2))
        try:
            return datetime(curr_year, m, d).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 만료일 미기재 시 기본 14일 부여
    return (base_date + timedelta(days=14)).strftime("%Y-%m-%d")

def translate_english_rewards(text):
    """글로벌 영문 보상 문구를 한국 공식 서비스 명칭으로 정밀 변환"""
    if not text:
        return "게임 아이템 보상"
        
    found_rewards = []
    items_pattern = r'(?:Epic Invite Letters?|Invite Letters?|Stellar Crystals?|Hero Essence|Soulstones?|Diamonds?|Gold|Summon Tickets?|Hamsters?)'
    
    pattern1 = re.compile(rf'({items_pattern})\s*x\s*(\d+k?)', re.IGNORECASE)
    pattern2 = re.compile(rf'(\d+)\s*({items_pattern})', re.IGNORECASE)
    
    for match in pattern1.finditer(text):
        item_raw, qty_raw = match.group(1), match.group(2)
        translated = ITEM_TRANSLATIONS.get(item_raw, "아이템")
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
        translated = ITEM_TRANSLATIONS.get(item_raw, "아이템")
        for eng, kor in ITEM_TRANSLATIONS.items():
            if eng.lower() == item_raw.lower():
                translated = kor
                break
        found_rewards.append(f"{translated} {qty_raw}개")
        
    if found_rewards:
        return ", ".join(list(dict.fromkeys(found_rewards)))
        
    return "게임 아이템 보상"

def fetch_global_db_coupons(url):
    """1차 수집: 글로벌 DB / BuffHub 수집망 스캔"""
    coupons = {}
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    try:
        res = scraper.get(url, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for cand in soup.find_all(['div', 'tr', 'li', 'td', 'p']):
                text = cand.get_text(separator=" ").strip()
                if len(text) > 250:
                    continue
                codes = re.findall(r'\b[A-Z0-9]{5,20}\b', text)
                for code in codes:
                    if code in EXCLUDED_CODES:
                        continue
                    reward = translate_english_rewards(text)
                    if code not in coupons or (coupons[code] == "게임 아이템 보상" and reward != "게임 아이템 보상"):
                        coupons[code] = reward
    except Exception as e:
        print(f"글로벌 DB 수집 예외: {e}")
    return coupons

def fetch_naver_lounge_verification(lounge_id):
    """2차 수집: 한국 공식 네이버 라운지 실시간 검증 데이터 스캔"""
    verification_db = {}
    today = datetime.now()
    
    encoded_query = urllib.parse.quote("쿠폰")
    url = f"https://game.naver.com/api/v2/lounge/{lounge_id}/board/search?query={encoded_query}&limit=15"
    
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": f"https://game.naver.com/lounge/{lounge_id}/home"
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            if res.getcode() == 200:
                body = res.read().decode('utf-8')
                data = json.loads(body)
                posts = data.get("content", {}).get("list", [])
                
                for post in posts:
                    title = post.get("title", "")
                    content = post.get("content", "")
                    full_text = f"{title} {content}"
                    
                    codes = re.findall(r'\b[A-Z0-9]{5,20}\b', full_text)
                    is_expired_reported = any(kw in full_text for kw in ["만료", "종료", "기간지남", "사용불가", "안됨"])
                    expiry_date_str = parse_expiry_date(full_text, today)
                    
                    for code in codes:
                        if code in EXCLUDED_CODES:
                            continue
                        verification_db[code] = {
                            "is_expired": is_expired_reported,
                            "expired_at": expiry_date_str,
                            "raw_text": full_text
                        }
    except Exception as e:
        print(f"네이버 라운지 검증 수집 예외: {e}")
        
    return verification_db

def process_game_coupons(game_key, config):
    print(f"[{config['name']}] 글로벌 DB + 한국 공식 커뮤니티 팩트체크 수집 시작...")
    file_name = config["file_name"]
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    
    # 1차: 글로벌 DB 크롤링
    global_coupons = fetch_global_db_coupons(config["global_db_url"])
    
    # 2차: 한국 공식 라운지 팩트체크 데이터 수집
    lounge_verification = fetch_naver_lounge_verification(config["lounge_id"])
    
    # 3차: 교차 대조 및 팩트체크 판별 (Cross-Fact-Checking)
    fact_checked_dict = {}
    
    # A. 수집된 모든 쿠폰 코드 취합
    all_codes = set(global_coupons.keys()).union(set(lounge_verification.keys()))
    
    for code in all_codes:
        if code in EXCLUDED_CODES:
            continue
            
        reward = global_coupons.get(code, "게임 아이템 보상")
        if code == "AFKJ10":
            reward = "일반 전체 소환권 10개"
        elif code == "HQC0ZFSC6QYTX":
            reward = "다이아 500개, 종이접기 햄스터 5개, 골드 5만개"
            
        verification = lounge_verification.get(code, {})
        is_community_expired = verification.get("is_expired", False)
        exp_date_str = verification.get("expired_at", (today + timedelta(days=14)).strftime("%Y-%m-%d"))
        
        # 상태 결정 (상시 쿠폰 예외)
        if code in PERMANENT_CODES:
            status = "ACTIVE"
            exp_date_str = None
        else:
            # 팩트체크 조건 1: 커뮤니티 만료 제보 확인 시
            # 팩트체크 조건 2: 만료 날짜가 오늘 이전인 경우
            is_date_expired = False
            try:
                exp_dt = datetime.strptime(exp_date_str, "%Y-%m-%d")
                if exp_dt < today:
                    is_date_expired = True
            except Exception:
                pass

            if is_community_expired or is_date_expired:
                status = "EXPIRED"
            else:
                status = "ACTIVE"

        fact_checked_dict[code] = {
            "code": code,
            "rewards": reward,
            "status": status,
            "created_at": today_str,
            "expired_at": exp_date_str if status == "EXPIRED" else None
        }

    # 4차: 만료 후 7일 경과 데이터 완전 자동 정기 삭제
    final_data = []
    for code, item in fact_checked_dict.items():
        if item["status"] == "EXPIRED" and item.get("expired_at"):
            try:
                exp_dt = datetime.strptime(item["expired_at"], "%Y-%m-%d")
                if (today - exp_dt).days > 7:
                    continue # 7일 경과 시 정기 완전 삭제
            except Exception:
                pass
        final_data.append(item)

    # JSON 최종 저장
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)
    print(f"[{config['name']}] 실시간 팩트체크 및 검증 완료! (총 {len(final_data)}개 쿠폰 처리됨)")

if __name__ == "__main__":
    for game_key, config in GAMES_CONFIG.items():
        process_game_coupons(game_key, config)
