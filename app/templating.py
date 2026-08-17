"""模板渲染封装：统一注入站点名称、提示消息等公共变量。"""
from datetime import datetime

from fastapi.templating import Jinja2Templates

from .config import BASE_DIR, settings
from .deps import get_setting

# 模板目录
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# 模板全局变量
templates.env.globals["current_year"] = datetime.now().year


def render(request, name: str, db, **context):
    """渲染页面模板。

    自动注入：
      - site_name 站点名称（从系统设置读取）
      - msg / msg_type 提示消息（从 URL 参数读取）
    """
    ctx = {
        "request": request,
        "site_name": get_setting(db, "site_name", settings.SITE_NAME),
        "msg": request.query_params.get("msg"),
        "msg_type": request.query_params.get("type", "success"),
    }
    ctx.update(context)
    return templates.TemplateResponse(request, name, ctx)