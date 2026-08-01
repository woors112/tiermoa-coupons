import requests
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime

# 1. 게임별 타겟 URL 및 저장 파일 설정
GAMES_CONFIG = {
    "afk-journey": {
        "name": "AFK 새로운 여정",
        "url": "https://www.afk.global/afk-journey/codes",
        "file_name": "afk_journey.json"
    }
}

# 2. 영문 보상 ➔ 한국 공식 서비스 명칭 자동 변환 매핑
ITEM_TRANSLATIONS = {
    "Diamond": "다이아",
    "Diamonds": "다이아",
    "Gold": "골드",
    "Invite Letter": "일반 초대장",
    "Invite Letters": "일반 초대장",
    "Epic Invite Letter": "에픽 초대장",
    "Epic Invite Letters": "에픽 초대장",
    "Stellar Crystal": "별의 결정",
    "Stellar Crystals": "별의 결정",
    "Hero Essence": "영웅의 정수",
    "Soulstone": "영웅 영혼석",
    "Soulstones": "영웅 영혼석"
}

def translate_to_korean(raw_text):
    """영문 보상을 한국어 공식 아이템 이름으로 자동 변환"""
    if not raw_text or len(raw_text.strip()) == 0:
        return "게임 보상 아이템"
    
    result = raw_text
    for eng, kor in ITEM_TRANSLATIONS.items():
        pattern = re.compile(re.escape(eng), re.IGNORECASE)
        result = pattern.sub(kor, result)
    return result.strip()

def process_game_coupons(game_key, config):
    print(f"[{config['name']}] 쿠폰 수집 시작...")
    file_name = config["file_name"]
    url = config["url"]
    
    # 기존 데이터 불러오기
    if os.path.exists(file_name):
        with open(file_name, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
    else:
        existing_data = []

    # 크롤링 요청
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    scraped_coupons = {}
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            # afk.global 표(tr) 및 카드 요소에서 쿠폰 추출
            items = soup.select("tr, .code-row, .coupon-item")
            for item in items:
                text = item.get_text(separator=" ")
                # 5자리 이상 대문자/숫자 코드를 검색
                code_match = re.search(r'\b[A-Z0-9]{5,20}\b', text)
                if code_match:
                    code = code_match.group(0)
                    rewards = translate_to_korean(text.replace(code, ""))
                    scraped_coupons[code] = rewards
    except Exception as e:
        print(f"[{config['name']}] 크롤링 실패: {e}")

    # 3단계 라이프사이클 처리
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    coupon_dict = {item['code']: item for item in existing_data}

    # A. 신규 및 활성 쿠폰 반영
    for code, rewards in scraped_coupons.items():
        if code not in coupon_dict:
            coupon_dict[code] = {
                "code": code,
                "rewards": rewards,
                "status": "ACTIVE",
                "created_at": today_str,
                "expired_at": None
            }
        else:
            coupon_dict[code]["rewards"] = rewards
            if coupon_dict[code]["status"] == "EXPIRED":
                coupon_dict[code]["status"] = "ACTIVE"
                coupon_dict[code]["expired_at"] = None

    # B. 사라진 쿠폰 만료 처리 및 7일 후 삭제
    scraped_set = set(scraped_coupons.keys())
    updated_data = []

    for code, item in list(coupon_dict.items()):
        if code not in scraped_set and item["status"] == "ACTIVE":
            item["status"] = "EXPIRED"
            item["expired_at"] = today_str

        # 만료된 지 7일 경과 여부 확인
        if item["status"] == "EXPIRED" and item["expired_at"]:
            expired_date = datetime.strptime(item["expired_at"], "%Y-%m-%d")
            if (today - expired_date).days > 7:
                continue # 7일 경과 시 목록에서 완전 삭제

        updated_data.append(item)

    # JSON 저장
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(updated_data, f, ensure_ascii=False, indent=2)
    print(f"[{config['name']}] 처리 완료!")

if __name__ == "__main__":
    for game_key, config in GAMES_CONFIG.items():
        process_game_coupons(game_key, config)
