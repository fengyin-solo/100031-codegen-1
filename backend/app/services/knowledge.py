"""运维知识库业务规则：从缺陷登记与消缺处理既有记录里沉淀可检索案例。

案例不单独登记、不另存一份：每次查询都实时关联缺陷记录（defect）与已验收的
消缺单（repair）生成，保证案例描述与缺陷记录始终一致。老的缺陷/消缺登记流程
无需感知本模块。

沉淀口径：
- 只有已验收（处理状态=已验收）的消缺单才沉淀为案例；
- 同一缺陷下重复登记的消缺单只沉淀一条案例，耗时按首次完成的处理计算，
  重复登记的消缺单号在案例详情里留痕；
- 设备类型由缺陷「所属设备」名称归类，便于按设备类型归档检索。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

DEFECT_MODULE = "defect"
REPAIR_MODULE = "repair"

# 已验收才代表处理措施经过确认，可作为经验沉淀进知识库
SETTLED_STATUS = "已验收"

# 关键词在这些字段里做包含匹配（案例列表按关键词定位往期案例）
SEARCH_FIELDS = [
    "缺陷编号", "所属设备", "设备类型", "缺陷类型", "严重等级",
    "处理措施", "处理人员", "备件消耗",
]

# 设备类型归类：按设备名称里的特征词命中，顺序即优先级
DEVICE_TYPE_RULES = [
    ("组串", "光伏组串"),
    ("逆变器", "逆变器"),
    ("汇流箱", "汇流箱"),
    ("辐照", "辐照测点"),
    ("箱变", "箱式变压器"),
    ("组件", "光伏组件"),
]
DEFAULT_DEVICE_TYPE = "其他设备"

_TIME_PATTERNS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")


def classify_device_type(device_name: str) -> str:
    """按设备名称特征归类设备类型；没有命中特征词时归入其他设备。"""
    name = device_name or ""
    for keyword, device_type in DEVICE_TYPE_RULES:
        if keyword in name:
            return device_type
    return DEFAULT_DEVICE_TYPE


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in _TIME_PATTERNS:
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _format_duration(minutes: int) -> str:
    """把耗时分钟数整理成值班人一眼能看懂的文案。"""
    if minutes < 60:
        return f"{minutes}分钟"
    hours, remain = divmod(minutes, 60)
    if remain:
        return f"{hours}小时{remain}分钟"
    return f"{hours}小时"


def build_case(defect: dict[str, Any], repairs: list[dict[str, Any]]) -> dict[str, Any]:
    """把一条缺陷和它名下已验收的消缺单组合成一条案例。

    耗时以最早完成的处理为准（重复补录不应把案例耗时拉长）；案例描述字段全部
    直接取自缺陷记录，避免与缺陷登记两边不一致。
    """
    repairs = sorted(repairs, key=lambda row: _parse_time(row.get("完成时间")) or datetime.max)
    primary, *duplicates = repairs
    finished_at = _parse_time(primary.get("完成时间"))
    found_at = _parse_time(defect.get("发现时间"))
    if finished_at and found_at:
        duration_minutes = max(int((finished_at - found_at).total_seconds() // 60), 0)
        duration_text = _format_duration(duration_minutes)
    else:
        duration_minutes = None
        duration_text = "—"

    device_name = str(defect.get("所属设备") or "")
    return {
        # 案例直接引用缺陷记录 id，案例详情与缺陷登记指向同一条数据
        "id": defect.get("id"),
        "案例编号": f"KB-{str(defect.get('缺陷编号') or '').replace('DEFE-', '')}",
        "缺陷编号": defect.get("缺陷编号"),
        "设备类型": classify_device_type(device_name),
        "所属设备": device_name,
        "缺陷类型": defect.get("缺陷类型"),
        "严重等级": defect.get("严重等级"),
        "发现时间": defect.get("发现时间"),
        "发现人": defect.get("发现人"),
        "处理期限": defect.get("处理期限"),
        "消缺单号": primary.get("消缺单号"),
        "处理措施": primary.get("处理措施"),
        "备件消耗": primary.get("备件消耗"),
        "处理人员": primary.get("处理人员"),
        "完成时间": primary.get("完成时间"),
        "验收人员": primary.get("验收人员"),
        "处理耗时": duration_text,
        "处理耗时分钟": duration_minutes,
        "沉淀时间": primary.get("完成时间"),
        "重复登记次数": len(duplicates),
        "重复消缺单号": [str(item.get("消缺单号")) for item in duplicates],
        # 列表倒序用，输出前会剔除，不暴露给前端
        "_sort_time": finished_at or datetime.min,
    }


def _public_view(case: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in case.items() if not key.startswith("_")}


class KnowledgeService:
    def _load_cases(self) -> list[dict[str, Any]]:
        """关联缺陷与已验收消缺单，按缺陷编号去重后生成案例（最新完成排最前）。"""
        defects = store.rows(DEFECT_MODULE)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for repair in store.rows(REPAIR_MODULE):
            if repair.get("status") != SETTLED_STATUS:
                continue
            ref = str(repair.get("关联缺陷") or "").strip()
            if ref:
                grouped.setdefault(ref, []).append(repair)

        cases: list[dict[str, Any]] = []
        for defect in defects:
            ref = str(defect.get("缺陷编号") or "").strip()
            repairs = grouped.get(ref)
            if not repairs:
                continue
            cases.append(build_case(defect, repairs))
        cases.sort(key=lambda case: case["_sort_time"], reverse=True)
        return cases

    def list_cases(
        self,
        *,
        keyword: str | None = None,
        device_type: str | None = None,
        defect_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """按设备类型、缺陷类型、关键词与完成时间区间检索案例。"""
        cases = self._load_cases()

        if device_type:
            cases = [case for case in cases if case["设备类型"] == device_type]
        if defect_type:
            cases = [case for case in cases if case["缺陷类型"] == defect_type]
        if date_from:
            start = _parse_time(date_from)
            cases = [
                case for case in cases
                if (finished := _parse_time(case["完成时间"])) is None
                or (start is not None and finished.date() >= start.date())
            ]
        if date_to:
            end = _parse_time(date_to)
            cases = [
                case for case in cases
                if (finished := _parse_time(case["完成时间"])) is None
                or (end is not None and finished.date() <= end.date())
            ]
        if keyword:
            word = keyword.strip()
            if word:
                cases = [
                    case for case in cases
                    if any(word.lower() in str(case.get(field) or "").lower() for field in SEARCH_FIELDS)
                ]

        total = len(cases)
        start_index = max(page - 1, 0) * size
        page_rows = [_public_view(case) for case in cases[start_index:start_index + size]]
        return page_rows, total

    def get_case(self, case_id: int) -> dict[str, Any] | None:
        """案例详情：带出处理措施、耗时，并附来源缺陷/消缺原始记录用于核对一致性。"""
        for case in self._load_cases():
            if int(case.get("id", 0)) != case_id:
                continue
            detail = _public_view(case)
            defect = store.find(DEFECT_MODULE, case_id)
            ref = str((defect or {}).get("缺陷编号") or detail.get("缺陷编号") or "")
            detail["来源缺陷记录"] = defect
            detail["来源消缺记录"] = [
                repair for repair in store.rows(REPAIR_MODULE)
                if str(repair.get("关联缺陷") or "").strip() == ref
                and repair.get("status") == SETTLED_STATUS
            ]
            return detail
        return None

    def facets(self) -> dict[str, Any]:
        """归档维度与看板统计：设备类型/缺陷类型筛选项、案例总数与平均耗时。"""
        cases = self._load_cases()
        device_counts: dict[str, int] = {}
        defect_counts: dict[str, int] = {}
        duration_values: list[int] = []
        latest = None
        for case in cases:
            device_counts[case["设备类型"]] = device_counts.get(case["设备类型"], 0) + 1
            defect_counts[str(case["缺陷类型"])] = defect_counts.get(str(case["缺陷类型"]), 0) + 1
            if case["处理耗时分钟"] is not None:
                duration_values.append(int(case["处理耗时分钟"]))
            if latest is None or case["_sort_time"] > latest:
                latest = case["_sort_time"]

        avg_minutes = int(sum(duration_values) / len(duration_values)) if duration_values else None
        return {
            "total": len(cases),
            "duplicated": sum(1 for case in cases if case["重复登记次数"] > 0),
            "avg_duration": _format_duration(avg_minutes) if avg_minutes is not None else "—",
            "latest_case_time": latest.strftime("%Y-%m-%d") if latest and latest != datetime.min else None,
            "device_types": [
                {"name": name, "count": count}
                for name, count in sorted(device_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
            "defect_types": [
                {"name": name, "count": count}
                for name, count in sorted(defect_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
        }
