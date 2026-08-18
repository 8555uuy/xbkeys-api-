"""普通用户相关页面与接口：首页、注册、登录、退出、生成卡密、我的卡密、个人中心、使用教程、API 文档。"""
from datetime import date, datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import add_log, auth_limiter, client_ip, get_current_user, get_setting, redirect_with
from ..models import Card, CardType, LoginSession, OperationLog, User
from ..security import generate_token, hash_password, verify_password
from ..templating import render
from ..utils import generate_card_code

router = APIRouter()

# 用户自定义类型的默认时长（天）
CUSTOM_TYPE_DAYS = 30


def _daily_limit(db: Session) -> int:
    """读取每日生成上限设置。"""
    try:
        return int(get_setting(db, "daily_limit", str(settings.DEFAULT_DAILY_LIMIT)))
    except ValueError:
        return settings.DEFAULT_DAILY_LIMIT


def _today_count(db: Session, user_id: int) -> int:
    """统计某用户今日已生成的卡密数量。"""
    start = datetime.combine(date.today(), datetime.min.time())
    return (
        db.query(Card)
        .filter(Card.owner_id == user_id, Card.generated_at >= start)
        .count()
    )


def _unique_code(db: Session) -> str:
    """生成数据库中不重复的卡密编码。"""
    while True:
        code = generate_card_code()
        if not db.query(Card).filter(Card.code == code).first():
            return code


def _resolve_expiry(expires_at: str, card_type: CardType) -> datetime:
    """计算卡密到期时间：优先使用用户指定时间，否则按类型时长推算（0 天为永久）。"""
    raw = (expires_at or "").strip()
    if raw:
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None
    if card_type and card_type.duration_days:
        return datetime.now() + timedelta(days=card_type.duration_days)
    return None


def _login_user(db: Session, user: User, msg: str, commit: bool = True) -> RedirectResponse:
    """创建会话并写入登录 Cookie（commit=False 时由调用方统一提交，减少 DB 往返）。"""
    token = generate_token()
    db.add(
        LoginSession(
            token=token,
            user_id=user.id,
            expires_at=datetime.now() + timedelta(days=settings.SESSION_EXPIRE_DAYS),
        )
    )
    if commit:
        db.commit()
    resp = RedirectResponse(url=f"/?msg={quote(msg)}", status_code=303)
    resp.set_cookie(
        "session_token",
        token,
        httponly=True,
        max_age=settings.SESSION_EXPIRE_DAYS * 86400,
        samesite="lax",
    )
    return resp


@router.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    """首页：已登录用户展示生成卡密功能，未登录用户展示宣传页。"""
    user = get_current_user(request, db)
    types = db.query(CardType).order_by(CardType.name).all()
    today_count = _today_count(db, user.id) if user else 0
    recent, stats = [], {}
    if user:
        recent = (
            db.query(Card)
            .filter(Card.owner_id == user.id)
            .order_by(Card.generated_at.desc())
            .limit(8)
            .all()
        )
        base = db.query(Card).filter(Card.owner_id == user.id)
        stats = {
            "total": base.count(),
            "unused": base.filter(Card.status == "unused").count(),
            "used": base.filter(Card.status == "used").count(),
            "today": today_count,
        }
    return render(
        request, "index.html", db,
        user=user, types=types,
        daily_limit=_daily_limit(db), today_count=today_count,
        recent=recent, stats=stats,
    )


# ---------- 注册 ----------

@router.get("/register")
def register_page(request: Request, db: Session = Depends(get_db)):
    """注册页面。"""
    if get_current_user(request, db):
        return RedirectResponse("/", status_code=303)
    return render(request, "register.html", db, user=None)


@router.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    """处理注册，成功后自动登录。"""
    if not auth_limiter.allow(client_ip(request)):
        return redirect_with("/register", "尝试过于频繁，请稍后再试", "error")
    username = username.strip()
    if len(username) < 3 or len(username) > 20:
        return redirect_with("/register", "用户名长度需在 3-20 个字符之间", "error")
    if len(password) < 6:
        return redirect_with("/register", "密码长度至少 6 位", "error")
    if password != confirm:
        return redirect_with("/register", "两次输入的密码不一致", "error")
    if db.query(User).filter(User.username == username).first():
        return redirect_with("/register", "用户名已存在", "error")

    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    add_log(db, user, "register", "注册账号", client_ip(request), commit=False)
    # 用户与日志合并一次提交，随后创建会话一并提交，减少远程 DB 往返
    db.commit()
    return _login_user(db, user, "注册成功，已自动登录")


# ---------- 登录 / 退出 ----------

@router.get("/login")
def login_page(request: Request, db: Session = Depends(get_db)):
    """登录页面。"""
    if get_current_user(request, db):
        return RedirectResponse("/", status_code=303)
    return render(request, "login.html", db, user=None)


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """处理登录。"""
    if not auth_limiter.allow(client_ip(request)):
        return redirect_with("/login", "尝试过于频繁，请稍后再试", "error")
    user = db.query(User).filter(User.username == username.strip()).first()
    if not user or not verify_password(password, user.password_hash):
        return redirect_with("/login", "用户名或密码错误", "error")
    if not user.is_active:
        return redirect_with("/login", "账号已被禁用，请联系管理员", "error")
    add_log(db, user, "login", "用户登录", client_ip(request), commit=False)
    return _login_user(db, user, "登录成功")


@router.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    """退出登录：删除会话并清除 Cookie。"""
    user = get_current_user(request, db)
    if user:
        add_log(db, user, "logout", "退出登录", client_ip(request))
    token = request.cookies.get("session_token")
    if token:
        db.query(LoginSession).filter(LoginSession.token == token).delete()
        db.commit()
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("session_token")
    return resp


# ---------- 生成卡密 ----------

@router.post("/generate")
def generate(
    request: Request,
    type_id: int = Form(0),
    custom_type: str = Form(""),
    expires_at: str = Form(""),
    db: Session = Depends(get_db),
):
    """为当前用户生成一个卡密。

    支持两种方式：
      - 选择已有类型（type_id）
      - 自定义类型（custom_type，不存在时自动创建）
    到期时间：可指定 expires_at（datetime-local），留空则按类型时长推算。
    """
    user = get_current_user(request, db)
    if not user:
        return redirect_with("/login", "请先登录", "error")

    card_type = None
    name = custom_type.strip()
    if name:
        # 自定义类型：不存在则自动创建
        card_type = db.query(CardType).filter(CardType.name == name).first()
        if not card_type:
            card_type = CardType(name=name, duration_days=CUSTOM_TYPE_DAYS, description="用户自定义类型")
            db.add(card_type)
            db.flush()
    elif type_id:
        card_type = db.query(CardType).filter(CardType.id == type_id).first()
    if not card_type:
        return redirect_with("/", "请选择或输入卡密类型", "error")

    # 每日上限仅对普通用户生效，管理员不受限制
    if not user.is_admin:
        limit = _daily_limit(db)
        if _today_count(db, user.id) >= limit:
            return redirect_with("/", "已达到今日生成上限，请明天再来", "error")

    code = _unique_code(db)
    expiry = _resolve_expiry(expires_at, card_type)
    db.add(Card(code=code, type_id=card_type.id, owner_id=user.id, expires_at=expiry))
    add_log(db, user, "generate", f"生成卡密 {code}（类型：{card_type.name}）", client_ip(request))
    db.commit()
    return redirect_with("/my-cards", f"卡密生成成功：{code}")


# ---------- 我的卡密 ----------

@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    """用户专属仪表盘：个人卡密统计、近 7 日生成趋势、最近卡密与操作记录。"""
    user = get_current_user(request, db)
    if not user:
        return redirect_with("/login", "请先登录", "error")

    base = db.query(Card).filter(Card.owner_id == user.id)
    now = datetime.now()
    start = datetime.combine(date.today(), datetime.min.time())
    stats = {
        "total": base.count(),
        "unused": base.filter(Card.status == "unused").count(),
        "used": base.filter(Card.status == "used").count(),
        "disabled": base.filter(Card.status == "disabled").count(),
        "expiring_soon": base.filter(
            Card.status == "unused", Card.expires_at.isnot(None),
            Card.expires_at > now, Card.expires_at <= now + timedelta(days=3),
        ).count(),
        "today": base.filter(Card.generated_at >= start).count(),
        "daily_limit": _daily_limit(db),
    }

    # 近 7 日个人生成趋势
    trend = []
    for i in range(6, -1, -1):
        d = date.today() - timedelta(days=i)
        s = datetime.combine(d, datetime.min.time())
        e = s + timedelta(days=1)
        cnt = db.query(Card).filter(Card.owner_id == user.id, Card.generated_at >= s, Card.generated_at < e).count()
        trend.append({"label": d.strftime("%m-%d"), "count": cnt})

    recent = base.order_by(Card.generated_at.desc()).limit(8).all()
    last_logs = (
        db.query(OperationLog)
        .filter(OperationLog.user_id == user.id)
        .order_by(OperationLog.created_at.desc())
        .limit(8)
        .all()
    )
    return render(
        request, "dashboard.html", db, user=user,
        stats=stats, trend=trend, recent=recent, last_logs=last_logs, now=now,
    )


@router.get("/my-cards")
def my_cards(request: Request, db: Session = Depends(get_db)):
    """我的卡密列表：支持按状态筛选、按编码搜索。"""
    user = get_current_user(request, db)
    if not user:
        return redirect_with("/login", "请先登录", "error")

    q = db.query(Card).filter(Card.owner_id == user.id)
    status = request.query_params.get("status", "")
    keyword = request.query_params.get("q", "").strip()
    if status in ("unused", "used", "disabled"):
        q = q.filter(Card.status == status)
    if keyword:
        q = q.filter(Card.code.ilike(f"%{keyword.upper()}%"))
    cards = q.order_by(Card.generated_at.desc()).all()

    base = db.query(Card).filter(Card.owner_id == user.id)
    stats = {
        "total": base.count(),
        "unused": base.filter(Card.status == "unused").count(),
        "used": base.filter(Card.status == "used").count(),
    }
    return render(
        request, "my_cards.html", db, user=user, cards=cards, stats=stats,
        filter_status=status, filter_q=keyword,
    )


@router.post("/my-cards/unbind")
def my_unbind(request: Request, card_id: int = Form(...), db: Session = Depends(get_db)):
    """解绑我的卡密：将已使用卡密恢复为未使用并清除设备信息。"""
    user = get_current_user(request, db)
    if not user:
        return redirect_with("/login", "请先登录", "error")
    card = db.query(Card).filter(Card.id == card_id, Card.owner_id == user.id).first()
    if not card:
        return redirect_with("/my-cards", "卡密不存在", "error")
    if card.status != "used":
        return redirect_with("/my-cards", "仅已使用的卡密可解绑", "error")
    card.status = "unused"
    card.used_at = None
    card.used_ip = ""
    card.used_ua = ""
    card.used_device = ""
    add_log(db, user, "unbind", f"解绑卡密 {card.code}", client_ip(request))
    db.commit()
    return redirect_with("/my-cards", f"卡密 {card.code} 已解绑，可重新使用")


@router.post("/my-cards/delete")
def my_delete_card(request: Request, card_id: int = Form(...), db: Session = Depends(get_db)):
    """删除我的卡密（仅未使用的卡密可删除）。"""
    user = get_current_user(request, db)
    if not user:
        return redirect_with("/login", "请先登录", "error")
    card = db.query(Card).filter(Card.id == card_id, Card.owner_id == user.id).first()
    if not card:
        return redirect_with("/my-cards", "卡密不存在", "error")
    if card.status == "used":
        return redirect_with("/my-cards", "已使用的卡密不可删除，请先解绑", "error")
    add_log(db, user, "delete_card", f"删除卡密 {card.code}", client_ip(request))
    db.delete(card)
    db.commit()
    return redirect_with("/my-cards", f"卡密 {card.code} 已删除")


@router.post("/my-cards/disable")
def my_disable_card(request: Request, card_id: int = Form(...), db: Session = Depends(get_db)):
    """停用 / 启用我的卡密（停用后该卡密无法通过验证）。"""
    user = get_current_user(request, db)
    if not user:
        return redirect_with("/login", "请先登录", "error")
    card = db.query(Card).filter(Card.id == card_id, Card.owner_id == user.id).first()
    if not card:
        return redirect_with("/my-cards", "卡密不存在", "error")
    if card.status == "used":
        return redirect_with("/my-cards", "已使用的卡密不可停用，请先解绑", "error")
    card.status = "unused" if card.status == "disabled" else "disabled"
    add_log(db, user, "toggle_card", f"{'启用' if card.status == 'unused' else '停用'}卡密 {card.code}", client_ip(request))
    db.commit()
    return redirect_with("/my-cards", f"卡密 {card.code} 已{'启用' if card.status == 'unused' else '停用'}")


# ---------- 个人中心 ----------

@router.get("/account")
def account_page(request: Request, db: Session = Depends(get_db)):
    """个人中心：展示账号信息，支持修改密码。"""
    user = get_current_user(request, db)
    if not user:
        return redirect_with("/login", "请先登录", "error")
    card_count = db.query(Card).filter(Card.owner_id == user.id).count()
    last_logs = (
        db.query(OperationLog)
        .filter(OperationLog.user_id == user.id)
        .order_by(OperationLog.created_at.desc())
        .limit(10)
        .all()
    )
    return render(request, "account.html", db, user=user, card_count=card_count, last_logs=last_logs)


@router.post("/account/change-password")
def change_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    """修改当前用户密码。"""
    user = get_current_user(request, db)
    if not user:
        return redirect_with("/login", "请先登录", "error")
    if not verify_password(old_password, user.password_hash):
        return redirect_with("/account", "原密码错误", "error")
    if len(new_password) < 6:
        return redirect_with("/account", "新密码至少 6 位", "error")
    if new_password != confirm:
        return redirect_with("/account", "两次输入的新密码不一致", "error")
    user.password_hash = hash_password(new_password)
    add_log(db, user, "change_password", "修改登录密码", client_ip(request))
    db.commit()
    return redirect_with("/account", "密码修改成功，请牢记新密码")


# ---------- 使用教程 / API 文档 ----------

@router.get("/guide")
def guide(request: Request, db: Session = Depends(get_db)):
    """使用教程页面。"""
    user = get_current_user(request, db)
    return render(request, "guide.html", db, user=user)


@router.get("/api-docs")
def api_docs(request: Request, db: Session = Depends(get_db)):
    """API 文档页面。"""
    user = get_current_user(request, db)
    return render(request, "api_docs.html", db, user=user)