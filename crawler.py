import json
import os
import re
import urllib.request
from datetime import datetime, timezone, timedelta
import cloudscraper
from bs4 import BeautifulSoup

# 한국 표준시(KST) 타임존 설정 (UTC+9)
KST = timezone(timedelta(hours=9))
NOW_KST_STR = datetime.now(KST).strftime("%Y.%m.%d. %H시 갱신")

# ==========================================
# 💎 원신(Genshin Impact) 한국 정식 서비스 아이템명 100% 팩트체크 사전
# ==========================================
GENSHIN_ITEM_MAP = {
    # 1. 재화 & 캐릭터 경험치 소재
    "Primogem": "원석",
    "Mora": "모라",
    "Hero's Wit": "영웅의 경험",
    "Adventurer's Experience": "모험가의 경험",
    "Wanderer's Advice": "방랑자의 경험",
    
    # 2. 무기 강화 소재 (인게임 정식 명칭)
    "Mystic Enhancement Ore": "정제용 마법 광물",
    "Fine Enhancement Ore": "양질의 마법 광물",
    "Enhancement Ore": "마법 광물",
    
    # 3. 기원(뽑기) 재화 & 고급 소재
    "Intertwined Fate": "뒤얽힌 인연",
    "Acquaint Fate": "만남의 인연",
    "Crown of Insight": "지식의 왕관",
    
    # 4. 수지 & 성유물 강화 소재
    "Fragile Resin": "약한 수지",
    "Transient Resin": "단기 수지",
    "Sanctifying Unction": "축복의 연고",
    "Sanctifying Essence": "축복의 정수",
    
    # 5. 음식 아이템 (인게임 정식 명칭)
    "Jueyun Chili Chicken": "절운고추 닭고기 무침",
    "Stir-Fried Fish Noodles": "생선 볶음면",
    "Sweet Madame": "달콤달콤 닭고기 스튜",
    "Northern Apple Stew": "북국의 사과 스튜",
    
    # 6. 이벤트 아이템
    "Masked Ball Invitation Letter": "가면 무도회 초대장"
}

def translate_genshin_rewards(rewards_text):
    """영문 보상 텍스트를 원신 한국 정식 명칭 및 수량(개)으로 자동 팩트체크 변환"""
    lines = [line.strip() for line in rewards_text.split('\n') if line.strip()]
    translated_items = []

    for line in lines:
        match = re.search(r'^(.*?)(?:\s*[×xX,]\s*(\d[\d,]*))?$', line)
        if match:
            item_name = match.group(1).strip()
            amount = match.group(2)
            ko_name = GENSHIN_ITEM_MAP.get(item_name, item_name)
            
            if amount:
                translated_items.append(f"{ko_name} {amount}개")
            else:
                translated_items.append(f"{ko_name}")
        else:
            translated_items.append(line)

    return ", ".join(translated_items) if translated_items else "원석 및 인게임 보상"

def process_genshin():
    """원신 위키(Fandom Wiki) 표 구조 직접 파싱 전용 크롤러"""
    url = "https://genshin-impact.fandom.com/wiki/Promotional_Code"
    print("=== [원신 (Fandom Wiki)] 정밀 수집 시작 ===")
    
    active_coupons = []
    expired_coupons = []
    seen_codes = set()
    
    html = ""
    try:
        scraper = cloudscraper.create_scraper()
        resp = scraper.get(url, timeout=15)
        if resp.status_code == 200:
            html = resp.text
    except Exception as e:
        print(f"[Genshin Cloudscraper 실패]: {e}")

    if not html:
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode('utf-8')
        except Exception as e:
            print(f"[Genshin Urllib 실패]: {e}")

    if html:
        try:
            soup = BeautifulSoup(html, 'html.parser')
            tables = soup.find_all('table', class_=['article-table', 'wikitable'])
            
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cols = row.find_all(['td', 'th'])
                    if len(cols) < 4:
                        continue
                    
                    code_raw = cols[0].get_text(strip=True)
                    server_raw = cols[1].get_text(strip=True)
                    reward_raw = cols[2].get_text('\n', strip=True)
                    duration_raw = cols[3].get_text(' ', strip=True)
                    
                    # 헤더 행 스킵
                    if "Code" in code_raw and "Server" in server_raw:
                        continue
                        
                    # 1. 한국 서버 유효성 검사 (China 전용 제외, Asia / Global 포함)
                    if "China" in server_raw and "Asia" not in server_raw:
                        continue
                        
                    # 2. 주석 번호 [1], [2] 제거 및 코드 추출
                    code = re.sub(r'\[.*?\]', '', code_raw).strip()
                    if not code or len(code) < 4:
                        continue
                        
                    code_upper = code.upper()
                    if code_upper in seen_codes:
                        continue
                        
                    # 3. 보상 한글 변환
                    rewards_ko = translate_genshin_rewards(reward_raw)
                    
                    # 4. 만료 여부 및 정확한 만료 날짜 추출
                    is_expired = "Expired" in duration_raw or "expired" in cols[3].get('class', [])
                    
                    if is_expired:
                        status = "EXPIRED"
                        exp_match = re.search(r'Expired:\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})', duration_raw, re.IGNORECASE)
                        if exp_match:
                            expiry_note = f"{exp_match.group(1)} 만료됨"
                        else:
                            expiry_note = "사용 만료"
                    else:
                        status = "ACTIVE"
                        valid_match = re.search(r'Valid until:\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})', duration_raw, re.IGNORECASE)
                        if valid_match:
                            expiry_note = f"{valid_match.group(1)}까지"
                        elif "indefinite" in duration_raw.lower():
                            expiry_note = "상시 유효"
                        else:
                            expiry_note = "유효"
                            
                    coupon_obj = {
                        "code": code_upper,
                        "rewards": rewards_ko,
                        "status": status,
                        "expiry_note": expiry_note,
                        "updated_at": NOW_KST_STR
                    }
                    
                    if status == "ACTIVE":
                        active_coupons.append(coupon_obj)
                    else:
                        expired_coupons.append(coupon_obj)
                        
                    seen_codes.add(code_upper)
        except Exception as e:
            print(f"[Genshin 파싱 오류]: {e}")

    final_list = active_coupons + expired_coupons
    with open("genshin.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
        
    print(f"[genshin.json] 저장 완료! (총 {len(final_list)}개 코드)")

def process_afk_journey():
    """AFK 새로운 여정 자동 크롤러"""
    print("=== [AFK 새로운 여정] 쿠폰 수집 시작 ===")
    url = "https://buffhub.com/blog/afk-journey/"
    
    always_active = ["AFKJ10"]
    known_expired = ["HQCOZFSC6QYTX", "4IYTSNBDXC", "B52F8N5OPOG7K", "E8BESLBQZLZUD", "H7PDTYNR61", "SMALLGIFTFROMPEGGY"]
    reward_overrides = {"AFKJ10": "일반 전체 소환권 10개"}
    
    active_coupons = []
    expired_coupons = []
    seen_codes = set()
    
    try:
        scraper = cloudscraper.create_scraper()
        resp = scraper.get(url, timeout=15)
        html = resp.text if resp.status_code == 200 else ""
    except Exception:
        html = ""

    if html:
        soup = BeautifulSoup(html, 'html.parser')
        paragraphs = soup.find_all(['p', 'li', 'td'])
        for p in paragraphs:
            text = p.get_text()
            code_matches = re.findall(r'\b[A-Za-z0-9]{8,20}\b', text)
            for code in code_matches:
                code_upper = code.upper()
                if code_upper in seen_codes:
                    continue
                if any(kw in code_upper for kw in ['BUFFHUB', 'COUPON', 'REDEMPTION', 'JOURNEY', 'VERSION']):
                    if code_upper not in always_active and code_upper not in known_expired:
                        continue
                
                status = "EXPIRED" if code_upper in known_expired else "ACTIVE"
                reward = reward_overrides.get(code_upper, "인게임 보상 (다이아 / 소환권 / 골드)")
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

    for code in always_active:
        if code not in seen_codes:
            active_coupons.append({
                "code": code,
                "rewards": reward_overrides.get(code, "공식 지원 보상"),
                "status": "ACTIVE",
                "expiry_note": "상시 유효",
                "updated_at": NOW_KST_STR
            })
            seen_codes.add(code)

    final_list = active_coupons + expired_coupons
    with open("afk_journey.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
    print("[afk_journey.json] 저장 완료!")

def main():
    process_afk_journey()
    process_genshin()

if __name__ == "__main__":
    main()
