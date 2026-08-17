"""对外验证 API：POST /api/verify。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import add_log, client_ip, verify_limiter
from ..models import Card
from ..schemas import VerifyRequest, VerifyResponse
from ..utils import parse_user_agent

router = APIRouter(prefix="/api")


def _expires(card: Card) -> str:
    """卡密到期时间（ISO 格式字符串）。"""
    return card.expires_at.strftime("%Y-%m-%d %H:%M:%S") if card.expires_at else ""


def _check_rate_limit(request: Request) -> None:
    """每 IP 频率限制：超出则拒绝请求（防批量撞库 / 滥用）。"""
    if not verify_limiter.allow(client_ip(request)):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")


@router.post("/verify", response_model=VerifyResponse)
def verify_card(req: VerifyRequest, request: Request, db: Session = Depends(get_db)):
    """验证卡密有效性。

    规则：
      - 卡密不存在      -> valid=False, status=not_found
      - 卡密已过期      -> valid=False, status=expired
      - 卡密已被使用    -> valid=False, status=used
      - 卡密有效（未使用）-> 标记为已使用并返回 valid=True, status=unused

    验证通过时记录使用方的 IP、User-Agent 与设备信息。
    """
    code = req.code.strip().upper()
    _check_rate_limit(request)
    card = db.query(Card).filter(Card.code == code).first()
    if not card:
        add_log(db, None, "verify", f"验证失败：卡密不存在（{req.code}）", client_ip(request))
        return VerifyResponse(
            valid=False, code=req.code, status="not_found", message="卡密不存在"
        )

    type_name = card.card_type.name if card.card_type else ""
    if card.expires_at and card.expires_at < datetime.now():
        add_log(db, None, "verify", f"验证失败：卡密已过期（{card.code}）", client_ip(request))
        return VerifyResponse(
            valid=False, code=card.code, type_name=type_name,
            status="expired", message="卡密已过期", expires_at=_expires(card),
        )

    if card.status == "used":
        add_log(db, None, "verify", f"验证失败：卡密已被使用（{card.code}）", client_ip(request))
        return VerifyResponse(
            valid=False, code=card.code, type_name=type_name,
            status="used", message="卡密已被使用", expires_at=_expires(card),
        )

    # 记录使用方设备信息
    ua = request.headers.get("user-agent", "")
    card.status = "used"
    card.used_at = datetime.now()
    card.used_ip = client_ip(request)
    card.used_ua = ua[:300]
    card.used_device = parse_user_agent(ua)
    add_log(db, None, "verify", f"验证通过并激活卡密 {card.code}（设备：{card.used_device}）", client_ip(request))
    db.commit()
    return VerifyResponse(
        valid=True, code=card.code, type_name=type_name,
        status="unused", message="验证通过，卡密已激活",
        expires_at=_expires(card), device=card.used_device,
    )