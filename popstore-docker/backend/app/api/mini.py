"""小程序端 API — 公开访问"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional
from app.core.database import get_db
from app.models.store import Store, StoreStatus
from app.schemas.schemas import StoreResponse, StoreListResponse

router = APIRouter(prefix="/mini", tags=["小程序"])


@router.get("/stores", response_model=StoreListResponse)
def list_stores(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    city: Optional[str] = None,
    keyword: Optional[str] = None,
    tag: Optional[str] = None,
    sort: Optional[str] = "newest",  # newest / hottest / ending_soon
    db: Session = Depends(get_db),
):
    """小程序端快闪店列表 — 仅返回已发布内容"""
    q = db.query(Store).filter(Store.status == StoreStatus.PUBLISHED.value)

    if city:
        q = q.filter(Store.city == city)
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
