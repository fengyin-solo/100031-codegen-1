"""运维知识库接口：检索缺陷处置沉淀案例，只读，不提供登记入口。

案例数据源是既有缺陷登记与消缺处理记录，因此本模块没有新增/动作接口，
老的缺陷登记流程保持原样。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import PageResult
from app.services.knowledge import KnowledgeService

router = APIRouter(prefix="/api/knowledge", tags=["运维知识库"])

service = KnowledgeService()

LIST_FIELDS = ["案例编号", "设备类型", "所属设备", "缺陷类型", "严重等级", "处理措施", "处理人员", "处理耗时", "完成时间"]
DEVICE_TYPES = ["逆变器", "汇流箱", "光伏组串", "箱式变压器", "光伏组件", "辐照测点", "其他设备"]


@router.get("", response_model=PageResult[dict])
def list_cases(
    keyword: str | None = Query(default=None, description="按缺陷编号、设备、缺陷类型、处理措施等关键词检索"),
    device_type: str | None = Query(default=None, description="按设备类型归档筛选"),
    defect_type: str | None = Query(default=None, description="按缺陷类型归档筛选"),
    date_from: str | None = Query(default=None, description="完成时间起，YYYY-MM-DD"),
    date_to: str | None = Query(default=None, description="完成时间止，YYYY-MM-DD"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """列出沉淀案例；某段时间没有案例时返回空页，由前端展示引导提示而非空白。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_cases(
        keyword=keyword,
        device_type=device_type,
        defect_type=defect_type,
        date_from=date_from,
        date_to=date_to,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/meta")
def case_facets() -> dict[str, Any]:
    """归档维度与统计口径：设备类型/缺陷类型筛选项、案例总数、重复沉淀数、平均耗时。"""
    return service.facets()


@router.get("/export")
def export_cases(
    keyword: str | None = None,
    device_type: str | None = None,
    defect_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """导出知识库案例清单：返回当前筛选条件下的全量案例。"""
    items, total = service.list_cases(
        keyword=keyword,
        device_type=device_type,
        defect_type=defect_type,
        date_from=date_from,
        date_to=date_to,
        page=1,
        size=10000,
    )
    return {"module": "knowledge", "total": total, "items": items}


@router.get("/{case_id}", response_model=dict)
def get_case(case_id: int) -> dict:
    """读取单条案例详情，带出当时的处理措施、耗时与来源缺陷/消缺原始记录。"""
    case = service.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"知识库案例 {case_id} 不存在，或对应消缺尚未验收沉淀")
    return case
