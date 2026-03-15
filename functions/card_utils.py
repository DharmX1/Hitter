import re

CARD_PATTERN = re.compile(
    r'(\d{15,19})\s*[|:/\\\-\s]\s*(\d{1,2})\s*[|:/\\\-\s]\s*(\d{2,4})\s*[|:/\\\-\s]\s*(\d{3,4})'
)

def parse_card(text: str) -> dict:
    """Parse a single card from text in format cc|mm|yy|cvv"""
    text = text.strip()
    if not text:
        return None
    
    parts = re.split(r'[|:/\\\-\s]+', text)
    if len(parts) < 4:
        match = CARD_PATTERN.search(text)
        if match:
            cc, mm, yy, cvv = match.groups()
        else:
            return None
    else:
        cc = re.sub(r'\D', '', parts[0])
        mm = parts[1].strip()
        yy = parts[2].strip()
        cvv = re.sub(r'\D', '', parts[3])
    
    if not (15 <= len(cc) <= 19):
        return None
    
    if len(mm) == 1:
        mm = f"0{mm}"
    if not (len(mm) == 2 and mm.isdigit() and 1 <= int(mm) <= 12):
        return None
    
    if len(yy) == 4:
        yy = yy[2:]
    if len(yy) != 2:
        return None
    
    if not (3 <= len(cvv) <= 4):
        return None
    
    return {"cc": cc, "month": mm, "year": yy, "cvv": cvv}

def parse_cards(text: str) -> list:
    """Parse multiple cards from text, one per line"""
    cards = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if line:
            card = parse_card(line)
            if card:
                cards.append(card)
    return cards

def format_card(card: dict) -> str:
    """Format card dict back to string"""
    return f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}"
