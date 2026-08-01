import json
import os
import re
import urllib.request
import urllib.parse
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# 1. 수집 게임 및 타겟 설정
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
# 2. 필수 차단 블랙리스트 (메뉴 및 시스템 단어 차단)
# ---------------------------------------------------------------------------
EXCLUDED_CODES = {
    "CODE", "CODES", "STATUS", "EXPIRED", "ACTIVE", "REDEMPTION", "REWARD",
    "REWARDS", "AFKJOURNEY", "GLOBAL", "BUFFHUB", "COPY", "REDEEM", "CLICK",
    "PREVIOUS", "ARENA", "RESOURCE", "AFFILIATED", "OVERVIEW", "JOURNEY",
    "FEATURED", "CHARACTERS", "TIERLIST", "PATCH", "NOTES", "NEWS", "EVENTS",
    "DATABASES", "TERMS", "PRIVACY", "DISCORD", "REDDIT", "GUIDES", "DATABASE",
    "MODES", "RESOURCES", "AFFILIATE", "COOKIES", "POLICY", "RIGHTS", "RESERVED"
}

# ---------------------------------------------------------------------------
# 3. 팩트체크 검증 데이터베이스
# ---------------------------------------------------------------------------
PERMANENT_ACTIVE_CODES = {
    "AFKJ10": "일반 전체 소환권 10개",
    "HQC0ZFSC6QYTX": "다이아 500개, 종이접기 햄스터 5개, 골드 5만개"
}

KNOWN_EXPIRED_CODES = {
    "B52F8N5OPOG7K": "다이아 500개, 종이접기 햄스터 10개, 골드 50만개",
    "ZC1JJ3UU0N": "다이아 1000개, 에픽 초대장 5개, 골드 20만개",
    "4IYTSNBDXC": "다이아 1000개, 에픽 초대장 5개, 골드 20만개",
    "H7PDTYNR61": "다이아 1000개, 에픽 초대장 5개, 골드 20만개",
    "E8BESLBQZLZUD": "다이아 500개, 종이접기 햄스터 10개, 골드 50만개",
    "SMALLGIFTFROMPEGGY": "다이아 500개, 골드 2만개"
}

# ---------------------------------------------------------------------------
# 4. 크롤링 및 파싱 함수
# ---------------------------------------------------------------------------
def fetch_buffhub_data(url):
    active_coupons = {}
    expired_coupons = set()
    
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    try:
        res = scraper.get(url, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for table in soup.find_all('table'):
                table_text = table.get_text()
                is_expired = any(kw in table_text for kw in ["Reported Expiration", "Expired Code", "Previous Rewards", "Expired"])
                
                for row in table.find_all('tr'):
                    cols = row.find_all(['td', 'th'])
                    if not cols:
                        continue
                    first_col = cols[0].get_text().strip()
                    for raw_code in re.findall(r'\b[a-zA-Z0-9]{5,20}\b', first_col):
                        code = raw_code.upper()
                        if code in EXCLUDED_CODES:
                            continue
                        if is_expired:
                            expired_coupons.add(code)
                        else:
                            active_coupons[code] = "게임 아이템 보상"
    except Exception as e:
        print(f"[BuffHub] 수집 중 예외: {e}")
        
    return active_coupons, expired_coupons

# ---------------------------------------------------------------------------
# 5. 메인 처리 프로세스 (상태별 정렬 로직 탑재)
# ---------------------------------------------------------------------------
def process_game_coupons(game_key, config):
    print(f"[{config['name']}] 정밀 팩트체크 및 자동 정렬 처리 시작...")
    file_name = config["file_name"]
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # BuffHub 수집
    scraped_active, scraped_expired = fetch_buffhub_data(config["buffhub_url"])
    
    total_expired = scraped_expired.union(set(KNOWN_EXPIRED_CODES.keys()))
    all_codes = set(scraped_active.keys()).union(set(PERMANENT_ACTIVE_CODES.keys())).union(total_expired)
    
    updated_list = []
    
    for code in all_codes:
        if code in EXCLUDED_CODES:
            continue
            
        if code in PERMANENT_ACTIVE_CODES:
            status = "ACTIVE"
            reward = PERMANENT_ACTIVE_CODES[code]
            expired_at = None
        elif code in total_expired:
            status = "EXPIRED"
            reward = KNOWN_EXPIRED_CODES.get(code, "게임 아이템 보상")
            expired_at = today_str
        else:
            status = "ACTIVE"
            reward = scraped_active.get(code, "게임 아이템 보상")
            expired_at = None

        updated_list.append({
            "code": code,
            "rewards": reward,
            "status": status,
            "created_at": today_str,
            "expired_at": expired_at
        })

    # 6. 만료 후 7일 지난 쿠폰 완전 자동 삭제
    final_list = []
    for item in updated_list:
        if item["status"] == "EXPIRED" and item.get("expired_at"):
            try:
                exp_dt = datetime.strptime(item["expired_at"], "%Y-%m-%d")
                if (datetime.now() - exp_dt).days > 7:
                    continue
            except Exception:
                pass
        final_list.append(item)

    # 7. 🔥 [핵심] 사용 가능(ACTIVE) 쿠폰 우선 정렬 (ACTIVE -> 0, EXPIRED -> 1)
    final_list.sort(key=lambda x: (0 if x["status"] == "ACTIVE" else 1, x["code"]))

    # JSON 저장
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
        
    print(f"[{config['name']}] 완료! 활성 쿠폰이 상단으로 정렬되어 저장되었습니다.")

if __name__ == "__main__":
    for game_key, config in GAMES_CONFIG.items():
        process_game_coupons(game_key, config)
