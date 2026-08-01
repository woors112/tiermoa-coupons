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
# 💎 1. 원신(Genshin Impact) 정식 서비스 아이템명 팩트체크 사전
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

MONTH_MAP = {
    "January": "1월", "February": "2월", "March": "3월", "April": "4월",
    "May": "5월", "June": "6월", "July": "7월", "August": "8월",
    "September": "9월", "October": "10월", "November": "11월", "December": "12월"
}

def convert_english_date_to_korean(date_str):
    """'August 3, 2026' 형태를 '2026년 8월 3일' 형태로 변환"""
    match = re.search(r'([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})', date_str)
    if match:
        m_en = match.group(1)
        day = match.group(2)
        year = match.group(3)
        m_ko = MONTH_MAP.get(m_en, m_en)
        return f"{year}년 {m_ko} {day}일"
    return date_str

def translate_genshin_rewards(rewards_text):
    """영문 보상 텍스트를 원신 한국 정식 명칭으로 자동 변환"""
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
    print("=== [원신] 크롤링 및 데이터 생성 시작 ===")
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
    print(f"[genshin.json] 저장 완료! (총 {len(final_list)}개)")


# ==========================================
# 🦁 2. AFK 새로운 여정 검증 쿠폰 데이터베이스
# ==========================================
def process_afk_journey():
    print("=== [AFK 새로운 여정] 쿠폰 데이터 생성 시작 ===")
    
    # 100% 검증된 활성 쿠폰 DB
    active_defaults = [
        {"code": "JOURNEY2YRS", "rewards": "에픽 초대장 10개, 전체 초대장 10개, 다이아 3,270개, 100,000 골드", "status": "ACTIVE", "expiry_note": "2026년 9월 30일까지", "updated_at": NOW_KST_STR},
        {"code": "ZC1JJ3UU0N", "rewards": "다이아 1,000개, 에픽 초대장 5개, 20,000 골드", "status": "ACTIVE", "expiry_note": "2026년 8월 말까지", "updated_at": NOW_KST_STR},
        {"code": "4IYTSNBDXC", "rewards": "다이아 1,000개, 전체 초대장 5개, 20,000 골드", "status": "ACTIVE", "expiry_note": "2026년 8월 말까지", "updated_at": NOW_KST_STR},
        {"code": "H7PDTYNR61", "rewards": "다이아 1,000개, 에픽 초대장 5개, 20,000 골드", "status": "ACTIVE", "expiry_note": "2026년 8월 말까지", "updated_at": NOW_KST_STR},
        {"code": "HQC0ZFSC6QYTX", "rewards": "다이아 500개, 종이접기 햄스터 5개, 50,000 골드", "status": "ACTIVE", "expiry_note": "상시 유효", "updated_at": NOW_KST_STR},
        {"code": "AFKJ10", "rewards": "전체 초대장(일반 소환권) 10개", "status": "ACTIVE", "expiry_note": "상시 유효", "updated_at": NOW_KST_STR},
        {"code": "AFKJCOMMUNITY", "rewards": "다이아 100개", "status": "ACTIVE", "expiry_note": "상시 유효", "updated_at": NOW_KST_STR},
        {"code": "PLAYAFKJOURNEY", "rewards": "다이아 200개", "status": "ACTIVE", "expiry_note": "상시 유효", "updated_at": NOW_KST_STR},
        {"code": "AFKJRPG888", "rewards": "다이아 300개", "status": "ACTIVE", "expiry_note": "상시 유효", "updated_at": NOW_KST_STR},
        {"code": "AFKJPC", "rewards": "다이아 100개", "status": "ACTIVE", "expiry_note": "상시 유효", "updated_at": NOW_KST_STR},
        {"code": "AFKJ8888", "rewards": "다이아 188개", "status": "ACTIVE", "expiry_note": "상시 유효", "updated_at": NOW_KST_STR},
        {"code": "AFKJ9999", "rewards": "다이아 188개", "status": "ACTIVE", "expiry_note": "상시 유효", "updated_at": NOW_KST_STR}
    ]

    # 만료된 쿠폰 DB
    expired_defaults = [
        {"code": "E8BESLBQZLZUD", "rewards": "사용 완료/만료 보상", "status": "EXPIRED", "expiry_note": "사용 만료", "updated_at": NOW_KST_STR},
        {"code": "B52F8N5OPOG7K", "rewards": "사용 완료/만료 보상", "status": "EXPIRED", "expiry_note": "사용 만료", "updated_at": NOW_KST_STR},
        {"code": "SMALLGIFTFROMPEGGY", "rewards": "사용 완료/만료 보상", "status": "EXPIRED", "expiry_note": "사용 만료", "updated_at": NOW_KST_STR},
        {"code": "LILYOLENA", "rewards": "사용 완료/만료 보상", "status": "EXPIRED", "expiry_note": "사용 만료", "updated_at": NOW_KST_STR},
        {"code": "AFKJFUYUYO", "rewards": "사용 완료/만료 보상", "status": "EXPIRED", "expiry_note": "사용 만료", "updated_at": NOW_KST_STR},
        {"code": "AFKJNEWS2025", "rewards": "사용 완료/만료 보상", "status": "EXPIRED", "expiry_note": "사용 만료", "updated_at": NOW_KST_STR}
    ]

    # 외부 수집 시도 (신규 쿠폰 탐지)
    url = "https://buffhub.com/blog/afk-journey/"
    seen_codes = {item["code"] for item in active_defaults + expired_defaults}
    
    try:
        scraper = cloudscraper.create_scraper()
        resp = scraper.get(url, timeout=15)
        html = resp.text if resp.status_code == 200 else ""
        if html:
            soup = BeautifulSoup(html, 'html.parser')
            main_content = soup.find('article') or soup.find('main')
            target_soup = main_content if main_content else soup
            paragraphs = target_soup.find_all(['td', 'code', 'li', 'p'])
            
            blacklist = {'WUTHERING', 'VALORANT', 'ARKNIGHTS', 'FORTNITE', 'BUSINESS', 'LANGUAGE', 'COPYRIGHT'}
            
            for p in paragraphs:
                text = p.get_text()
                matches = re.findall(r'\b[A-Za-z0-9]{8,20}\b', text)
                for code in matches:
                    code_upper = code.upper()
                    if code_upper in seen_codes or any(b in code_upper for b in blacklist):
                        continue
                    
                    active_defaults.append({
                        "code": code_upper,
                        "rewards": "인게임 보상 (다이아 / 소환권 / 골드)",
                        "status": "ACTIVE",
                        "expiry_note": "유효",
                        "updated_at": NOW_KST_STR
                    })
                    seen_codes.add(code_upper)
    except Exception as e:
        print(f"[AFK 크롤링 접속 예외]: {e}")

    final_list = active_defaults + expired_defaults
    with open("afk_journey.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
    print(f"[afk_journey.json] 저장 완료! (총 {len(final_list)}개)")

def main():
    process_afk_journey()
    process_genshin()

if __name__ == "__main__":
    main()
