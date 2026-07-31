"""MySQL 연결(PyMySQL) — jobs 테이블 polling 전용.

ORM 없이 최소 커넥션만 감싼다. Spring Boot(JPA)와 같은 auto_sns 스키마를 공유하지만,
워커는 jobs 테이블만 직접 다룬다(users/projects/assets는 아직 건드리지 않음).
"""

from __future__ import annotations

import pymysql
import pymysql.cursors

from .config import load_db_config


def get_connection() -> pymysql.connections.Connection:
    cfg = load_db_config()
    return pymysql.connect(
        host=cfg.host,
        port=cfg.port,
        database=cfg.name,
        user=cfg.user,
        password=cfg.password,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
