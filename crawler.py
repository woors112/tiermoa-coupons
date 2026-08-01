import json
import os
import re
import urllib.request
import urllib.parse
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# 1. 수집 타겟 및 출처 설정
# ---------------------------------------------------------------------------
GAMES_CONFIG = {
    "afk-journey": {
        "name": "AFK 새로운 여정",
        "buffhub_url": "https://www.afk.global/afk-journey/codes",
        "arca_url": "https://arca.live/b/afkjourney?target=title_content&keyword=%EC%BF%A0%ED%8F%B0",
        "lounge_id": "AFK_Journey",
        "file_name": "afk_journey.json"
    }
}

# ---------------------------------------------------------------------------
# 2. 최소 블랙리스트 및 만료 표현 정밀 감지 키워드
# ---------------------------------------------------------------------------
MINIMUM_EXCLUDED_CODES = {
    "CODE", "CODES", "STATUS", "EXPIRED", "ACTIVE",
    "REDEMPTION", "REWARD", "REWARDS", "AFKJOURNEY",
    "GLOBAL", "BUFFHUB", "COPY", "REDEEM", "CLICK", "PREVIOUS"
}

# 커뮤니티 및 공지에서 등장하는 모든 만료/무효 표현 (정밀 감지)
EXPIRATION_KEYWORDS = [
    "만료", "종료", "안됨", "안 됨", "지남", "기간지남", "기간 지남",
    "존재하지 않는", "존재하지않는", "올바르지 않은", "올바르지않은",
    "사용불가", "사용 불가", "사용할 수 없는", "이미 만료", "쿠폰 끝",
    "막힘", "막혔", "등록 불가", "등록불가"
]

PERMANENT_CODES = {"AFKJ10"}

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

def translate_rewards(text):
    """영문 보상 명칭을 한국 공식 명칭으로 정밀 치환"""
    if not text:
        return "게임 아이템 보상"
        
    found_rewards = []
    items_pattern = r'(?:Epic Invite Letters?|Invite Letters?|Stellar Crystals?|Hero Essence|Soulstones?|Diamonds?|Gold|Summon Tickets?|Hamsters?)'
    
    p1 = re.compile(rf'({items_pattern})\s*x\s*(\d+k?)', re.IGNORECASE)
    p2 = re.compile(rf'(\d+)\s*({items_pattern})', re.IGNORECASE)
    
    for match in p1.finditer(text):
        item_raw, qty_raw = match.group(1), match.group(2)
        translated = next((kor for eng, kor in ITEM_TRANSLATIONS.items() if eng.lower() == item_raw.lower()), "아이템")
        qty_str = qty_raw.lower().replace('k', '만개')
        if not qty_str.endswith('만개'):
            qty_str += '개'
        found_rewards.append(f"{translated} {qty_str}")
        
    for match in p2.finditer(text):
        qty_raw, item_raw = match.group(1), match.group(2)
        translated = next((kor for eng, kor in ITEM_TRANSLATIONS.items() if eng.lower() == item_raw.lower()), "아이템")
        found_rewards.append(f"{translated} {qty_raw}개")
        
    return ", ".join(list(dict.fromkeys(found_rewards))) if found_rewards else "게임 아이템 보상"

def check_is_expired_text(text):
    """텍스트에 만료/무효 관련 키워드가 포함되어 있는지 정밀 파싱"""
    return any(keyword in text for keyword in EXPIRATION_KEYWORDS)

# ---------------------------------------------------------------------------
# 3. 출처별 정밀 파싱 모듈
# ---------------------------------------------------------------------------
def fetch_buffhub_tables(url):
    """1. BuffHub: Reported Expiration or Status 표 정밀 파싱"""
    active_coupons = {}
    expired_coupons = set()
    
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    try:
        res = scraper.get(url, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            tables = soup.find_all('table')
            
            for table in tables:
                table_text = table.get_text()
                is_expired_table = any(kw in table_text for kw in ["Reported Expiration", "Expired Code", "Previous Rewards"])
                
                rows = table.find_all('tr')
                for row in rows:
                    cols = row.find_all(['td', 'th'])
                    if not cols:
                        continue
                    
                    first_col_text = cols[0].get_text().strip()
                    raw_codes = re.findall(r'\b[a-zA-Z0-9]{5,20}\b', first_col_text)
                    
                    reward_text = cols[1].get_text().strip() if len(cols) > 1 else ""
                    translated_reward = translate_rewards(reward_text)
                    
                    for raw_code in raw_codes:
                        code = raw_code.upper()
                        if code in MINIMUM_EXCLUDED_CODES:
                            continue
                            
                        if is_expired_table:
                            expired_coupons.add(code)
                        else:
                            if code not in active_coupons or (active_coupons[code] == "게임 아이템 보상" and translated_reward != "게임 아이템 보상"):
                                active_coupons[code] = translated_reward
    except Exception as e:
        print(f"BuffHub 파싱 예외: {e}")
        
    return active_coupons, expired_coupons

def fetch_arca_live(url):
    """2. 아카라이브 AFK 새로운 여정 채널 키워드 스캔"""
    arca_expired = set()
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    try:
        res = scraper.get(url, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            articles = soup.find_all('a', class_=re.compile(r'title', re.I))
            for art in articles:
                title = art.get_text().strip()
                if check_is_expired_text(title):
                    codes = re.findall(r'\b[a-zA-Z0-9]{5,20}\b', title)
                    for raw_code in codes:
                        code = raw_code.upper()
                        if code not in MINIMUM_EXCLUDED_CODES:
                            arca_expired.add(code)
    except Exception as e:
        print(f"아카라이브 파싱 예외: {e}")
    return arca_expired

def fetch_naver_lounge(lounge_id):
    """3. 네이버 게임 라운지 공지 및 유저 게시글 만료 표현 스캔"""
    lounge_expired = set()
    encoded_query = urllib.parse.quote("쿠폰")
    url = f"https://game.naver.com/api/v2/lounge/{lounge_id}/board/search?query={encoded_query}&limit=20"
    
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            if res.getcode() == 200:
                data = json.loads(res.read().decode('utf-8'))
                posts = data.get("content", {}).get("list", [])
                for post in posts:
                    full_text = f"{post.get('title', '')} {post.get('content', '')}"
                    if check_is_expired_text(full_text):
                        codes = re.findall(r'\b[a-zA-Z0-9]{5,20}\b', full_text)
                        for raw_code in codes:
                            code = raw_code.upper()
                            if code not in MINIMUM_EXCLUDED_CODES:
                                lounge_expired.add(code)
    except Exception as e:
        print(f"네이버 라운지 파싱 예외: {e}")
    return lounge_expired

# ---------------------------------------------------------------------------
# 4. 메인 동기화 로직
# ---------------------------------------------------------------------------
def process_game_coupons(game_key, config):
    print(f"[{config['name']}] 확장 만료 키워드 + 출처 통합 팩트체크 크롤링 시작...")
    file_name = config["file_name"]
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    
    # 1. 히스토리 로드
    existing_data = {}
    if os.path.exists(file_name):
        try:
            with open(file_name, "r", encoding="utf-8") as f:
                for item in json.load(f):
                    existing_data[item["code"]] = item
        except Exception:
            pass

    # 2. 출처별 수집 및 만료 파싱
    active_buffhub, expired_buffhub = fetch_buffhub_tables(config["buffhub_url"])
    expired_arca = fetch_arca_live(config["arca_url"])
    expired_lounge = fetch_naver_lounge(config["lounge_id"])
    
    total_expired = expired_buffhub.union(expired_arca).union(expired_lounge)
    
    # 3. 통합 및 상태 결정
    all_codes = set(active_buffhub.keys()).union(set(existing_data.keys()))
    updated_list = []
    
    for code in all_codes:
        if code in MINIMUM_EXCLUDED_CODES:
            continue
            
        prev_item = existing_data.get(code, {})
        created_at_str = prev_item.get("created_at", today_str)
        reward = active_buffhub.get(code, prev_item.get("rewards", "게임 아이템 보상"))
        
        # 특수 상시 쿠폰 고정
        if code == "AFKJ10":
            reward = "일반 전체 소환권 10개"
        elif code == "HQC0ZFSC6QYTX":
            reward = "다이아 500개, 종이접기 햄스터 5개, 골드 5만개"
            
        if code in PERMANENT_CODES:
            status = "ACTIVE"
            exp_date_str = None
        else:
            is_expired = (code in total_expired) or prev_item.get("status") == "EXPIRED"
            status = "EXPIRED" if is_expired else "ACTIVE"
            exp_date_str = prev_item.get("expired_at") or (today_str if status == "EXPIRED" else None)

        updated_list.append({
            "code": code,
            "rewards": reward,
            "status": status,
            "created_at": created_at_str,
            "expired_at": exp_date_str
        })

    # 4. 만료 후 7일 경과 시 자동 삭제
    final_list = []
    for item in updated_list:
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
        
    print(f"[{config['name']}] 크롤링 완료! (총 {len(final_list)}개 처리됨)")

if __name__ == "__main__":
    for game_key, config in GAMES_CONFIG.items():
        process_game_coupons(game_key, config)
