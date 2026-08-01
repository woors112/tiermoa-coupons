import json
import os
import re
import urllib.request
import urllib.parse
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# 1. 수집 타겟 및 출처 설정 (진짜 BuffHub URL 반영)
# ---------------------------------------------------------------------------
GAMES_CONFIG = {
    "afk-journey": {
        "name": "AFK 새로운 여정",
        "buffhub_url": "https://buffhub.com/blog/afk-journey/",
        "lounge_id": "AFK_Journey",
        "file_name": "afk_journey.json"
    }
}

# ---------------------------------------------------------------------------
# 2. 최소 블랙리스트 및 만료 키워드
# ---------------------------------------------------------------------------
MINIMUM_EXCLUDED_CODES = {
    "CODE", "CODES", "STATUS", "EXPIRED", "ACTIVE",
    "REDEMPTION", "REWARD", "REWARDS", "AFKJOURNEY",
    "GLOBAL", "BUFFHUB", "COPY", "REDEEM", "CLICK", "PREVIOUS"
}

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
    return any(kw in text for kw in EXPIRATION_KEYWORDS)

# ---------------------------------------------------------------------------
# 3. 진짜 BuffHub(buffhub.com) 표 파싱 모듈
# ---------------------------------------------------------------------------
def fetch_buffhub_tables(url):
    active_coupons = {}
    expired_coupons = set()
    
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    try:
        res = scraper.get(url, timeout=15)
        print(f"[BuffHub 접속] HTTP 응답 코드: {res.status_code}")
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            tables = soup.find_all('table')
            print(f"[BuffHub 접속] 파싱된 Table 개수: {len(tables)}")
            
            for table in tables:
                table_text = table.get_text()
                is_expired_table = any(kw in table_text for kw in ["Reported Expiration", "Expired Code", "Previous Rewards", "Expired"])
                
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
        print(f"[BuffHub 접속] 파싱 수집 예외: {e}")
        
    print(f"[BuffHub 파싱 결과] 활성: {len(active_coupons)}개, 만료: {len(expired_coupons)}개")
    return active_coupons, expired_coupons

def verify_code_via_naver_lounge(lounge_id, code):
    """네이버 게임 라운지 핀포인트 만료 제보 확인"""
    encoded_code = urllib.parse.quote(code)
    url = f"https://game.naver.com/api/v2/lounge/{lounge_id}/board/search?query={encoded_code}&limit=10"
    
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            if res.getcode() == 200:
                data = json.loads(res.read().decode('utf-8'))
                posts = data.get("content", {}).get("list", [])
                for post in posts:
                    full_text = f"{post.get('title', '')} {post.get('content', '')}"
                    if check_is_expired_text(full_text):
                        return True
    except Exception:
        pass
    return False

# ---------------------------------------------------------------------------
# 4. 메인 동기화 프로세스
# ---------------------------------------------------------------------------
def process_game_coupons(game_key, config):
    print(f"[{config['name']}] 진짜 BuffHub(buffhub.com) 동기화 시작...")
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

    # 2. BuffHub 수집
    active_buffhub, expired_buffhub = fetch_buffhub_tables(config["buffhub_url"])
    
    # 3. 데이터 취합
    all_codes = set(active_buffhub.keys()).union(set(expired_buffhub)).union(set(existing_data.keys()))
    updated_list = []
    
    for code in all_codes:
        if code in MINIMUM_EXCLUDED_CODES:
            continue
            
        prev_item = existing_data.get(code, {})
        created_at_str = prev_item.get("created_at", today_str)
        reward = active_buffhub.get(code, prev_item.get("rewards", "게임 아이템 보상"))
        
        # 커스텀 보상 지정
        if code == "AFKJ10":
            reward = "일반 전체 소환권 10개"
        elif code == "HQC0ZFSC6QYTX":
            reward = "다이아 500개, 종이접기 햄스터 5개, 골드 5만개"
            
        # 4. 네이버 라운지 교차 검증
        is_lounge_expired = verify_code_via_naver_lounge(config["lounge_id"], code)
        
        # 5. 최종 만료 상태 판별
        if code in PERMANENT_CODES:
            status = "ACTIVE"
            exp_date_str = None
        else:
            is_expired = (code in expired_buffhub) or is_lounge_expired or (prev_item.get("status") == "EXPIRED")
            status = "EXPIRED" if is_expired else "ACTIVE"
            exp_date_str = prev_item.get("expired_at") or (today_str if status == "EXPIRED" else None)

        print(f" -> 코드: {code} | 상태: {status}")

        updated_list.append({
            "code": code,
            "rewards": reward,
            "status": status,
            "created_at": created_at_str,
            "expired_at": exp_date_str
        })

    # 6. 만료 후 7일 지난 데이터 완전 자동 삭제
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

    # JSON 최종 저장
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
        
    print(f"[{config['name']}] 진짜 BuffHub 연동 성공! (총 {len(final_list)}개 동기화됨)")

if __name__ == "__main__":
    for game_key, config in GAMES_CONFIG.items():
        process_game_coupons(game_key, config)
