"""共享依赖与辅助函数。"""
import threading
import time
from collections import defaultdict
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode

from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .config import settings
from .models import LoginSession, OperationLog, Setting, User


def client_ip(request) -> str:
    """获取客户端 IP 地址。"""
    return request.client.host if request.client else ""


class RateLimiter:
    """进程内滑动窗口限流器：统计每个 key 在时间窗口内的请求次数，超出返回是否放行。

    说明：内存实现，适用于单进程部署；若部署为多副本/Serverless，
    建议改用 Redis 等共享存储（生产可平滑替换）。
    """

    def __init__(self, limit: int, window: int):
        self.limit = limit
        self.window = window
        self._hits: dict = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """返回 True 表示放行，False 表示超出限流。"""
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            bucket[:] = [t for t in bucket if now - t < self.window]
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True

    def reset(self, key: str) -> None:
        """清除某个 key 的计数（可选）。"""
        with self._lock:
            self._hits.pop(key, None)


# 预置限流器
verify_limiter = RateLimiter(settings.VERIFY_RATE_LIMIT, settings.RATE_LIMIT_WINDOW)
auth_limiter = RateLimiter(settings.AUTH_RATE_LIMIT, settings.RATE_LIMIT_WINDOW)


def add_log(db: Session, user, action: str, detail: str = "", ip: str = "", commit: bool = True) -> None:
    """记录一条操作日志，默认立即提交（可传 commit=False 批量提交以减少 DB 往返）。"""
    db.add(OperationLog(
        user_id=user.id if user else None,
        username=user.username if user else "",
        action=action,
        detail=detail[:300],
        ip=ip,
    ))
    if commit:
        db.commit()


def get_current_user(request, db: Session) -> Optional[User]:
    """根据 Cookie 中的会话令牌获取当前登录用户，未登录返回 None。"""
    token = request.cookies.get("session_token")
    if not token:
        return None
    sess = db.query(LoginSession).filter(LoginSession.token == token).first()
    if not sess or sess.expires_at < datetime.now():
        return None
    user = db.query(User).filter(User.id == sess.user_id).first()
    if not user or not user.is_active:
        return None
    return user


def get_setting(db: Session, key: str, default: str = "") -> str:
    """读取系统设置项。"""
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row else default


def set_setting(db: Session, key: str, value: str) -> None:
    """写入系统设置项。"""
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()


def redirect_with(url: str, msg: str = "", msg_type: str = "success") -> RedirectResponse:
    """带提示消息的重定向响应（消息通过 URL 参数传递并在页面显示）。"""
    query = urlencode({"msg": msg, "type": msg_type})
    sep = "&" if "?" in url else "?"
    return RedirectResponse(url=f"{url}{sep}{query}", status_code=303)