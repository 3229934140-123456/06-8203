from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from calendar_utils import CalendarArithmetic


@dataclass
class CronField:
    """
    Cron 单个字段的解析结果。

    字段范围：
    - second (秒):     0-59
    - minute (分):     0-59
    - hour (时):       0-23
    - day (日):        1-31    [高级语法: L (月末), NW (最近N号的工作日)]
    - month (月):      1-12
    - weekday (周几):  0-6     [高级语法: N#M (本月第M个周N), L (最后一个周几)]

    支持的高级语法：
    - L        : 月末 (day 字段)，或"最后一个周N" (weekday 字段，如 "6L"=最后一个周六)
    - NW       : 最接近 N 号的工作日 (day 字段，如 "15W"，避开周末)
    - N#M      : 本月第 M 个周 N (weekday 字段，如 "1#3"=第3个周一, "MON#2"=第2个周一)
    """

    name: str
    min_value: int
    max_value: int
    values: Set[int] = field(default_factory=set)
    any: bool = False
    unspecified: bool = False

    # day 字段高级语法
    last_day: bool = False
    nearest_workday_to: Optional[int] = None

    # weekday 字段高级语法: [(weekday, nth_in_month)]  # nth=None 表示"最后一个"
    nth_weekdays: List[Tuple[int, Optional[int]]] = field(default_factory=list)
    weekday_last: Set[int] = field(default_factory=set)

    MONTH_NAMES = {
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    }
    WEEKDAY_NAMES = {
        "SUN": 0, "MON": 1, "TUE": 2, "WED": 3, "THU": 4, "FRI": 5, "SAT": 6,
    }

    @classmethod
    def parse(
        cls,
        expr: str,
        name: str,
        min_value: int,
        max_value: int,
        allow_question: bool = False,
    ) -> "CronField":
        """解析单个 cron 字段。"""
        values: Set[int] = set()
        last_day = False
        nearest_workday_to: Optional[int] = None
        nth_weekdays: List[Tuple[int, Optional[int]]] = []
        weekday_last: Set[int] = set()

        expr = expr.strip().upper()

        if expr == "*":
            return cls(
                name=name,
                min_value=min_value,
                max_value=max_value,
                values=set(range(min_value, max_value + 1)),
                any=True,
            )

        if allow_question and expr == "?":
            return cls(
                name=name,
                min_value=min_value,
                max_value=max_value,
                values=set(range(min_value, max_value + 1)),
                unspecified=True,
            )

        name_map: Dict[str, int] = {}
        if name == "month":
            name_map = cls.MONTH_NAMES
        elif name == "weekday":
            name_map = cls.WEEKDAY_NAMES

        parts = expr.split(",")
        for part in parts:
            if name == "day" and part == "L":
                last_day = True
                continue

            if name == "day" and part.endswith("W"):
                day_num_str = part[:-1]
                if day_num_str.isdigit():
                    nearest_workday_to = int(day_num_str)
                    if not (1 <= nearest_workday_to <= 31):
                        raise ValueError(f"工作日锚点超出范围: {part}")
                    continue
                raise ValueError(f"无法解析工作日表达式: {part}")

            if name == "weekday" and "#" in part:
                wd_str, nth_str = part.split("#", 1)
                wd = cls._resolve_value(wd_str, name_map)
                if wd == 7:
                    wd = 0
                if not (0 <= wd <= 6):
                    raise ValueError(f"周几超出范围: {wd_str}")
                if not nth_str.isdigit():
                    raise ValueError(f"第几个周几必须是数字: {nth_str}")
                nth = int(nth_str)
                if not (1 <= nth <= 5):
                    raise ValueError(f"第几个周几必须在 1-5 之间: {nth}")
                nth_weekdays.append((wd, nth))
                continue

            if name == "weekday" and part.endswith("L"):
                wd_str = part[:-1]
                wd = cls._resolve_value(wd_str, name_map) if wd_str else None
                if wd is None:
                    continue
                if wd == 7:
                    wd = 0
                weekday_last.add(wd)
                continue

            values.update(cls._parse_part(part, min_value, max_value, name_map))

        if name == "day" and (last_day or nearest_workday_to is not None):
            if not values:
                values = set(range(1, 32))

        if name == "weekday" and (nth_weekdays or weekday_last):
            if not values:
                values = set(range(0, 7))

        if not values:
            raise ValueError(f"字段 {name} 没有匹配的值: {expr}")

        for v in values:
            if v < min_value or v > max_value:
                raise ValueError(
                    f"字段 {name} 的值 {v} 超出范围 [{min_value}, {max_value}]"
                )

        return cls(
            name=name,
            min_value=min_value,
            max_value=max_value,
            values=values,
            last_day=last_day,
            nearest_workday_to=nearest_workday_to,
            nth_weekdays=nth_weekdays,
            weekday_last=weekday_last,
        )

    @staticmethod
    def _parse_part(
        part: str,
        min_value: int,
        max_value: int,
        name_map: dict,
    ) -> Set[int]:
        result: Set[int] = set()

        step = 1
        if "/" in part:
            range_part, step_str = part.split("/", 1)
            step = int(step_str)
            if step <= 0:
                raise ValueError(f"步长必须为正整数: {step_str}")
        else:
            range_part = part

        if range_part == "*" or range_part == "":
            start, end = min_value, max_value
        elif "-" in range_part:
            start_str, end_str = range_part.split("-", 1)
            start = CronField._resolve_value(start_str, name_map)
            end = CronField._resolve_value(end_str, name_map)
        else:
            if "/" in part:
                start = CronField._resolve_value(range_part, name_map)
                end = max_value
            else:
                val = CronField._resolve_value(range_part, name_map)
                if val == 7 and CronField._try_is_weekday(name_map):
                    return {0}
                return {val}

        for v in range(start, end + 1, step):
            if v == 7 and CronField._try_is_weekday(name_map):
                result.add(0)
            else:
                result.add(v)

        return result

    @staticmethod
    def _try_is_weekday(name_map: dict) -> bool:
        return 0 in name_map.values() and 1 in name_map.values()

    @staticmethod
    def _resolve_value(val_str: str, name_map: dict) -> int:
        val_str = val_str.strip().upper()
        if val_str in name_map:
            return name_map[val_str]
        try:
            return int(val_str)
        except ValueError:
            raise ValueError(f"无法解析值: {val_str}")

    def matches(self, value: int) -> bool:
        return value in self.values

    def next_value(self, current: int) -> Optional[int]:
        """获取大于 current 的最小值，如果没有则返回 None。"""
        for v in sorted(self.values):
            if v > current:
                return v
        return None

    def first_value(self) -> int:
        return min(self.values)

    def __contains__(self, value: int) -> bool:
        return value in self.values


class CronExpression:
    """
    Cron 表达式解析与计算。

    支持两种格式：
    - 5字段（标准 Unix Cron）：分 时 日 月 周几
    - 6字段（带秒）：秒 分 时 日 月 周几

    字段说明：
    ┌───────────── 秒 (0-59)       [可选，6字段格式]
    │ ┌───────────── 分 (0-59)
    │ │ ┌───────────── 时 (0-23)
    │ │ │ ┌───────────── 日 (1-31)
    │ │ │ │ ┌───────────── 月 (1-12)
    │ │ │ │ │ ┌───────────── 周几 (0-6, 0=周日)
    │ │ │ │ │ │
    * * * * * *

    特殊规则：
    - 日和周几字段：如果其中一个指定为 ?（不关心），则按另一个匹配；
      如果都指定了具体值，则两者都要匹配（OR 关系 - 但大多数 Cron 实现是两者之一匹配即触发）。
      本实现采用标准 Quartz 风格：日和周几同时指定时，OR 匹配。
    """

    FIELD_NAMES_6 = ["second", "minute", "hour", "day", "month", "weekday"]
    FIELD_NAMES_5 = ["minute", "hour", "day", "month", "weekday"]

    FIELD_RANGES = {
        "second": (0, 59),
        "minute": (0, 59),
        "hour": (0, 23),
        "day": (1, 31),
        "month": (1, 12),
        "weekday": (0, 6),
    }

    def __init__(
        self,
        second: CronField,
        minute: CronField,
        hour: CronField,
        day: CronField,
        month: CronField,
        weekday: CronField,
        raw_expression: str,
    ):
        self.second = second
        self.minute = minute
        self.hour = hour
        self.day = day
        self.month = month
        self.weekday = weekday
        self.raw_expression = raw_expression

    @classmethod
    def parse(cls, expression: str) -> "CronExpression":
        """
        解析 Cron 表达式字符串。

        示例:
        - "0 0 12 * * ?"        : 每天中午12点
        - "0 */5 * * * ?"       : 每5分钟
        - "0 0 0 1 * ?"         : 每月1号零点
        - "0 0 9 ? * MON-FRI"   : 工作日早上9点
        - "30 5 15 * * ?"       : 每天15:05:30
        """
        tokens = expression.strip().split()
        if len(tokens) == 5:
            tokens = ["0"] + tokens
        elif len(tokens) != 6:
            raise ValueError(
                f"Cron 表达式必须有5或6个字段，当前有 {len(tokens)} 个: {expression}"
            )

        fields = {}
        for name, token in zip(cls.FIELD_NAMES_6, tokens):
            min_val, max_val = cls.FIELD_RANGES[name]
            allow_question = name in ("day", "weekday")

            if name == "weekday":
                token = cls._normalize_weekday(token)

            fields[name] = CronField.parse(
                token, name, min_val, max_val, allow_question
            )

        if not fields["day"].unspecified and not fields["weekday"].unspecified:
            pass

        return cls(
            second=fields["second"],
            minute=fields["minute"],
            hour=fields["hour"],
            day=fields["day"],
            month=fields["month"],
            weekday=fields["weekday"],
            raw_expression=expression,
        )

    @staticmethod
    def _normalize_weekday(token: str) -> str:
        """
        标准化周几字段。
        - Unix Cron 使用 0-6，0=周日
        - Quartz 使用 1-7，7=周日，1=周一
        本实现统一转换为 0-6，0=周日
        同时保留高级语法标记：#N (第N个)、L (最后一个)
        """
        result = []
        for part in token.split(","):
            # 处理 MON#3 / 2#3 (第N个周几)
            if "#" in part:
                base, nth = part.split("#", 1)
                base_norm = CronExpression._normalize_single_weekday_val(base)
                result.append(f"{base_norm}#{nth}")
                continue
            # 处理 MONL / 6L (最后一个周几)
            if part.upper().endswith("L"):
                base = part[:-1]
                base_norm = CronExpression._normalize_single_weekday_val(base) if base else base
                result.append(f"{base_norm}L")
                continue
            # 处理 */step 和 普通范围
            dash_parts = part.split("/")
            range_expr = dash_parts[0]

            if "-" in range_expr:
                r_start, r_end = range_expr.split("-", 1)
                range_expr = (
                    f"{CronExpression._normalize_single_weekday_val(r_start)}-"
                    f"{CronExpression._normalize_single_weekday_val(r_end)}"
                )
            else:
                range_expr = CronExpression._normalize_single_weekday_val(range_expr)

            if len(dash_parts) > 1:
                result.append(f"{range_expr}/{dash_parts[1]}")
            else:
                result.append(range_expr)

        return ",".join(result)

    @staticmethod
    def _normalize_single_weekday_val(v: str) -> str:
        v = v.strip().upper()
        if v in CronField.WEEKDAY_NAMES:
            return str(CronField.WEEKDAY_NAMES[v])
        if v in ("*", "?"):
            return v
        try:
            n = int(v)
            if n == 7:
                return "0"
            if 0 <= n <= 6:
                return str(n)
            if 1 <= n <= 7:
                return str(n - 1)
            return v
        except ValueError:
            return v

    # ============================================================
    # 高级语法辅助方法
    # ============================================================

    @staticmethod
    def _nth_weekday_in_month(year: int, month: int, weekday: int, nth: int) -> Optional[int]:
        """
        计算 (year, month) 中第 nth 个 weekday 的日期（1..31），不存在返回 None。
        weekday: 0=周日 .. 6=周六；nth: 1..5
        """
        first = datetime(year, month, 1)
        first_wd = (first.weekday() + 1) % 7  # Python 的 weekday() 0=周一，统一转为 0=周日
        delta = (weekday - first_wd + 7) % 7
        first_occurrence = 1 + delta
        target_day = first_occurrence + (nth - 1) * 7
        max_day = CalendarArithmetic.days_in_month(year, month)
        return target_day if target_day <= max_day else None

    @staticmethod
    def _last_weekday_in_month(year: int, month: int, weekday: int) -> int:
        """返回 (year, month) 中最后一个 weekday 的日期。"""
        last_day = CalendarArithmetic.days_in_month(year, month)
        last_dt = datetime(year, month, last_day)
        last_wd = (last_dt.weekday() + 1) % 7
        delta = (last_wd - weekday + 7) % 7
        return last_day - delta

    @staticmethod
    def _nearest_workday(year: int, month: int, day: int) -> int:
        """
        计算最接近 day 号的工作日（周一至周五）。
        规则：
          - day 本身是工作日 (0..4 对应周一到周五)，返回 day
          - 若为周六，返回 day-1（周五）
          - 若为周日，返回 day+1（周一）
          - 若 day-1 / day+1 跨月，则取最近的非周末
        """
        max_day = CalendarArithmetic.days_in_month(year, month)
        dt = datetime(year, month, min(max(day, 1), max_day))
        py_wd = dt.weekday()  # 0=周一 .. 5=周六 .. 6=周日
        if py_wd <= 4:
            return dt.day
        if py_wd == 5:  # 周六 -> 周五
            return dt.day - 1 if dt.day > 1 else dt.day + 2
        # 周日 -> 周一
        return dt.day + 1 if dt.day < max_day else dt.day - 2

    # ============================================================
    # 匹配逻辑
    # ============================================================

    def _evaluate_day_advanced(self, dt: datetime) -> bool:
        """计算 day 字段的高级语法匹配 (L / NW)。"""
        f = self.day
        if not f.last_day and f.nearest_workday_to is None:
            return True

        if f.last_day and dt.day != CalendarArithmetic.days_in_month(dt.year, dt.month):
            return False

        if f.nearest_workday_to is not None:
            expected = self._nearest_workday(dt.year, dt.month, f.nearest_workday_to)
            if dt.day != expected:
                return False

        return True

    def _evaluate_weekday_advanced(self, dt: datetime, weekday: int) -> bool:
        """计算 weekday 字段的高级语法匹配 (#N / NL)。"""
        f = self.weekday
        if not f.nth_weekdays and not f.weekday_last:
            return True

        matched = False

        # #N: 第 N 个周几
        for (target_wd, nth) in f.nth_weekdays:
            if weekday != target_wd:
                continue
            expected_day = self._nth_weekday_in_month(dt.year, dt.month, target_wd, nth or 1)
            if expected_day is not None and dt.day == expected_day:
                matched = True
                break

        # NL: 最后一个周几
        if not matched and f.weekday_last:
            for target_wd in f.weekday_last:
                if weekday != target_wd:
                    continue
                expected_day = self._last_weekday_in_month(dt.year, dt.month, target_wd)
                if dt.day == expected_day:
                    matched = True
                    break

        return matched

    def _day_weekday_match(self, dt: datetime) -> bool:
        """
        日和周几的联合匹配逻辑。

        Quartz Cron 规则（考虑高级语法 L / W / #N / NL）：
        - 如果 日/周几 存在高级语法，则必须通过高级语法检测 + 常规值匹配
        - 若 day 或 weekday 其中一个未指定（?/*），另一个指定具体值，则按指定的匹配
        - 若两者都指定了具体值（含高级语法），则 OR 匹配（任一满足即可）。
        """
        weekday = (dt.weekday() + 1) % 7

        day_has_advanced = self.day.last_day or self.day.nearest_workday_to is not None
        wd_has_advanced = bool(self.weekday.nth_weekdays or self.weekday.weekday_last)

        day_is_specific = (not self.day.any and not self.day.unspecified) or day_has_advanced
        weekday_is_specific = (not self.weekday.any and not self.weekday.unspecified) or wd_has_advanced

        # 常规值匹配
        day_match_basic = dt.day in self.day
        wd_match_basic = weekday in self.weekday

        # 高级语法匹配（不开启则视为 True，即不影响）
        day_match_adv = self._evaluate_day_advanced(dt)
        wd_match_adv = self._evaluate_weekday_advanced(dt, weekday)

        # 最终 day / weekday 匹配 = 基础 AND 高级
        day_match = day_match_basic and day_match_adv
        wd_match = wd_match_basic and wd_match_adv

        if not day_has_advanced:
            day_match = day_match_basic
        if not wd_has_advanced:
            wd_match = wd_match_basic

        if day_is_specific and weekday_is_specific:
            return day_match or wd_match
        elif day_is_specific:
            return day_match
        elif weekday_is_specific:
            return wd_match
        else:
            return day_match and wd_match

    def matches(self, dt: datetime) -> bool:
        """判断给定时间是否匹配此 Cron 表达式。"""
        month_match = dt.month in self.month
        hour_match = dt.hour in self.hour
        minute_match = dt.minute in self.minute
        second_match = dt.second in self.second

        day_weekday_match = self._day_weekday_match(dt)

        return all([
            month_match,
            hour_match,
            minute_match,
            second_match,
            day_weekday_match,
        ])

    @staticmethod
    def _advance_day(dt: datetime, days: int = 1) -> datetime:
        """安全地推进日期，自动处理跨月/跨年。"""
        return (dt + timedelta(days=days)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    @staticmethod
    def _advance_hour(dt: datetime, hours: int = 1) -> datetime:
        """安全地推进小时，自动处理跨天。"""
        result = dt + timedelta(hours=hours)
        return result.replace(minute=0, second=0, microsecond=0)

    @staticmethod
    def _advance_minute(dt: datetime, minutes: int = 1) -> datetime:
        """安全地推进分钟，自动处理跨小时/跨天。"""
        result = dt + timedelta(minutes=minutes)
        return result.replace(second=0, microsecond=0)

    def next_trigger(
        self,
        base: Optional[datetime] = None,
        max_iterations: int = 100000,
    ) -> datetime:
        """
        计算严格大于 base 的下一个触发时间点。

        核心算法："逐字段向上搜索法"（Field-by-Field Advancement）

        所有进位操作使用 timedelta，确保：
        - 23:59:30 → 下一小时 = 次日 00:00:00（不会出现 hour=24 越界）
        - 1月31日 → 下一天 = 2月1日（不会出现 day=32 越界）
        - 12月31日 → 下一月 = 次年1月1日

        步骤：
        1. 从 base + 1秒开始（保证严格大于当前时刻）
        2. 从大单位到小单位（年 -> 月 -> 日 -> 时 -> 分 -> 秒）依次检查
        3. 不匹配时：有下一个允许值就用它并清零低位；没有就用 timedelta 向上进位
        4. 所有字段匹配且日/周几条件满足时返回
        """
        if base is None:
            base = datetime.now()

        candidate = base + timedelta(seconds=1)
        candidate = candidate.replace(microsecond=0)

        iterations = 0
        while iterations < max_iterations:
            iterations += 1

            if not (candidate.month in self.month):
                next_month = self.month.next_value(candidate.month)
                if next_month is not None:
                    candidate = candidate.replace(
                        month=next_month,
                        day=1,
                        hour=0,
                        minute=0,
                        second=0,
                    )
                else:
                    candidate = candidate.replace(
                        year=candidate.year + 1,
                        month=self.month.first_value(),
                        day=1,
                        hour=0,
                        minute=0,
                        second=0,
                    )
                continue

            max_day = CalendarArithmetic.days_in_month(candidate.year, candidate.month)
            valid_days = {d for d in self.day.values if 1 <= d <= max_day}

            day_ok = self._day_weekday_match(candidate)
            if candidate.day not in valid_days:
                day_ok = False

            if not day_ok:
                candidate = self._advance_day(candidate, 1)
                continue

            if not (candidate.hour in self.hour):
                next_hour = self.hour.next_value(candidate.hour)
                if next_hour is not None:
                    candidate = candidate.replace(
                        hour=next_hour,
                        minute=0,
                        second=0,
                    )
                else:
                    candidate = self._advance_day(candidate, 1)
                    candidate = candidate.replace(hour=self.hour.first_value())
                continue

            if not (candidate.minute in self.minute):
                next_minute = self.minute.next_value(candidate.minute)
                if next_minute is not None:
                    candidate = candidate.replace(
                        minute=next_minute,
                        second=0,
                    )
                else:
                    candidate = self._advance_hour(candidate, 1)
                    candidate = candidate.replace(minute=self.minute.first_value())
                continue

            if not (candidate.second in self.second):
                next_second = self.second.next_value(candidate.second)
                if next_second is not None:
                    candidate = candidate.replace(second=next_second)
                else:
                    candidate = self._advance_minute(candidate, 1)
                    candidate = candidate.replace(second=self.second.first_value())
                continue

            return candidate

        raise RuntimeError(
            f"在 {max_iterations} 次迭代内未找到下一个触发时间，可能表达式过于严格"
        )

    def next_n_triggers(
        self,
        n: int,
        base: Optional[datetime] = None,
        max_span: Optional[timedelta] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> List[datetime]:
        """
        获取接下来 n 个触发时间。

        参数:
            n:        最多返回条数
            base:     起始基准时间（不含自身），优先级低于 start
            max_span: 最大查找跨度（如 timedelta(days=365)）。
                      超出跨度的后续触发不再计算，直接返回已找到的。
                      防止 "2月29日" 这种极稀疏规则搜索过久。
            start:    查找范围的起始时间（含，不含自身）。
                      若提供则覆盖 base。
            end:      查找范围的截止时间（不含）。
                      超出此时间的触发不会返回，且搜索立即停止。
                      适合 "列出 2024 年内的所有触发" 这类窗口查询。

        返回:
            触发时间列表，长度 <= n（当触达 max_span 或 end 时可能少于 n）
        """
        effective_base = start if start is not None else base
        if effective_base is None:
            effective_base = datetime.now()

        deadline = None
        if max_span is not None:
            deadline = effective_base + max_span
        if end is not None:
            if deadline is None or end < deadline:
                deadline = end

        result: List[datetime] = []
        current = effective_base
        for _ in range(n):
            current = self.next_trigger(current)
            if deadline is not None and current >= deadline:
                break
            result.append(current)
        return result

    def __str__(self) -> str:
        return f"CronExpression('{self.raw_expression}')"

    def __repr__(self) -> str:
        return str(self)
