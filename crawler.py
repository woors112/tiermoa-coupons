import json
import os
import re
import urllib.request
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import cloudscraper

# 한국 표준시(KST) 타임존 설정 (UTC+9)
KST = timezone(timedelta(hours=9))
NOW_KST_STR = datetime.now(KST).strftime("%Y.%m.%d. %H시 갱신")

# ==========================================
# 💎 원신(Genshin Impact) 한국 정식 서비스 아이템명 팩트체크 사전
# ==========================================
GENSHIN_ITEM_MAP = {
    "Primogem": "원석",
    "Mora": "모라",
    "Hero's Wit": "영웅의 경험",
    "Adventurer's Experience": "모험가의 경험",
    "Wanderer's Advice": "방랑자의 경험",
    "Mystic Enhancement Ore": "정제용 마법 광물",
    "Fine Enhancement Ore": "양질의 마법 광물",
    "Enhancement Ore": "마법 광물",
    "Intertwined Fate": "뒤얽힌 인연",
    "Acquaint Fate": "만남의 인연",
    "Crown of Insight": "지식의 왕관",
    "Fragile Resin": "약한 수지",
    "Transient Resin": "단기 수지",
    "Sanctifying Unction": "축복의 연고",
    "Sanctifying Essence": "축복의 정수",
    "Jueyun Chili Chicken": "절운고추 닭고기 무침",
    "Stir-Fried Fish Noodles": "생선 볶음면",
    "Sweet Madame": "달콤달콤 닭고기 스튜",
    "Northern Apple Stew": "북국의 사과 스튜",
    "Masked Ball Invitation Letter": "가면 무도회 초대장"
}

# 영문 월(Month) 이름을 한글로 변환하는 사전
MONTH_MAP = {
    "January": "1월", "February": "2월", "March": "3월", "April": "4월",
    "May": "5월", "June": "6월", "July": "7월", "August": "8월",
    "September": "9월", "October": "10월", "November": "11월", "December": "12월"
}

def convert_english_date_to_korean(date_str):
    """'August 3, 2026' 같은 영문 날짜를 '2026년 8월 3일' 형태로 변환"""
    match = re.search(r'([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})', date_str)
    if match:
        m_en = match.group(1)
        day = match.group(2)
        year = match.group(3)
        m_ko = MONTH_MAP.get(m_en, m_en)
        return f"{year}년 {m_ko} {day}일"
    return date_str

def translate_genshin_rewards(rewards_text):
    """영문 보상 텍스트를 원신 한국 정식 명칭 및 수량(개)으로 자동 변환"""
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

def fetch_fandom_via_api():
    api_url = "https://genshin-impact.fandom.com/api.php?action=parse&page=Promotional_Code&format=json"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    req = urllib.request.Request(api_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            res_json = json.loads(resp.read().decode('utf-8'))
            return res_json.get('parse', {}).get('text', {}).get('*', '')
    except Exception as e:
        print(f"[Fandom API 실패]: {e}")
        return ""

def process_genshin():
    print("=== [원신] 크롤링 및 날짜 한글화 시작 ===")
    
    active_coupons = []
    expired_coupons = []
    seen_codes = set()

    fandom_html = fetch_fandom_via_api()
    if fandom_html:
        try:
            soup = BeautifulSoup(fandom_html, 'html.parser')
            tables = soup.find_all('table', class_=['article-table', 'wikitable'])
            
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cols = row.find_all(['td', 'th'])
                    if len(cols) < 4:
                        continue
                    
                    server_raw = cols[1].get_text(strip=True)
                    reward_raw = cols[2].get_text('\n', strip=True)
                    duration_raw = cols[3].get_text(' ', strip=True)
                    
                    if "Server" in server_raw and "Rewards" in reward_raw:
                        continue
                    if "China" in server_raw and "Asia" not in server_raw:
                        continue
                    
                    code_texts = [code_tag.get_text(strip=True) for code_tag in cols[0].find_all(['code', 'a', 'b', 'span'])]
                    if not code_texts:
                        code_texts = [cols[0].get_text(strip=True)]
                        
                    for raw_code in code_texts:
                        code = re.sub(r'\[.*?\]', '', raw_code).strip()
                        if not code or len(code) < 4 or code.upper() in ["CODE", "SERVER"]:
                            continue
                            
                        code_upper = code.upper()
                        if code_upper in seen_codes:
                            continue
                            
                        rewards_ko = translate_genshin_rewards(reward_raw)
                        is_expired = "Expired" in duration_raw or "expired" in cols[3].get('class', [])
                        
                        if is_expired:
                            status = "EXPIRED"
                            exp_match = re.search(r'Expired:\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})', duration_raw, re.IGNORECASE)
                            if exp_match:
                                ko_date = convert_english_date_to_korean(exp_match.group(1))
                                expiry_note = f"{ko_date} 만료됨"
                            else:
                                expiry_note = "사용 만료"
                        else:
                            status = "ACTIVE"
                            valid_match = re.search(r'Valid until:\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})', duration_raw, re.IGNORECASE)
                            if valid_match:
                                ko_date = convert_english_date_to_korean(valid_match.group(1))
                                expiry_note = f"{ko_date}까지"
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
            print(f"[Fandom 파싱 에러]: {e}")

    # 백업 기본 세트 (유효성 보장)
    full_backups = [
        {"code": "GENSHINGIFT", "rewards": "원석 50개, 영웅의 경험 3개", "status": "ACTIVE", "expiry_note": "상시 유효", "updated_at": NOW_KST_STR},
        {"code": "EVERWINTER", "rewards": "원석 100개, 정제용 마법 광물 10개", "status": "ACTIVE", "expiry_note": "2026년 8월 3일까지", "updated_at": NOW_KST_STR},
        {"code": "ONTOSNEZHNAYA", "rewards": "원석 100개, 영웅의 경험 5개", "status": "ACTIVE", "expiry_note": "2026년 8월 3일까지", "updated_at": NOW_KST_STR},
        {"code": "ODETTE0812", "rewards": "원석 100개, 모라 50,000개", "status": "ACTIVE", "expiry_note": "2026년 8월 3일까지", "updated_at": NOW_KST_STR},
        {"code": "LEGEDILJKSGM", "rewards": "원석 60개, 모험가의 경험 5개", "status": "ACTIVE", "expiry_note": "2026년 9월 2일까지", "updated_at": NOW_KST_STR},
        {"code": "2BJ64QRZ7RT8", "rewards": "원석 60개, 모험가의 경험 5개", "status": "ACTIVE", "expiry_note": "유효", "updated_at": NOW_KST_STR},
        {"code": "UIVIBUQM6Q8A", "rewards": "모라 10,000개, 모험가의 경험 10개, 양질의 마법 광물 5개, 절운고추 닭고기 무침 5개, 생선 볶음면 5개", "status": "ACTIVE", "expiry_note": "유효", "updated_at": NOW_KST_STR},
        {"code": "UIVI13C8X156", "rewards": "모라 10,000개, 모험가의 경험 10개, 양질의 마법 광물 5개, 절운고추 닭고기 무침 5개, 생선 볶음면 5개", "status": "ACTIVE", "expiry_note": "유효", "updated_at": NOW_KST_STR}
    ]

    for fb in full_backups:
        if fb["code"] not in seen_codes:
            active_coupons.append(fb)

    final_list = active_coupons + expired_coupons
    with open("genshin.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
        
    print(f"[genshin.json] 저장 완료! (총 {len(final_list)}개 코드)")

def process_afk_journey():
    """AFK 새로운 여정 정밀 크롤러 (푸터/타게임 오탐지 완벽 제거)"""
    print("=== [AFK 새로운 여정] 크롤링 시작 ===")
    url = "https://buffhub.com/blog/afk-journey/"
    
    always_active = ["AFKJ10"]
    known_expired = ["HQCOZFSC6QYTX", "4IYTSNBDXC", "B52F8N5OPOG7K", "E8BESLBQZLZUD", "H7PDTYNR61", "SMALLGIFTFROMPEGGY"]
    reward_overrides = {"AFKJ10": "일반 전체 소환권 10개"}
    
    # 🚫 수집에서 완전히 제외시킬 타 게임명 및 일반 영문 단어 블랙리스트
    blacklist_words = {
        'WUTHERING', 'ARKNIGHTS', 'ENDFIELD', 'SURVIVAL', 'NEVERNESS', 'EVERNESS', 'WHITEOUT', 
        'IDENTITY', 'GENERATION', 'VALORANT', 'KINGDOMS', 'PLAYSTATION', 'HEARTOPIA', 'VOUCHERS', 
        'MILIASTRA', 'WONDERLAND', 'FORTNITE', 'MONOPOLY', 'PROTOCOL', 'RESONANCE', 'BREAKOUT', 
        'INFINITY', 'DEEPSPACE', 'NIGHTMARE', 'UMAMUSUME', 'DIAMONDS', 'HAMSTERS', 'ENHANCEMENT', 
        'NAVIGATION', 'GLOBENEWSWIRE', 'BENZINGA', 'BUSINESS', 'FIDELITY', 'COPYRIGHT', 'LANGUAGE', 
        'CURRENCY', 'INDONESIA', 'ITALIANO', 'MESSAGES', 'REDEMPTION', 'JOURNEY', 'VERSION', 'BUFFHUB'
    }

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
        # 사이드바/푸터 제외하고 메인 본문 영역(article 또는 main)만 지정
        main_content = soup.find('article') or soup.find('main') or soup.find(class_=re.compile(r'content|post|entry'))
        
        target_soup = main_content if main_content else soup
        
        # 본문 내 표(table)나 리스트(li/td/code)에서 수집
        paragraphs = target_soup.find_all(['td', 'code', 'li', 'p'])
        for p in paragraphs:
            text = p.get_text()
            code_matches = re.findall(r'\b[A-Za-z0-9]{8,20}\b', text)
            for code in code_matches:
                code_upper = code.upper()
                if code_upper in seen_codes:
                    continue
                
                # 블랙리스트 단어는 모두 스킵
                if code_upper in blacklist_words:
                    continue
                if any(kw in code_upper for kw in blacklist_words):
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

    # 상시 쿠폰 보장
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
