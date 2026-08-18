"""密码哈希、会话令牌等安全工具。"""
import hashlib
import os
import secrets

# 使用标准库 PBKDF2 进行密码哈希，无需额外依赖
_PBKDF2_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    """生成密码哈希，返回格式：盐(hex)$摘要(hex)。"""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验密码是否与存储的哈希匹配。"""
    try:
        salt_hex, digest_hex = stored.split("$")
        salt = bytes.fromhex(salt_hex)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
        )
        return secrets.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def generate_token() -> str:
    """生成随机会话令牌。"""
    return secrets.token_urlsafe(48)