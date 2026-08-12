"""数据库连接与会话管理"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# SQLite 需要 check_same_thread=False
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# SQLite 外键支持
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db():
    """FastAPI 依赖注入 — 获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """创建所有表并初始化默认管理员"""
    from app.models.store import Store, CrawlLog  # noqa: F401
    from app.models.admin import Admin, LoginAttempt  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # 无损迁移：补上旧库里缺失的列（模型已新增、但已存在表未迁移）
    _upgrade_columns(engine)

    # 创建默认管理员
    db = SessionLocal()
    try:
        from app.models.admin import Admin
        if not db.query(Admin).filter(Admin.username == settings.DEFAULT_ADMIN_USERNAME).first():
            admin = Admin()
            admin.username = settings.DEFAULT_ADMIN_USERNAME
            admin.set_password(settings.DEFAULT_ADMIN_PASSWORD)
            db.add(admin)
            db.commit()
            print(f"[INIT] 默认管理员已创建: {settings.DEFAULT_ADMIN_USERNAME}")
    finally:
        db.close()


def _upgrade_columns(engine):
    """无损迁移：给已存在的表补上模型里有、但数据库实际缺的列。

    SQLAlchemy 的 create_all 只建新表、不修改已存在表的结构，
    因此当模型新增列而旧库未迁移时会报 no such column。这里做幂等补列。
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    for table_name, table in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue
        existing = {c["name"] for c in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name in existing or column.primary_key:
                continue
            col_type = column.type.compile(dialect=engine.dialect)
            ddl = f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" {col_type}'
            # 处理默认值（跳过 callable 默认值，避免执行副作用）
            default = getattr(column.default, "arg", None)
            if default is not None and not callable(default):
                if isinstance(default, str):
                    ddl += f" DEFAULT '{default}'"
                elif isinstance(default, bool):
                    ddl += f" DEFAULT {1 if default else 0}"
                else:
                    ddl += f" DEFAULT {default}"
            print(f"[MIGRATE] 表 {table_name} 新增列 {column.name} ({col_type})")
            with engine.begin() as conn:
                conn.execute(text(ddl))
