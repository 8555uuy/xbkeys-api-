"""集中配置管理：所有可调整的配置项集中在这里，方便统一维护。"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 加载根目录下的 .env 文件（生产环境由 Vercel/Supabase 直接注入环境变量）
load_dotenv(BASE_DIR / ".env")


class Settings:
    """系统配置。"""

    # ---------- 数据库 ----------
    # 数据库连接串：默认本地 SQLite（开发用），生产环境通过环境变量 DATABASE_URL 指向 Supabase
    DB_DIR = BASE_DIR / "data"                      # 本地 SQLite 文件目录
    DB_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_DIR / 'card_system.db'}")

    # ---------- 站点 ----------
    SITE_NAME = "xb密钥系统"                           # 站点名称（可在后台修改，此为默认值）
    DEFAULT_DAILY_LIMIT = 50                         # 默认每日生成卡密上限

    # ---------- 会话安全 ----------
    SECRET_KEY = os.getenv("SECRET_KEY", "请在生产环境修改为随机字符串")  # 签名密钥
    SESSION_EXPIRE_DAYS = 7                           # 登录会话有效期（天）

    # ---------- 防攻击：接口频率限制 ----------
    # 单位时间窗口（秒）内，同一 IP 对敏感接口允许的最大请求次数；超出返回 429
    RATE_LIMIT_WINDOW = 60                            # 时间窗口（秒）
    VERIFY_RATE_LIMIT = 20                            # /api/verify 每窗口每 IP 上限
    AUTH_RATE_LIMIT = 10                              # 登录/注册 每窗口每 IP 上限

    # ---------- 默认管理员（首次启动自动创建）----------
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

    # ---------- 卡密编码规则 ----------
    CARD_PREFIX = "KMS"                              # 卡密前缀
    CARD_SEGMENTS = 4                                # 分段数（不含前缀）
    CARD_SEG_LENGTH = 4                              # 每段字符数

    # ---------- 服务 ----------
    HOST = "0.0.0.0"
    PORT = 8000


settings = Settings()
