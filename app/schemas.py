"""Pydantic 数据模型（API 请求 / 响应）。"""
from pydantic import BaseModel


class VerifyRequest(BaseModel):
    """POST /api/verify 请求体。"""
    code: str


class VerifyResponse(BaseModel):
    """POST /api/verify 响应体。"""
    valid: bool = False                    # 是否验证通过
    code: str = ""                         # 卡密编码
    type_name: str = ""                    # 卡密类型名称
    status: str = ""                       # not_found 不存在 / used 已被使用 / expired 已过期 / unused 未使用（本次已激活）
    message: str = ""                      # 提示信息
    expires_at: str = ""                   # 到期时间（ISO 格式，永久为空）
    device: str = ""                       # 使用方设备信息（系统/浏览器/端型）