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
# 💎 1. 원신(Genshin Impact) 용어 사전 & 크롤러
# ==========================================
GENSHIN_ITEM_MAP = {
    "Primogem": "원석", "Mora": "모라", "Hero's Wit": "영웅의 경험",
    "Adventurer's Experience": "모험가의 경험", "Wanderer's Advice": "방랑자의 경험",
    "Mystic Enhancement Ore": "정제용 마법 광물", "Fine Enhancement Ore": "양질의 마법 광물",
    "Enhancement Ore": "마법 광물", "Intertwined Fate": "뒤얽힌 인연",
    "Acquaint Fate": "만남의 인연", "Crown of Insight": "지식의 왕관",
    "Fragile Resin": "약한 수지", "Transient Resin": "단기 수지",
    "Sanctifying Unction": "축복의 연고", "Sanctifying Essence": "축복의 정수",
    "Jueyun Chili Chicken": "절운고추 닭고기 무침", "Stir-Fried Fish Noodles": "생선 볶음면",
    "Sweet Madame": "달콤달콤 닭고기 스튜", "Northern Apple Stew": "북국의 사과 스튜"
}

MONTH_MAP = {
    "January": "1월", "February": "2월", "March": "3월", "April": "4월",
    "May": "5월", "June": "6월", "July": "7월", "August": "8월",
    "September": "9월", "October": "10월", "November": "11월", "December": "12월"
}

def convert_english_date_to_korean(date_str):
    match = re.search(r'([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})', date_str)
    if match:
        m_en, day, year = match.group(1), match.group(2), match.group(3)
        m_ko = MONTH_MAP.get(m_en, m_en)
        return f"{year}년 {m_ko} {day}일"
    return date_str

def translate_genshin_rewards(rewards_text):
    lines = [line.strip() for line in rewards_text.split('\n') if line.strip()]
    translated_items = []
    for line in lines:
        match = re.search(r'^(.*?)(?:\s*[×xX,]\s*(\d[\d,]*))?$', line)
        if match:
            item_name, amount = match.group(1).strip(), match.group(2)
            ko_name = GENSHIN_ITEM_MAP.get(item_name, item_name)
            translated_items.append(f"{ko_name} {amount}개" if amount else f"{ko_name}")
        else:
            translated_items.append(line)
    return ", ".join(translated_items) if translated_items else "원석 및 인게임 보상"

def process_genshin():
    print("=== [원신] 실시간 API 및 웹 크롤링 시작 ===")
    api_url = "https://genshin-impact.fandom.com/api.php?action=parse&page=Promotional_Code&format=json"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    active_coupons, expired_coupons, seen_codes = [], [], set()

    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            res_json = json.loads(resp.read().decode('utf-8'))
            html = res_json.get('parse', {}).get('text', {}).get('*', '')
            
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                tables = soup.find_all('table', class_=['article-table', 'wikitable'])
                for table in tables:
                    for row in table.find_all('tr'):
                        cols = row.find_all(['td', 'th'])
                        if len(cols) < 4: continue
                        
                        server_raw = cols[1].get_text(strip=True)
                        reward_raw = cols[2].get_text('\n', strip=True)
                        duration_raw = cols[3].get_text(' ', strip=True)
                        
                        if "China" in server_raw and "Asia" not in server_raw: continue
                        
                        code_texts = [c.get_text(strip=True) for c in cols[0].find_all(['code', 'a', 'b', 'span'])] or [cols[0].get_text(strip=True)]
                        for raw_code in code_texts:
                            code = re.sub(r'\[.*?\]', '', raw_code).strip().upper()
                            if not code or len(code) < 4 or code in ["CODE", "SERVER"] or code in seen_codes: continue
                            
                            rewards_ko = translate_genshin_rewards(reward_raw)
                            is_expired = "Expired" in duration_raw or "expired" in cols[3].get('class', [])
                            
                            if is_expired:
                                status = "EXPIRED"
                                exp_match = re.search(r'Expired:\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})', duration_raw, re.IGNORECASE)
                                expiry_note = f"{convert_english_date_to_korean(exp_match.group(1))} 만료됨" if exp_match else "사용 만료"
                            else:
                                status = "ACTIVE"
                                valid_match = re.search(r'Valid until:\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})', duration_raw, re.IGNORECASE)
                                if valid_match:
                                    expiry_note = f"{convert_english_date_to_korean(valid_match.group(1))}까지"
                                elif "indefinite" in duration_raw.lower():
                                    expiry_note = "상시 유효"
                                else:
                                    expiry_note = "유효"
                                    
                            coupon_obj = {"code": code, "rewards": rewards_ko, "status": status, "expiry_note": expiry_note, "updated_at": NOW_KST_STR}
                            (expired_coupons if status == "EXPIRED" else active_coupons).append(coupon_obj)
                            seen_codes.add(code)
    except Exception as e:
        print(f"[원신 수집 예외]: {e}")

    # 백업 기본 세트 보장
    known_genshin_defaults = [
        {"code": "GENSHINGIFT", "rewards": "원석 50개, 영웅의 경험 3개", "status": "ACTIVE", "expiry_note": "상시 유효", "updated_at": NOW_KST_STR},
        {"code": "EVERWINTER", "rewards": "원석 100개, 정제용 마법 광물 10개", "status": "ACTIVE", "expiry_note": "2026년 8월 3일까지", "updated_at": NOW_KST_STR},
        {"code": "ONTOSNEZHNAYA", "rewards": "원석 100개, 영웅의 경험 5개", "status": "ACTIVE", "expiry_note": "2026년 8월 3일까지", "updated_at": NOW_KST_STR},
        {"code": "ODETTE0812", "rewards": "원석 100개, 모라 50,000개", "status": "ACTIVE", "expiry_note": "2026년 8월 3일까지", "updated_at": NOW_KST_STR},
        {"code": "LEGEDILJKSGM", "rewards": "원석 60개, 모험가의 경험 5개", "status": "ACTIVE", "expiry_note": "2026년 9월 2일까지", "updated_at": NOW_KST_STR},
        {"code": "2BJ64QRZ7RT8", "rewards": "원석 60개, 모험가의 경험 5개", "status": "ACTIVE", "expiry_note": "유효", "updated_at": NOW_KST_STR},
        {"code": "UIVIBUQM6Q8A", "rewards": "모라 10,000개, 모험가의 경험 10개, 양질의 마법 광물 5개, 절운고추 닭고기 무침 5개, 생선 볶음면 5개", "status": "ACTIVE", "expiry_note": "유효", "updated_at": NOW_KST_STR},
        {"code": "UIVI13C8X156", "rewards": "모라 10,000개, 모험가의 경험 10개, 양질의 마법 광물 5개, 절운고추 닭고기 무침 5개, 생선 볶음면 5개", "status": "ACTIVE", "expiry_note": "유효", "updated_at": NOW_KST_STR}
    ]
    for fb in known_genshin_defaults:
        if fb["code"] not in seen_codes:
            active_coupons.append(fb)

    final_list = active_coupons + expired_coupons
    with open("genshin.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
    print(f"[genshin.json] 저장 완료! (총 {len(final_list)}개)")


# ==========================================
# 🦁 2. AFK 새로운 여정 용어 사전 & 동적 실시간 크롤러
# ==========================================
AFK_REWARD_MAP = {
    "Dragon Crystal": "용의 결정", "Diamond": "다이아", "Diamonds": "다이아",
    "Invite Letter": "전체 초대장", "Invite Letters": "전체 초대장",
    "Epic Invite Letter": "에픽 초대장", "Epic Invite Letters": "에픽 초대장",
    "Gold": "골드", "Hero Essence": "영웅의 정수", "Soulstone": "영혼석"
}

# 알려진 쿠폰 정보 사전 (검증된 한글 데이터)
KNOWN_AFK_MAP = {
    "JOURNEY2YRS": {"rewards": "에픽 초대장 10개, 전체 초대장 10개, 다이아 3,270개, 100,000 골드", "expiry": "2026년 9월 30일까지"},
    "ZC1JJ3UU0N": {"rewards": "다이아 1,000개, 에픽 초대장 5개, 20,000 골드", "expiry": "2026년 8월 말까지"},
    "4IYTSNBDXC": {"rewards": "다이아 1,000개, 전체 초대장 5개, 20,000 골드", "expiry": "2026년 8월 말까지"},
    "H7PDTYNR61": {"rewards": "다이아 1,000개, 에픽 초대장 5개, 20,000 골드", "expiry": "2026년 8월 말까지"},
    "HQC0ZFSC6QYTX": {"rewards": "다이아 500개, 종이접기 햄스터 5개, 50,000 골드", "expiry": "상시 유효"},
    "AFKJ10": {"rewards": "전체 초대장(일반 소환권) 10개", "expiry": "상시 유효"},
    "AFKJCOMMUNITY": {"rewards": "다이아 100개", "expiry": "상시 유효"},
    "PLAYAFKJOURNEY": {"rewards": "다이아 200개", "expiry": "상시 유효"},
    "AFKJRPG888": {"rewards": "다이아 300개", "expiry": "상시 유효"},
    "AFKJPC": {"rewards": "다이아 100개", "expiry": "상시 유효"},
    "AFKJ8888": {"rewards": "다이아 188개", "expiry": "상시 유효"},
    "AFKJ9999": {"rewards": "다이아 188개", "expiry": "상시 유효"}
}

KNOWN_EXPIRED_AFK = {"E8BESLBQZLZUD", "B52F8N5OPOG7K", "SMALLGIFTFROMPEGGY", "LILYOLENA", "AFKJFUYUYO", "AFKJNEWS2025"}

def translate_afk_reward(raw_text):
    """실시간으로 수집된 영문 보상 텍스트를 한글 아이템명으로 자동 번역"""
    translated = raw_text
    for en, ko in AFK_REWARD_MAP.items():
        translated = re.sub(r'\b' + en + r'\b', ko, translated, flags=re.IGNORECASE)
    translated = re.sub(r'(\d+)\s*([가-힣]+)', r'\2 \1개', translated)
    return translated if translated else "인게임 보상 (다이아 / 소환권 / 골드)"

def process_afk_journey():
    print("=== [AFK 새로운 여정] 실시간 탐색 및 크롤링 시작 ===")
    
    active_coupons, expired_coupons, seen_codes = [], [], set()
    
    # 1. 알려진 검증 쿠폰 먼저 기본 탑재
    for code, info in KNOWN_AFK_MAP.items():
        active_coupons.append({
            "code": code,
            "rewards": info["rewards"],
            "status": "ACTIVE",
            "expiry_note": info["expiry"],
            "updated_at": NOW_KST_STR
        })
        seen_codes.add(code)

    for code in KNOWN_EXPIRED_AFK:
        expired_coupons.append({
            "code": code,
            "rewards": "사용 완료/만료 보상",
            "status": "EXPIRED",
            "expiry_note": "사용 만료",
            "updated_at": NOW_KST_STR
        })
        seen_codes.add(code)

    # 2. 🌐 실시간 웹사이트 탐색 (새로 출시되는 신규 패치 코드 자동 감지 엔진)
    urls = [
        "https://buffhub.com/blog/afk-journey/",
        "https://afkjourney.fandom.com/wiki/Redemption_Codes"
    ]
    
    blacklist = {'WUTHERING', 'VALORANT', 'ARKNIGHTS', 'FORTNITE', 'BUSINESS', 'LANGUAGE', 'COPYRIGHT', 'PROMOTIONAL', 'REDEMPTION'}
    
    scraper = cloudscraper.create_scraper()
    for url in urls:
        try:
            resp = scraper.get(url, timeout=12)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                main_area = soup.find('article') or soup.find('main') or soup
                
                # 표(table) 또는 본문 텍스트 내 신규 코드 탐색
                for row in main_area.find_all(['tr', 'p', 'li']):
                    text = row.get_text(strip=True)
                    matches = re.findall(r'\b[A-Za-z0-9]{8,20}\b', text)
                    for code in matches:
                        code_upper = code.upper()
                        if code_upper in seen_codes or any(b in code_upper for b in blacklist):
                            continue
                            
                        # 🎉 새로운 패치/이벤트 코드가 감지됨!
                        parsed_reward = translate_afk_reward(text)
                        active_coupons.insert(0, {
                            "code": code_upper,
                            "rewards": parsed_reward,
                            "status": "ACTIVE",
                            "expiry_note": "신규 유효 코드",
                            "updated_at": NOW_KST_STR
                        })
                        seen_codes.add(code_upper)
                        print(f"✨ [AFK 신규 리딤코드 자동 감지!]: {code_upper}")
        except Exception as e:
            print(f"[AFK 웹 실시간 탐색 예외 - {url}]: {e}")

    final_list = active_coupons + expired_coupons
    with open("afk_journey.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
    print(f"[afk_journey.json] 저장 완료! (총 {len(final_list)}개)")

def main():
    process_afk_journey()
    process_genshin()

if __name__ == "__main__":
    main()
