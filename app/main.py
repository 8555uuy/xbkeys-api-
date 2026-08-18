"""xb密钥系统入口。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR, settings
from .database import Base, SessionLocal, engine
from .models import User
from .router import admin, api, public
from .security import hash_password


def _init_admin() -> None:
    """首次启动时自动创建默认管理员账号（凭据来自 config.py）。"""
    db = SessionLocal()
    try:
        exists = db.query(User).filter(User.username == settings.ADMIN_USERNAME).first()
        if not exists:
            db.add(User(
                username=settings.ADMIN_USERNAME,
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                is_admin=True,
                is_active=True,
            ))
            db.commit()
            print(f"[初始化] 已创建默认管理员账号：{settings.ADMIN_USERNAME}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表并初始化默认管理员。"""
    Base.metadata.create_all(bind=engine)
    _init_admin()
    yield


app = FastAPI(title=settings.SITE_NAME, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

# 静态资源
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

# 业务路由
app.include_router(public.router)
app.include_router(admin.router)
app.include_router(api.router)