import json
import os
import re
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

# 1. 게임별 설정
GAMES_CONFIG = {
    "afk-journey": {
        "name": "AFK 새로운 여정",
        "lounge_id": "AFK_Journey",
        "file_name": "afk_journey.json"
    }
}

# 2. 쿠폰 코드가 아닌 시스템/메뉴 차단 단어
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
    "NAVER", "LOUNGE", "LOUNGEID", "NOTICE", "BOARD"
}

# 3. 상시 유지 쿠폰 (만료 예외)
PERMANENT_CODES = {"AFKJ10"}

def parse_expiry_date(text, created_date):
    """게시글 텍스트에서 만료 날짜(~8월 31일, ~2026.08.31 등) 정밀 추출"""
    current_year = created_date.year
    
    # 패턴 1: 2026.08.31 / 2026-08-31 / 2026/08/31
    match_full = re.search(r'20\d{2}[.-/](\d{1,2})[.-/](\d{1,2})', text)
    if match_full:
        m, d = int(match_full.group(1)), int(match_full.group(2))
        try:
            return datetime(current_year, m, d).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 패턴 2: ~8월 31일 / ~08월31일
    match_kor = re.search(r'(?:~\s*|까지\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일', text)
    if match_kor:
        m, d = int(match_kor.group(1)), int(match_kor.group(2))
        try:
            return datetime(current_year, m, d).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 패턴 3: ~8/31 / ~08/31
    match_slash = re.search(r'(?:~\s*|까지\s*)(\d{1,2})/(\d{1,2})', text)
    if match_slash:
        m, d = int(match_slash.group(1)), int(match_slash.group(2))
        try:
            return datetime(current_year, m, d).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 만료일 문구가 없는 경우 -> 기본 14일 뒤로 설정
    default_expiry = created_date + timedelta(days=14)
    return default_expiry.strftime("%Y-%m-%d")

def extract_korean_rewards(text):
    """한국어 보상 문구 파싱"""
    rewards = []
    
    patterns = [
        r'(일반\s*전체\s*소환권|에픽\s*초대장|일반\s*초대장|다이아|골드|종이접기\s*햄스터|영웅의\s*정수|별의\s*결정)\s*x?\s*(\d+만?개?)'
    ]
    
    for p in patterns:
        matches = re.findall(p, text)
        for item, qty in matches:
            rewards.append(f"{item.strip()} {qty.strip()}")
            
    if rewards:
        return ", ".join(list(dict.fromkeys(rewards)))
    return "게임 아이템 보상"

def fetch_from_naver_lounge(lounge_id):
    """네이버 게임 라운지 공식 게시판 실시간 수집"""
    parsed_coupons = {}
    today = datetime.now()
    
    # 검색 쿼리: 쿠폰
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
                    
                    # 게시글 작성일 파싱
                    created_date = today
                    
                    # 5~20자리 쿠폰 코드 찾기
                    codes = re.findall(r'\b[A-Z0-9]{5,20}\b', full_text)
                    for code in codes:
                        if code in EXCLUDED_CODES:
                            continue
                            
                        expiry_date_str = parse_expiry_date(full_text, created_date)
                        reward_str = extract_korean_rewards(full_text)
                        
                        if code not in parsed_coupons:
                            parsed_coupons[code] = {
                                "rewards": reward_str,
                                "expired_at": expiry_date_str
                            }
    except Exception as e:
        print(f"네이버 라운지 파싱 중 예외: {e}")
        
    return parsed_coupons

def process_game_coupons(game_key, config):
    print(f"[{config['name']}] 네이버 공식 라운지 쿠폰 & 만료일 수집 시작...")
    file_name = config["file_name"]
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    
    # 1. 기존 파일 불러오기
    existing_data = {}
    if os.path.exists(file_name):
        try:
            with open(file_name, "r", encoding="utf-8") as f:
                raw = json.load(f)
                for item in raw:
                    code = item.get("code")
                    if code:
                        existing_data[code] = item
        except Exception:
            existing_data = {}

    # 2. 네이버 라운지 실시간 수집
    lounge_coupons = fetch_from_naver_lounge(config["lounge_id"])
    
    # 3. 데이터 통합 및 만료 상태 판별
    for code, info in lounge_coupons.items():
        exp_date_str = info["expired_at"]
        rewards = info["rewards"]
        
        # 상시 쿠폰 예외 처리
        if code in PERMANENT_CODES:
            status = "ACTIVE"
            exp_date_str = None
        else:
            # 만료일과 오늘 날짜 비교
            try:
                exp_dt = datetime.strptime(exp_date_str, "%Y-%m-%d")
                status = "EXPIRED" if exp_dt < today else "ACTIVE"
            except Exception:
                status = "ACTIVE"
                
        existing_data[code] = {
            "code": code,
            "rewards": rewards if rewards != "게임 아이템 보상" or code not in existing_data else existing_data[code].get("rewards", rewards),
            "status": status,
            "created_at": existing_data.get(code, {}).get("created_at", today_str),
            "expired_at": exp_date_str
        }

    # 4. 만료 후 7일 지난 데이터 완전 삭제
    final_list = []
    for code, item in existing_data.items():
        if item["status"] == "EXPIRED" and item.get("expired_at"):
            try:
                exp_dt = datetime.strptime(item["expired_at"], "%Y-%m-%d")
                if (today - exp_dt).days > 7:
                    continue # 7일 경과 시 자동 삭제
            except Exception:
                pass
        final_list.append(item)

    # JSON 저장
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
    print(f"[{config['name']}] 네이버 라운지 기반 수집 및 만료일 동기화 완료!")

if __name__ == "__main__":
    for game_key, config in GAMES_CONFIG.items():
        process_game_coupons(game_key, config)
