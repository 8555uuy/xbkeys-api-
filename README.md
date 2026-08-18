# xb密钥系统

基于 **Python + FastAPI + SQLite + Bootstrap** 的卡密（激活码）自助生成与管理平台。

## 功能

### 普通用户
- 注册 / 登录 / 退出
- 首页一键生成卡密（选择类型，受每日上限限制）
- 我的卡密：查看编码、类型、状态（未使用/已使用）、生成时间
- 一键复制卡密编码

### 管理员后台
- 仪表盘：总用户、总卡密、今日新增、未使用/已使用统计
- 卡密管理：查看全部、按用户/类型/状态筛选、手动/批量生成、删除、导出 CSV
- 用户管理：用户列表、启用/禁用、重置密码
- 卡密类型管理：添加/编辑/删除（月卡、季卡、年卡、永久等）
- 系统设置：站点名称、用户每日生成上限

### 验证 API
```
POST /api/verify
Content-Type: application/json

{ "code": "KMS-XXXX-XXXX-XXXX-XXXX" }
```
返回：
- 卡密不存在：`{"valid": false, "status": "not_found", "message": "卡密不存在"}`
- 已被使用：`{"valid": false, "status": "used", "message": "卡密已被使用"}`
- 验证通过：`{"valid": true, "status": "unused", "message": "验证通过，卡密已激活"}`（并自动标记为已使用）

## 运行

```bash
# 1. 安装依赖（建议使用虚拟环境）
pip install -r requirements.txt

# 2. 启动
python run.py

# 3. 访问
http://127.0.0.1:8000
```

默认管理员账号（首次启动自动创建，请登录后及时修改密码）：
- 用户名：`admin`
- 密码：`admin123`

> 生产部署前请修改 `app/config.py` 中的 `SECRET_KEY` 和默认管理员账号密码。

## 使用流程

1. 用管理员账号登录，进入“管理后台 → 卡密类型管理”添加类型（如月卡/季卡/年卡/永久）。
2. 用户注册登录后即可在首页自助生成卡密。
3. 第三方系统可通过 `POST /api/verify` 校验卡密。
4. 系统数据保存在 `data/card_system.db`（SQLite 文件）。

## 目录结构

```
├── run.py                  # 启动入口
├── requirements.txt
├── app/
│   ├── main.py             # FastAPI 应用入口
│   ├── config.py           # 集中配置
│   ├── database.py         # 数据库连接
│   ├── models.py           # ORM 模型
│   ├── schemas.py          # API 数据模型
│   ├── security.py         # 密码哈希 / 会话令牌
│   ├── utils.py            # 卡密生成
│   ├── deps.py             # 共享依赖
│   ├── templating.py       # 模板渲染封装
│   ├── router/             # 路由：public / admin / api
│   ├── static/             # 静态资源
│   └── templates/          # 页面模板
└── data/                   # SQLite 数据库（运行时生成）
```
