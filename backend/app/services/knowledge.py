"""运维知识库业务规则：案例不单独登记，直接从既有缺陷与消缺记录沉淀。

口径说明：
- 数据源：缺陷登记（defect）中「已闭环」的缺陷，配上消缺处理（repair）里关联同一
  缺陷编号、且已验收的消缺单；缺一条都不算可沉淀案例。
- 案例里的缺陷描述（编号、设备、类型等）直接取缺陷记录，不存副本，保证与缺陷登记一致。
- 同一缺陷编号只沉淀一条案例：消缺单重复登记（同一案例登记两次）时取最新一条，不重复显示。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

DEFECT_MODULE = "defect"
REPAIR_MODULE = "repair"
CLOSED_STATUS = "已闭环"
ACCEPTED_STATUS = "已验收"

# 案例在列表里展示的字段（同时也是关键词检索覆盖的字段）
LIST_FIELDS = [
    "案例编号",
    "设备类型",
    "缺陷类型",
    "缺陷编号",
    "所属设备",
    "处理措施",
    "处理人员",
    "处理耗时",
    "沉淀时间",
]
# 详情页带出的字段，缺陷侧字段与消缺侧字段分开，缺陷侧全部来自缺陷记录本身
DETAIL_FIELDS = [
    "案例编号",
    "缺陷编号",
    "所属设备",
    "设备类型",
    "缺陷类型",
    "严重等级",
    "发现时间",
    "发现人",
    "处理期限",
    "缺陷状态",
    "消缺单号",
    "处理措施",
    "备件消耗",
    "处理人员",
    "完成时间",
    "验收人员",
    "处理耗时",
    "沉淀时间",
]
KEYWORD_FIELDS = ["缺陷编号", "所属设备", "设备类型", "缺陷类型", "处理措施", "备件消耗", "处理人员"]
TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")


def _parse_time(value: Any) -> datetime | None:
    """尽量把「2026-09-01」或「2026-09-01 14:30」这类时间解析成 datetime。"""
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _format_duration(minutes: float) -> str:
    """把耗时分钟数格式化成值班人一眼能读懂的口径。"""
    total_minutes = int(round(minutes))
    days, remain = divmod(total_minutes, 24 * 60)
    hours, mins = divmod(remain, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}天")
    if hours:
        parts.append(f"{hours}小时")
    if mins or not parts:
        parts.append(f"{mins}分钟")
    return "".join(parts)


def _device_type(defect: dict[str, Any]) -> str:
    """从所属设备里归纳设备类型（取「逆变器-INV-…」这类编号的前缀）；归档不到时归到「其他设备」。"""
    device = str(defect.get("所属设备") or "").strip()
    if not device:
        return "其他设备"
    return device.split("-", 1)[0].strip() or "其他设备"


class KnowledgeService:
    def _build_cases(self) -> list[dict[str, Any]]:
        """从既有记录沉淀案例：闭环缺陷 × 已验收消缺单，按缺陷编号去重。"""
        defects = store.rows(DEFECT_MODULE)
        repairs = store.rows(REPAIR_MODULE)

        # 关联键是缺陷编号；同一缺陷登记了两张消缺单时只保留完成时间最新的一张
        latest_repair: dict[str, dict[str, Any]] = {}
        for repair in repairs:
            if repair.get("status") != ACCEPTED_STATUS:
                continue
            defect_no = str(repair.get("关联缺陷") or "").strip()
            if not defect_no:
                continue
            current = latest_repair.get(defect_no)
            if current is None or self._repair_time(repair) >= self._repair_time(current):
                latest_repair[defect_no] = repair

        cases: list[dict[str, Any]] = []
        for defect in defects:
            if defect.get("status") != CLOSED_STATUS:
                continue
            defect_no = str(defect.get("缺陷编号") or "").strip()
            repair = latest_repair.get(defect_no)
            if repair is None:
                continue
            cases.append(self._compose_case(defect, repair))
        # 最近沉淀的案例排前面
        cases.sort(key=lambda case: case["沉淀时间"], reverse=True)
        return cases

    @staticmethod
    def _repair_time(repair: dict[str, Any]) -> datetime:
        return _parse_time(repair.get("完成时间")) or datetime.min

    def _compose_case(self, defect: dict[str, Any], repair: dict[str, Any]) -> dict[str, Any]:
        """把一条闭环缺陷与它的消缺单拼成案例；缺陷侧字段原样透传，不做改写。"""
        found_at = _parse_time(defect.get("发现时间"))
        finished_at = _parse_time(repair.get("完成时间"))
        if found_at and finished_at and finished_at >= found_at:
            duration = _format_duration((finished_at - found_at).total_seconds() / 60)
        else:
            duration = "—"

        case = {field: defect.get(field) for field in (
            "缺陷编号", "所属设备", "缺陷类型", "严重等级", "发现时间", "发现人", "处理期限", "缺陷状态"
        )}
        case.update({
            "id": defect.get("id"),
            "案例编号": f"CASE-{int(defect.get('id', 0)):04d}",
            "设备类型": _device_type(defect),
            "消缺单号": repair.get("消缺单号"),
            "处理措施": repair.get("处理措施"),
            "备件消耗": repair.get("备件消耗"),
            "处理人员": repair.get("处理人员"),
            "完成时间": repair.get("完成时间"),
            "验收人员": repair.get("验收人员"),
            "处理耗时": duration,
            "沉淀时间": str(repair.get("完成时间") or ""),
            # 详情里可以回溯到两条源记录
            "缺陷记录ID": defect.get("id"),
            "消缺记录ID": repair.get("id"),
        })
        return case

    def list_cases(
        self,
        *,
        keyword: str | None = None,
        device_type: str | None = None,
        defect_type: str | None = None,
        begin: str | None = None,
        end: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        cases = self._build_cases()
        if keyword:
            kw = keyword.strip()
            cases = [
                case for case in cases
                if kw in " ".join(str(case.get(field) or "") for field in KEYWORD_FIELDS)
            ]
        if device_type:
            cases = [case for case in cases if case.get("设备类型") == device_type]
        if defect_type:
            cases = [case for case in cases if case.get("缺陷类型") == defect_type]
        begin_at = _parse_time(begin)
        end_at = _parse_time(end)
        if begin_at:
            cases = [
                case for case in cases
                if (case_dt := _parse_time(case.get("沉淀时间"))) is None or case_dt >= begin_at
            ]
        if end_at:
            cases = [
                case for case in cases
                if (case_dt := _parse_time(case.get("沉淀时间"))) is None or case_dt <= end_at
            ]

        total = len(cases)
        start = max(page - 1, 0) * size
        page_rows = [
            {"id": case.get("id"), **{field: case.get(field) for field in LIST_FIELDS}}
            for case in cases[start:start + size]
        ]
        return page_rows, total

    def get_case(self, case_id: int) -> dict[str, Any] | None:
        """按案例编号（CASE-xxxx 里的序号，对应缺陷记录 id）取详情。"""
        for case in self._build_cases():
            if int(case.get("缺陷记录ID") or 0) == case_id:
                return {field: case.get(field) for field in DETAIL_FIELDS + ["缺陷记录ID", "消缺记录ID"]}
        return None

    def filters(self) -> dict[str, list[str]]:
        """筛选项候选值：设备类型、缺陷类型都来自已沉淀案例，随数据自然收敛。"""
        cases = self._build_cases()
        device_types = sorted({str(case["设备类型"]) for case in cases if case.get("设备类型")})
        defect_types = sorted({str(case["缺陷类型"]) for case in cases if case.get("缺陷类型")})
        return {"设备类型": device_types, "缺陷类型": defect_types}


service = KnowledgeService()
