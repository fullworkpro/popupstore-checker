"""数据库连接与会话管理"""
import logging
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

logger = logging.getLogger("popstore")

# SQLite 需要 check_same_thread=False
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    # 数据库落在 NAS 网络共享卷上时，文件锁不可靠；设较长超时避免请求无限挂起
    connect_args["timeout"] = 30

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_reset_on_return="rollback",
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# SQLite 外键支持 + 网络挂载锁优化
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        # 繁忙时等待锁而非立即报错/无限挂起（NAS 网络共享卷下尤其重要）
        cursor.execute("PRAGMA busy_timeout=30000")
        # 注意：DB 在 NAS 网络共享卷上时 **不要用 WAL**（WAL 依赖 -shm 共享内存，
        # 网络文件系统支持差，反而更易卡死）；用默认 rollback journal + NORMAL 同步即可
        cursor.execute("PRAGMA synchronous=NORMAL")
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
    """创建所有表并初始化默认管理员（启动期异常不再阻塞整个后端）"""
    from app.models.store import Store, CrawlLog  # noqa: F401
    from app.models.admin import Admin, LoginAttempt  # noqa: F401
    try:
        Base.metadata.create_all(bind=engine)
        # 无损迁移：补上旧库里缺失的列（模型已新增、但已存在表未迁移）
        _upgrade_columns(engine)
    except Exception as e:
        logger.warning("⚠️ 数据库初始化/迁移异常（应用仍启动，功能可能受限）: %s", e)

    # 创建默认管理员
    db = SessionLocal()
    try:
        if not db.query(Admin).filter(Admin.username == settings.DEFAULT_ADMIN_USERNAME).first():
            admin = Admin()
            admin.username = settings.DEFAULT_ADMIN_USERNAME
            admin.set_password(settings.DEFAULT_ADMIN_PASSWORD)
            db.add(admin)
            db.commit()
            print(f"[INIT] 默认管理员已创建: {settings.DEFAULT_ADMIN_USERNAME}")
    except Exception as e:
        db.rollback()
        print(f"[INIT] 默认管理员创建失败（可忽略，若已存在）: {e}")
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
