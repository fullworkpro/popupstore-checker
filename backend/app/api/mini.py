"""小程序端 API — 公开访问"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional
from app.core.database import get_db
from app.models.store import (
    Store,
    StoreStatus,
    STORE_TYPES,
    STORE_TYPE_VALUES,
    DEFAULT_STORE_TYPE,
)
from app.schemas.schemas import StoreResponse, StoreListResponse
from app.services.archive import maybe_archive_expired

router = APIRouter(prefix="/mini", tags=["小程序"])


@router.get("/stores", response_model=StoreListResponse)
def list_stores(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    city: Optional[str] = None,
    store_type: Optional[str] = None,
    keyword: Optional[str] = None,
    tag: Optional[str] = None,
    sort: Optional[str] = "newest",  # newest / hottest / ending_soon
    db: Session = Depends(get_db),
):
    """小程序端快闪店列表 — 仅返回已发布内容"""
    # 请求级懒归档（内部节流 5 分钟）：保证已结束的活动不会出现在小程序
    maybe_archive_expired(db)

    q = db.query(Store).filter(Store.status == StoreStatus.PUBLISHED.value)

    if city:
        # 支持多城市：主城市匹配，或 cities JSON 中含该城市
        q = q.filter((Store.city == city) | (Store.cities.contains(city)))
    if store_type and store_type in STORE_TYPE_VALUES:
        if store_type == DEFAULT_STORE_TYPE:
            # 该列是后加的，历史行可能为 NULL；NULL 一律按默认类型（联名快闪）处理，
            # 否则这些老数据在小程序里会凭空消失。
            q = q.filter(
                (Store.store_type == store_type) | (Store.store_type.is_(None))
            )
        else:
            q = q.filter(Store.store_type == store_type)
    if keyword:
        q = q.filter(
            (Store.title.contains(keyword)) | (Store.description.contains(keyword))
        )
    if tag:
        q = q.filter(Store.tags.contains(tag))

    # 排序
    if sort == "hottest":
        q = q.order_by(desc(Store.view_count))
    elif sort == "ending_soon":
        q = q.filter(Store.end_date.isnot(None)).order_by(Store.end_date.asc())
    else:  # newest
        q = q.order_by(desc(Store.created_at))

    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    return StoreListResponse(
        items=[StoreResponse.model_validate(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stores/{store_id}", response_model=StoreResponse)
def get_store(store_id: str, db: Session = Depends(get_db)):
    """获取详情，同时增加浏览量"""
    maybe_archive_expired(db)

    store = db.query(Store).filter(
        Store.id == store_id,
        Store.status == StoreStatus.PUBLISHED.value,
    ).first()
    if not store:
        raise HTTPException(status_code=404, detail="快闪店不存在或已下架")

    store.view_count = (store.view_count or 0) + 1
    db.commit()
    db.refresh(store)

    return StoreResponse.model_validate(store)


@router.get("/banners", response_model=list)
def get_banners(db: Session = Depends(get_db)):
    """首页 Banner — 取最新发布的 5 条"""
    maybe_archive_expired(db)

    stores = (
        db.query(Store)
        .filter(Store.status == StoreStatus.PUBLISHED.value)
        .order_by(desc(Store.created_at))
        .limit(5)
        .all()
    )
    return [
        {
            "id": s.id,
            "title": s.title,
            "cover_image": s.cover_image,
            "city": s.city,
            "start_date": s.start_date.isoformat() if s.start_date else None,
        }
        for s in stores
    ]


@router.get("/cities", response_model=list)
def list_cities(db: Session = Depends(get_db)):
    """返回有已发布内容的城市列表"""
    maybe_archive_expired(db)

    results = (
        db.query(Store.city)
        .filter(Store.status == StoreStatus.PUBLISHED.value, Store.city != "")
        .distinct()
        .all()
    )
    return sorted([r[0] for r in results if r[0]])


@router.get("/tags", response_model=list)
def list_tags(db: Session = Depends(get_db)):
    """返回热门标签"""
    maybe_archive_expired(db)

    # 简化处理：从已发布内容的 tags JSON 中提取
    stores = (
        db.query(Store.tags)
        .filter(Store.status == StoreStatus.PUBLISHED.value, Store.tags != "[]")
        .limit(200)
        .all()
    )
    tag_counter = {}
    import json
    for (tags_str,) in stores:
        try:
            for t in json.loads(tags_str):
                tag_counter[t] = tag_counter.get(t, 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass
    sorted_tags = sorted(tag_counter.items(), key=lambda x: x[1], reverse=True)[:30]
    return [{"name": t, "count": c} for t, c in sorted_tags]


@router.get("/store-types", response_model=list)
def list_store_types():
    """快闪类型字典 — 小程序首页「快闪类型」下拉使用。

    与后台录入表单共用 models.store.STORE_TYPES，避免两处硬编码不一致。
    """
    return STORE_TYPES
