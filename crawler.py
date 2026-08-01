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
NOW_KST_STR = datetime.now(KST).strftime("%Y.%m.%d. %H시 갱신")

# ==========================================
# 게임별 쿠폰/리딤코드 데이터베이스 및 설정
# ==========================================
GAMES_CONFIG = {
    "afk_journey": {
        "file_name": "afk_journey.json",
        "url": "https://buffhub.com/blog/afk-journey/",
        "always_active": ["AFKJ10"],
        "known_expired": ["HQCOZFSC6QYTX", "4IYTSNBDXC", "B52F8N5OPOG7K", "E8BESLBQZLZUD", "H7PDTYNR61", "SMALLGIFTFROMPEGGY"],
        "reward_overrides": {
            "AFKJ10": "일반 전체 소환권 10개"
        }
    },
    "genshin": {
        "file_name": "genshin.json",
        "url": "https://buffhub.com/blog/genshin-impact/",
        "always_active": [],
        "known_expired": ["GENSHINGIFT"],
        "reward_overrides": {}
    }
}

def fetch_html_buffhub(url):
    """Buffhub 웹페이지 HTML 가져오기"""
    try:
        scraper = cloudscraper.create_scraper()
        resp = scraper.get(url, timeout=15)
        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        print(f"[{url}] Cloudscraper 실패: {e}")
    
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        print(f"[{url}] Urllib 실패: {e}")
        return None

def process_game_coupons(game_key, config):
    print(f"=== [{game_key}] 리딤코드 크롤링 시작 ===")
    html = fetch_html_buffhub(config["url"])
    
    active_coupons = []
    expired_coupons = []
    seen_codes = set()
    
    if html:
        soup = BeautifulSoup(html, 'html.parser')
        paragraphs = soup.find_all(['p', 'li', 'td'])
        
        for p in paragraphs:
            text = p.get_text()
            if not text:
                continue
                
            code_matches = re.findall(r'\b[A-Za-z0-9]{8,20}\b', text)
            for code in code_matches:
                code_upper = code.upper()
                if code_upper in seen_codes:
                    continue
                    
                # 공통 제외 키워드 필터링
                if any(kw in code_upper for kw in ['BUFFHUB', 'COUPON', 'REDEMPTION', 'GENSHIN', 'JOURNEY', 'VERSION']):
                    if code_upper not in config["always_active"] and code_upper not in config["known_expired"]:
                        continue

                # 기본 활성/만료 판별
                if code_upper in config["known_expired"]:
                    status = "EXPIRED"
                else:
                    status = "ACTIVE"
                    
                reward = config["reward_overrides"].get(code_upper, "원신 인게임 보상 (원석 / 모라 / 경험치)")
                expiry_note = "만료일 미정" if status == "ACTIVE" else "사용 만료"
                
                coupon_obj = {
                    "code": code_upper,
                    "rewards": reward,
                    "status": status,
                    "expiry_note": expiry_note,
                    "updated_at": NOW_KST_STR
                }
                
                if status == "ACTIVE":
                    active_coupons.append(coupon_obj)
                else:
                    expired_coupons.append(coupon_obj)
                seen_codes.add(code_upper)

    # 상시 활성 쿠폰 추가 보장
    for code in config["always_active"]:
        if code not in seen_codes:
            active_coupons.append({
                "code": code,
                "rewards": config["reward_overrides"].get(code, "공식 지원 보상"),
                "status": "ACTIVE",
                "expiry_note": "상시 유효",
                "updated_at": NOW_KST_STR
            })
            seen_codes.add(code)

    # 최종 정렬 (ACTIVE 우선)
    final_list = active_coupons + expired_coupons
    
    # JSON 파일 저장
    with open(config["file_name"], "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
        
    print(f"[{config['file_name']}] 저장 완료! (총 {len(final_list)}개 코드)")

def main():
    for game_key, config in GAMES_CONFIG.items():
        process_game_coupons(game_key, config)

if __name__ == "__main__":
    main()
