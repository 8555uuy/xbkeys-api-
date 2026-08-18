-- ============================================================
-- xb密钥系统 - Supabase (PostgreSQL) 建表 SQL
-- 在 Supabase 控制台 -> SQL Editor 中执行本脚本。
-- 应用启动时也会通过 SQLAlchemy 自动建表；此脚本用于手动初始化。
-- 与项目内 app/models.py 中的模型保持一致。
-- ============================================================

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id            BIGSERIAL PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    password_hash VARCHAR(200) NOT NULL,
    is_admin      BOOLEAN      NOT NULL DEFAULT FALSE,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- 卡密类型表
CREATE TABLE IF NOT EXISTS card_types (
    id            BIGSERIAL PRIMARY KEY,
    name          VARCHAR(50) NOT NULL UNIQUE,
    duration_days INTEGER     NOT NULL DEFAULT 30,
    description   VARCHAR(200) NOT NULL DEFAULT '',
    created_at    TIMESTAMP   NOT NULL DEFAULT NOW()
);

-- 卡密表（含到期时间与使用方设备信息）
CREATE TABLE IF NOT EXISTS cards (
    id            BIGSERIAL PRIMARY KEY,
    code          VARCHAR(64)  NOT NULL UNIQUE,
    type_id       BIGINT REFERENCES card_types(id),
    owner_id      BIGINT REFERENCES users(id),
    status        VARCHAR(20)  NOT NULL DEFAULT 'unused',
    generated_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    expires_at    TIMESTAMP,                          -- 到期时间（NULL 表示永久）
    used_at       TIMESTAMP,                          -- 使用时间
    used_ip       VARCHAR(50)  NOT NULL DEFAULT '',   -- 使用方IP
    used_ua       VARCHAR(300) NOT NULL DEFAULT '',   -- 使用方User-Agent
    used_device   VARCHAR(100) NOT NULL DEFAULT ''    -- 使用方设备信息
);

-- 系统设置表（键值对）
CREATE TABLE IF NOT EXISTS settings (
    key   VARCHAR(50)  PRIMARY KEY,
    value VARCHAR(200) NOT NULL DEFAULT ''
);

-- 登录会话表
CREATE TABLE IF NOT EXISTS sessions (
    token      VARCHAR(64) PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL
);

-- 操作日志表
CREATE TABLE IF NOT EXISTS operation_logs (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT,
    username   VARCHAR(50)  NOT NULL DEFAULT '',
    action     VARCHAR(50)  NOT NULL,
    detail     VARCHAR(300) NOT NULL DEFAULT '',
    ip         VARCHAR(50)  NOT NULL DEFAULT '',
    created_at TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- 常用索引
CREATE INDEX IF NOT EXISTS ix_cards_code      ON cards (code);
CREATE INDEX IF NOT EXISTS ix_cards_type_id   ON cards (type_id);
CREATE INDEX IF NOT EXISTS ix_cards_owner_id  ON cards (owner_id);
CREATE INDEX IF NOT EXISTS ix_users_username  ON users (username);
CREATE INDEX IF NOT EXISTS ix_operation_logs_action     ON operation_logs (action);
CREATE INDEX IF NOT EXISTS ix_operation_logs_created_at ON operation_logs (created_at);