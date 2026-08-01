import json
import os
import re
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
import cloudscraper
from bs4 import BeautifulSoup

# 한국 표준시(KST) 타임존 설정 (UTC+9)
KST = timezone(timedelta(hours=9))

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
# 2. 필수 차단 블랙리스트
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
# 5. 메인 처리 프로세스 (KST 시각 포맷 적용)
# ---------------------------------------------------------------------------
def process_game_coupons(game_key, config):
    file_name = config["file_name"]
    
    # 🔥 한국 시간(KST) 기준 날짜 및 시각 생성
    now_kst = datetime.now(KST)
    today_str = now_kst.strftime("%Y-%m-%d")
    updated_at_str = now_kst.strftime("%Y.%m.%d. %H시 갱신") # 예: 2026.08.02. 18시 갱신
    
    print(f"[{config['name']}] 정밀 크롤링 시작 (KST 기준시각: {updated_at_str})...")

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
            expiry_note = "상시 유효"  # 버튼 왼편에 표시될 문구
        elif code in total_expired:
            status = "EXPIRED"
            reward = KNOWN_EXPIRED_CODES.get(code, "게임 아이템 보상")
            expired_at = today_str
            expiry_note = f"{now_kst.strftime('%Y.%m.%d.')} 만료" # 예: 2026.08.02. 만료
        else:
            status = "ACTIVE"
            reward = scraped_active.get(code, "게임 아이템 보상")
            expired_at = None
            expiry_note = "소진 시까지"

        updated_list.append({
            "code": code,
            "rewards": reward,
            "status": status,
            "updated_at": updated_at_str,
            "expiry_note": expiry_note,
            "created_at": today_str,
            "expired_at": expired_at
        })

    # 6. 만료 후 7일 지난 쿠폰 자동 삭제
    final_list = []
    for item in updated_list:
        if item["status"] == "EXPIRED" and item.get("expired_at"):
            try:
                exp_dt = datetime.strptime(item["expired_at"], "%Y-%m-%d").replace(tzinfo=KST)
                if (now_kst - exp_dt).days > 7:
                    continue
            except Exception:
                pass
        final_list.append(item)

    # 7. 사용 가능(ACTIVE) 쿠폰 상단 정렬
    final_list.sort(key=lambda x: (0 if x["status"] == "ACTIVE" else 1, x["code"]))

    # JSON 저장
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
        
    print(f"[{config['name']}] 동기화 완료!")

if __name__ == "__main__":
    for game_key, config in GAMES_CONFIG.items():
        process_game_coupons(game_key, config)
