"""运维知识库接口：只读检索既有缺陷/消缺记录沉淀下来的案例。

知识库不提供案例登记入口——老的缺陷登记流程照旧，案例随闭环自动沉淀。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import PageResult
from app.services.knowledge import LIST_FIELDS, service

router = APIRouter(prefix="/api/knowledge", tags=["运维知识库"])


@router.get("/filters")
def list_filters() -> dict[str, list[str]]:
    """设备类型、缺陷类型的筛选候选值，取自当前已沉淀案例。"""
    return service.filters()


@router.get("", response_model=PageResult[dict])
def list_cases(
    keyword: str | None = Query(default=None, description="按缺陷编号、设备、缺陷类型、处理措施等关键词检索"),
    device_type: str | None = Query(default=None, description="按设备类型归档过滤"),
    defect_type: str | None = Query(default=None, description="按缺陷类型归档过滤"),
    begin: str | None = Query(default=None, description="沉淀时间起，格式 YYYY-MM-DD"),
    end: str | None = Query(default=None, description="沉淀时间止，格式 YYYY-MM-DD"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """检索案例列表；某段时间没有沉淀时返回空页，由前端展示空状态而不是一片空白。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_cases(
        keyword=keyword,
        device_type=device_type,
        defect_type=defect_type,
        begin=begin,
        end=end,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{case_id}", response_model=dict)
def get_case(case_id: int) -> dict[str, Any]:
    """案例详情：带出当时的处理措施与处理耗时；缺陷侧描述与缺陷登记记录保持一致。"""
    case = service.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"案例 {case_id} 不存在，或源缺陷尚未闭环沉淀")
    return case


@router.get("/export/all")
def export_cases(
    keyword: str | None = None,
    device_type: str | None = None,
    defect_type: str | None = None,
) -> dict[str, Any]:
    """导出当前过滤条件下的全量案例。"""
    items, total = service.list_cases(
        keyword=keyword,
        device_type=device_type,
        defect_type=defect_type,
        page=1,
        size=10000,
    )
    return {"module": "knowledge", "fields": LIST_FIELDS, "total": total, "items": items}
