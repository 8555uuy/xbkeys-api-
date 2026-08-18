"""数据库模型定义。"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    """用户表。"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True, comment="用户名")
    password_hash = Column(String(200), nullable=False, comment="密码哈希")
    is_admin = Column(Boolean, default=False, comment="是否管理员")
    is_active = Column(Boolean, default=True, comment="是否启用（禁用后无法登录）")
    created_at = Column(DateTime, default=datetime.now, comment="注册时间")

    cards = relationship("Card", back_populates="owner")


class CardType(Base):
    """卡密类型表（月卡 / 季卡 / 年卡 / 永久 等，由管理员维护）。"""
    __tablename__ = "card_types"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False, comment="类型名称")
    duration_days = Column(Integer, default=30, comment="有效期天数（0 表示永久）")
    description = Column(String(200), default="", comment="说明")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    cards = relationship("Card", back_populates="card_type")


class Card(Base):
    """卡密表。"""
    __tablename__ = "cards"

    id = Column(Integer, primary_key=True)
    code = Column(String(64), unique=True, nullable=False, index=True, comment="卡密编码")
    type_id = Column(Integer, ForeignKey("card_types.id"), comment="卡密类型")
    owner_id = Column(Integer, ForeignKey("users.id"), comment="归属用户（管理员生成时可为空）")
    status = Column(String(20), default="unused", comment="状态：unused 未使用 / used 已使用")
    generated_at = Column(DateTime, default=datetime.now, comment="生成时间")
    expires_at = Column(DateTime, nullable=True, comment="到期时间（为空表示永久有效）")
    used_at = Column(DateTime, nullable=True, comment="使用时间")
    used_ip = Column(String(50), default="", comment="使用方IP")
    used_ua = Column(String(300), default="", comment="使用方User-Agent")
    used_device = Column(String(100), default="", comment="使用方设备信息（系统/浏览器/端型）")

    owner = relationship("User", back_populates="cards")
    card_type = relationship("CardType", back_populates="cards")


class Setting(Base):
    """系统设置表（键值对）。"""
    __tablename__ = "settings"

    key = Column(String(50), primary_key=True)
    value = Column(String(200), default="")


class LoginSession(Base):
    """登录会话表。"""
    __tablename__ = "sessions"

    token = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, nullable=False)


class OperationLog(Base):
    """操作日志表（登录、注册、生成、验证、后台操作等）。"""
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True, comment="操作用户ID（未登录可为空）")
    username = Column(String(50), default="", comment="操作用户名")
    action = Column(String(50), index=True, comment="操作类型")
    detail = Column(String(300), default="", comment="操作详情")
    ip = Column(String(50), default="", comment="客户端IP")
    created_at = Column(DateTime, default=datetime.now, index=True, comment="操作时间")