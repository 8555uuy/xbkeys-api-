"""管理员后台：仪表盘、卡密管理、用户管理、卡密类型管理、操作日志、系统设置。"""
import csv
import io
from datetime import date, datetime, timedelta
from math import ceil
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import add_log, client_ip, get_current_user, get_setting, redirect_with, set_setting
from ..models import Card, CardType, OperationLog, User
from ..security import hash_password
from ..templating import render
from ..utils import generate_card_code

router = APIRouter(prefix="/admin")

# 后台列表页分页大小
PAGE_SIZE = 30


def _admin(request: Request, db: Session) -> bool:
    """判断当前登录用户是否为管理员。"""
    user = get_current_user(request, db)
    return bool(user and user.is_admin)


def _card_query(db: Session, params) -> object:
    """按筛选条件构建卡密查询（支持 user / type / status / q 过滤）。"""
    q = db.query(Card)
    uid = params.get("user")
    tid = params.get("type")
    status = params.get("status")
    keyword = params.get("q", "").strip()
    if uid and uid.isdigit():
        q = q.filter(Card.owner_id == int(uid))
    if tid and tid.isdigit():
        q = q.filter(Card.type_id == int(tid))
    if status in ("unused", "used"):
        q = q.filter(Card.status == status)
    if keyword:
        q = q.filter(Card.code.ilike(f"%{keyword.upper()}%"))
    return q


def _filter_query_string(request: Request, page: int = 0) -> str:
    """从当前请求中提取筛选参数，用于导出、分页链接。"""
    filters = {
        k: v for k, v in request.query_params.items()
        if k in ("user", "type", "status", "q") and v
    }
    if page:
        filters["page"] = page
    return "?" + urlencode(filters) if filters else ""


def _unique_code(db: Session) -> str:
    """生成数据库中不重复的卡密编码。"""
    while True:
        code = generate_card_code()
        if not db.query(Card).filter(Card.code == code).first():
            return code


def _resolve_expiry(expires_at: str, card_type: CardType) -> datetime:
    """计算卡密到期时间：优先使用管理员指定时间，否则按类型时长推算（0 天为永久）。"""
    raw = (expires_at or "").strip()
    if raw:
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None
    if card_type and card_type.duration_days:
        return datetime.now() + timedelta(days=card_type.duration_days)
    return None


def _trend(db: Session, days: int = 7) -> list:
    """近 N 天每日卡密生成量，用于仪表盘趋势图。"""
    rows = []
    today = date.today()
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        start = datetime.combine(d, datetime.min.time())
        end = start + timedelta(days=1)
        cnt = db.query(Card).filter(Card.generated_at >= start, Card.generated_at < end).count()
        rows.append({"label": d.strftime("%m-%d"), "count": cnt})
    return rows


# ---------- 仪表盘 ----------

@router.get("")
def dashboard(request: Request, db: Session = Depends(get_db)):
    """仪表盘：总用户、总卡密、今日新增、近 7 日趋势、活跃用户排行等。"""
    if not _admin(request, db):
        return redirect_with("/login", "需要管理员权限", "error")

    start = datetime.combine(date.today(), datetime.min.time())
    stats = {
        "total_users": db.query(User).count(),
        "total_cards": db.query(Card).count(),
        "today_users": db.query(User).filter(User.created_at >= start).count(),
        "today_cards": db.query(Card).filter(Card.generated_at >= start).count(),
        "unused": db.query(Card).filter(Card.status == "unused").count(),
        "used": db.query(Card).filter(Card.status == "used").count(),
    }
    trend = _trend(db)
    # 按卡密数量取前 5 名用户
    top_users = (
        db.query(User.id, User.username, func.count(Card.id).label("cnt"))
        .join(Card, Card.owner_id == User.id)
        .group_by(User.id)
        .order_by(func.count(Card.id).desc())
        .limit(5)
        .all()
    )
    recent = (
        db.query(Card).order_by(Card.generated_at.desc()).limit(10).all()
    )
    return render(
        request, "admin/dashboard.html", db,
        user=get_current_user(request, db),
        stats=stats, trend=trend, top_users=top_users, recent=recent,
    )


# ---------- 卡密管理 ----------

@router.get("/cards")
def cards_page(request: Request, db: Session = Depends(get_db)):
    """卡密列表：查看全部卡密、按用户/类型/状态/编码筛选、分页。"""
    if not _admin(request, db):
        return redirect_with("/login", "需要管理员权限", "error")

    q = _card_query(db, request.query_params)
    page = max(1, int(request.query_params.get("page", 1)))
    total = q.count()
    pages = ceil(total / PAGE_SIZE) if total else 1
    cards = (
        q.order_by(Card.generated_at.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .all()
    )
    users = db.query(User).order_by(User.id).all()
    types = db.query(CardType).order_by(CardType.name).all()
    filter_query = _filter_query_string(request)

    def page_url(p: int) -> str:
        params = {k: v for k, v in request.query_params.items() if k in ("user", "type", "status", "q") and v}
        params["page"] = p
        return "/admin/cards?" + urlencode(params)

    return render(
        request, "admin/cards.html", db,
        user=get_current_user(request, db),
        cards=cards, users=users, types=types,
        total=total, page=page, pages=pages,
        filter_query=filter_query,
        filter_user=request.query_params.get("user", ""),
        filter_type=request.query_params.get("type", ""),
        filter_status=request.query_params.get("status", ""),
        filter_q=request.query_params.get("q", ""),
        page_url=page_url,
        now=datetime.now(),
    )


@router.post("/cards/generate")
def admin_generate(
    request: Request,
    count: int = Form(1),
    type_id: int = Form(...),
    owner_id: int = Form(0),
    expires_at: str = Form(""),
    db: Session = Depends(get_db),
):
    """管理员手动 / 批量生成卡密（不受每日上限限制）。"""
    if not _admin(request, db):
        return redirect_with("/login", "需要管理员权限", "error")

    count = max(1, min(500, count))
    card_type = db.query(CardType).filter(CardType.id == type_id).first()
    if not card_type:
        return redirect_with("/admin/cards", "卡密类型不存在", "error")

    owner = None
    if owner_id:
        owner = db.query(User).filter(User.id == owner_id).first()

    expiry = _resolve_expiry(expires_at, card_type)
    codes = []
    created = 0
    while created < count:
        code = _unique_code(db)
        codes.append(code)
        db.add(Card(code=code, type_id=card_type.id, owner_id=owner.id if owner else None, expires_at=expiry))
        created += 1
    add_log(
        db, get_current_user(request, db), "generate",
        f"后台批量生成 {created} 个卡密（类型：{card_type.name}）", client_ip(request),
    )
    db.commit()
    return redirect_with("/admin/cards", f"成功生成 {created} 个卡密")


@router.post("/cards/delete")
def admin_delete_cards(
    request: Request,
    card_ids: list[int] = Form(...),
    db: Session = Depends(get_db),
):
    """批量删除卡密。"""
    if not _admin(request, db):
        return redirect_with("/login", "需要管理员权限", "error")
    if not card_ids:
        return redirect_with("/admin/cards", "未选择卡密", "error")
    deleted = db.query(Card).filter(Card.id.in_(card_ids)).delete(synchronize_session=False)
    add_log(db, get_current_user(request, db), "delete_card", f"后台删除 {deleted} 个卡密", client_ip(request))
    db.commit()
    return redirect_with("/admin/cards", f"已删除 {deleted} 个卡密")


@router.get("/cards/export")
def export_cards(request: Request, db: Session = Depends(get_db)):
    """导出卡密为 CSV（含 BOM，便于 Excel 直接打开）。"""
    if not _admin(request, db):
        return redirect_with("/login", "需要管理员权限", "error")

    q = _card_query(db, request.query_params).order_by(Card.generated_at.desc())
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ID", "卡密编码", "类型", "归属用户", "状态", "生成时间", "到期时间", "使用时间", "使用设备", "使用IP"])
    for c in q.all():
        writer.writerow([
            c.id,
            c.code,
            c.card_type.name if c.card_type else "",
            c.owner.username if c.owner else "",
            "已使用" if c.status == "used" else "未使用",
            c.generated_at.strftime("%Y-%m-%d %H:%M:%S"),
            c.expires_at.strftime("%Y-%m-%d %H:%M:%S") if c.expires_at else "",
            c.used_at.strftime("%Y-%m-%d %H:%M:%S") if c.used_at else "",
            c.used_device,
            c.used_ip,
        ])
    data = "\ufeff" + buf.getvalue()
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=cards.csv"},
    )


# ---------- 用户管理 ----------

@router.get("/users")
def users_page(request: Request, db: Session = Depends(get_db)):
    """用户列表：包含各自的卡密数量。"""
    if not _admin(request, db):
        return redirect_with("/login", "需要管理员权限", "error")
    users = db.query(User).order_by(User.id).all()
    counts = {
        u.id: db.query(Card).filter(Card.owner_id == u.id).count() for u in users
    }
    return render(request, "admin/users.html", db,
                  user=get_current_user(request, db), users=users, counts=counts)


@router.post("/users/toggle")
def toggle_user(
    request: Request,
    user_id: int = Form(...),
    db: Session = Depends(get_db),
):
    """启用 / 禁用用户。"""
    admin = get_current_user(request, db)
    if not admin or not admin.is_admin:
        return redirect_with("/login", "需要管理员权限", "error")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        return redirect_with("/admin/users", "用户不存在", "error")
    if target.id == admin.id:
        return redirect_with("/admin/users", "不能禁用自己", "error")
    target.is_active = not target.is_active
    add_log(db, admin, "toggle_user",
            f"{'禁用' if not target.is_active else '启用'}用户 {target.username}", client_ip(request))
    db.commit()
    return redirect_with("/admin/users",
                         f"用户 {target.username} 已{'启用' if target.is_active else '禁用'}")


@router.post("/users/reset-password")
def reset_password(
    request: Request,
    user_id: int = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db),
):
    """重置指定用户密码。"""
    admin = get_current_user(request, db)
    if not admin or not admin.is_admin:
        return redirect_with("/login", "需要管理员权限", "error")
    if len(new_password) < 6:
        return redirect_with("/admin/users", "新密码至少 6 位", "error")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        return redirect_with("/admin/users", "用户不存在", "error")
    target.password_hash = hash_password(new_password)
    add_log(db, admin, "reset_password", f"重置用户 {target.username} 的密码", client_ip(request))
    db.commit()
    return redirect_with("/admin/users", f"用户 {target.username} 密码已重置")


# ---------- 卡密类型管理 ----------

@router.get("/types")
def types_page(request: Request, db: Session = Depends(get_db)):
    """卡密类型列表。"""
    if not _admin(request, db):
        return redirect_with("/login", "需要管理员权限", "error")
    types = db.query(CardType).order_by(CardType.id).all()
    counts = {
        t.id: db.query(Card).filter(Card.type_id == t.id).count() for t in types
    }
    return render(request, "admin/types.html", db,
                  user=get_current_user(request, db), types=types, counts=counts)


@router.post("/types/save")
def save_type(
    request: Request,
    id: int = Form(0),
    name: str = Form(...),
    duration_days: int = Form(30),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    """新增或编辑卡密类型（id 为 0 表示新增）。"""
    if not _admin(request, db):
        return redirect_with("/login", "需要管理员权限", "error")

    name = name.strip().replace("'", "").replace('"', "")
    description = description.strip().replace("'", "").replace('"', "")
    if not name:
        return redirect_with("/admin/types", "类型名称不能为空", "error")
    if duration_days < 0:
        return redirect_with("/admin/types", "时长天数不能为负数（永久请填 0）", "error")

    admin = get_current_user(request, db)
    if id:
        t = db.query(CardType).filter(CardType.id == id).first()
        if not t:
            return redirect_with("/admin/types", "类型不存在", "error")
        if db.query(CardType).filter(CardType.name == name, CardType.id != id).first():
            return redirect_with("/admin/types", "类型名称已存在", "error")
        t.name, t.duration_days, t.description = name, duration_days, description
        add_log(db, admin, "save_type", f"编辑类型：{name}", client_ip(request))
    else:
        if db.query(CardType).filter(CardType.name == name).first():
            return redirect_with("/admin/types", "类型名称已存在", "error")
        db.add(CardType(name=name, duration_days=duration_days, description=description))
        add_log(db, admin, "save_type", f"新增类型：{name}（{duration_days} 天）", client_ip(request))
    db.commit()
    return redirect_with("/admin/types", "类型已保存")


@router.post("/types/delete")
def delete_type(
    request: Request,
    id: int = Form(...),
    db: Session = Depends(get_db),
):
    """删除卡密类型（该类型下存在卡密时不允许删除）。"""
    if not _admin(request, db):
        return redirect_with("/login", "需要管理员权限", "error")
    t = db.query(CardType).filter(CardType.id == id).first()
    if not t:
        return redirect_with("/admin/types", "类型不存在", "error")
    cnt = db.query(Card).filter(Card.type_id == id).count()
    if cnt:
        return redirect_with("/admin/types", f"该类型下已有 {cnt} 个卡密，无法删除", "error")
    db.delete(t)
    add_log(db, get_current_user(request, db), "delete_type", f"删除类型：{t.name}", client_ip(request))
    db.commit()
    return redirect_with("/admin/types", "类型已删除")


# ---------- 操作日志 ----------

@router.get("/logs")
def logs_page(request: Request, db: Session = Depends(get_db)):
    """操作日志：按操作类型 / 用户名筛选、分页查看。"""
    if not _admin(request, db):
        return redirect_with("/login", "需要管理员权限", "error")

    q = db.query(OperationLog)
    action = request.query_params.get("action", "")
    username = request.query_params.get("username", "").strip()
    if action:
        q = q.filter(OperationLog.action == action)
    if username:
        q = q.filter(OperationLog.username.ilike(f"%{username}%"))

    page = max(1, int(request.query_params.get("page", 1)))
    total = q.count()
    pages = ceil(total / PAGE_SIZE) if total else 1
    logs = (
        q.order_by(OperationLog.created_at.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .all()
    )
    actions = [r[0] for r in db.query(OperationLog.action).distinct().order_by(OperationLog.action).all()]

    def page_url(p: int) -> str:
        params = {}
        if action:
            params["action"] = action
        if username:
            params["username"] = username
        params["page"] = p
        return "/admin/logs?" + urlencode(params)

    return render(
        request, "admin/logs.html", db,
        user=get_current_user(request, db),
        logs=logs, actions=actions,
        total=total, page=page, pages=pages,
        filter_action=action, filter_username=username,
        page_url=page_url,
    )


# ---------- 系统设置 ----------

@router.get("/settings")
def settings_page(request: Request, db: Session = Depends(get_db)):
    """系统设置页面。"""
    if not _admin(request, db):
        return redirect_with("/login", "需要管理员权限", "error")
    return render(
        request, "admin/settings.html", db,
        user=get_current_user(request, db),
        site_name=get_setting(db, "site_name", settings.SITE_NAME),
        daily_limit=get_setting(db, "daily_limit", str(settings.DEFAULT_DAILY_LIMIT)),
    )


@router.post("/settings/save")
def save_settings(
    request: Request,
    site_name: str = Form(...),
    daily_limit: int = Form(50),
    db: Session = Depends(get_db),
):
    """保存系统设置。"""
    if not _admin(request, db):
        return redirect_with("/login", "需要管理员权限", "error")
    site_name = site_name.strip() or settings.SITE_NAME
    daily_limit = max(1, daily_limit)
    set_setting(db, "site_name", site_name)
    set_setting(db, "daily_limit", str(daily_limit))
    add_log(db, get_current_user(request, db), "save_settings",
            f"保存系统设置（站点：{site_name}，每日上限：{daily_limit}）", client_ip(request))
    return redirect_with("/admin/settings", "系统设置已保存")