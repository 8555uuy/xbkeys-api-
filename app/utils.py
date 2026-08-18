"""卡密编码生成工具。"""
import secrets

from .config import settings

# 去掉容易混淆的字符（如 0/O、1/I）
CARD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_card_code() -> str:
    """生成唯一卡密编码，格式如：KMS-XXXX-XXXX-XXXX-XXXX。"""
    segments = []
    for _ in range(settings.CARD_SEGMENTS):
        seg = "".join(secrets.choice(CARD_ALPHABET) for _ in range(settings.CARD_SEG_LENGTH))
        segments.append(seg)
    return "-".join([settings.CARD_PREFIX, *segments])


def parse_user_agent(ua: str) -> str:
    """从 User-Agent 解析简短的设备信息：操作系统 · 浏览器 · 端型。"""
    ua = ua or ""
    os_name = "未知系统"
    if "Windows" in ua:
        os_name = "Windows"
    elif "iPhone" in ua:
        os_name = "iOS"
    elif "iPad" in ua:
        os_name = "iPadOS"
    elif "Android" in ua:
        os_name = "Android"
    elif "Mac OS" in ua:
        os_name = "macOS"
    elif "Linux" in ua:
        os_name = "Linux"

    browser = "未知浏览器"
    if "Edg/" in ua:
        browser = "Edge"
    elif "Firefox/" in ua:
        browser = "Firefox"
    elif "Chrome/" in ua:
        browser = "Chrome"
    elif "Safari/" in ua:
        browser = "Safari"
    elif "OPR/" in ua or "Opera" in ua:
        browser = "Opera"

    device = "桌面端"
    if "Mobile" in ua or "iPhone" in ua:
        device = "移动端"
    elif "iPad" in ua or "Tablet" in ua:
        device = "平板"

    return f"{os_name} · {browser} · {device}"