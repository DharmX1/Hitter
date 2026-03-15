"""Unicode font conversion utilities for premium formatting"""

BOLD_MAP = {
    'A': '𝗔', 'B': '𝗕', 'C': '𝗖', 'D': '𝗗', 'E': '𝗘', 'F': '𝗙', 'G': '𝗚', 'H': '𝗛', 'I': '𝗜',
    'J': '𝗝', 'K': '𝗞', 'L': '𝗟', 'M': '𝗠', 'N': '𝗡', 'O': '𝗢', 'P': '𝗣', 'Q': '𝗤', 'R': '𝗥',
    'S': '𝗦', 'T': '𝗧', 'U': '𝗨', 'V': '𝗩', 'W': '𝗪', 'X': '𝗫', 'Y': '𝗬', 'Z': '𝗭',
    'a': '𝗮', 'b': '𝗯', 'c': '𝗰', 'd': '𝗱', 'e': '𝗲', 'f': '𝗳', 'g': '𝗴', 'h': '𝗵', 'i': '𝗶',
    'j': '𝗷', 'k': '𝗸', 'l': '𝗹', 'm': '𝗺', 'n': '𝗻', 'o': '𝗼', 'p': '𝗽', 'q': '𝗾', 'r': '𝗿',
    's': '𝘀', 't': '𝘁', 'u': '𝘂', 'v': '𝘃', 'w': '𝘄', 'x': '𝘅', 'y': '𝘆', 'z': '𝘇',
    '0': '𝟬', '1': '𝟭', '2': '𝟮', '3': '𝟯', '4': '𝟰', '5': '𝟱', '6': '𝟲', '7': '𝟳', '8': '𝟴', '9': '𝟵',
}

MONO_MAP = {
    'A': '𝙰', 'B': '𝙱', 'C': '𝙲', 'D': '𝙳', 'E': '𝙴', 'F': '𝙵', 'G': '𝙶', 'H': '𝙷', 'I': '𝙸',
    'J': '𝙹', 'K': '𝙺', 'L': '𝙻', 'M': '𝙼', 'N': '𝙽', 'O': '𝙾', 'P': '𝙿', 'Q': '𝚀', 'R': '𝚁',
    'S': '𝚂', 'T': '𝚃', 'U': '𝚄', 'V': '𝚅', 'W': '𝚆', 'X': '𝚇', 'Y': '𝚈', 'Z': '𝚉',
    'a': '𝚊', 'b': '𝚋', 'c': '𝚌', 'd': '𝚍', 'e': '𝚎', 'f': '𝚏', 'g': '𝚐', 'h': '𝚑', 'i': '𝚒',
    'j': '𝚓', 'k': '𝚔', 'l': '𝚕', 'm': '𝚖', 'n': '𝚗', 'o': '𝚘', 'p': '𝚙', 'q': '𝚚', 'r': '𝚛',
    's': '𝚜', 't': '𝚝', 'u': '𝚞', 'v': '𝚟', 'w': '𝚠', 'x': '𝚡', 'y': '𝚢', 'z': '𝚣',
    '0': '𝟶', '1': '𝟷', '2': '𝟸', '3': '𝟹', '4': '𝟺', '5': '𝟻', '6': '𝟼', '7': '𝟽', '8': '𝟾', '9': '𝟿',
}

def to_bold(text: str) -> str:
    """Convert text to bold Unicode font"""
    return ''.join(BOLD_MAP.get(c, c) for c in str(text))

def to_mono(text: str) -> str:
    """Convert text to monospace Unicode font"""
    return ''.join(MONO_MAP.get(c, c) for c in str(text).upper())

def fmt(label: str, value: str, emoji: str = "⌯") -> str:
    """Format a label-value pair with premium styling
    Example: [⌯] 𝗕𝗶𝗻 ⌁ 𝚅𝙸𝚂𝙰
    """
    return f"[{emoji}] {to_bold(label)} ⌁ {to_mono(value)}"

def header(text: str, emoji: str = "⚡") -> str:
    """Format a header with premium styling
    Example: ═══════ ⚡ 𝗦𝗧𝗥𝗜𝗣𝗘 𝗖𝗛𝗔𝗥𝗚𝗘 ⚡ ═══════
    """
    return f"═══════ {emoji} {to_bold(text.upper())} {emoji} ═══════"

def section(text: str) -> str:
    """Format a section header
    Example: ━━━ 💳 𝗖𝗔𝗥𝗗 𝗗𝗘𝗧𝗔𝗜𝗟𝗦 ━━━
    """
    return f"━━━ {to_bold(text.upper())} ━━━"

def divider() -> str:
    """Return a divider line"""
    return "═════════════════════════"

def fmt_code(label: str, value: str, emoji: str = "⌯") -> str:
    """Format a label-value pair with bold label and monospace code value (easy to copy)
    Example: [💳] 𝗖𝗮𝗿𝗱 ⌁ <code>5312590010995308|03|26|777</code>
    """
    return f"[{emoji}] {to_bold(label)} ⌁ <code>{value}</code>"
