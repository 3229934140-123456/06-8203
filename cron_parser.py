from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Set, Tuple

from calendar_utils import CalendarArithmetic


@dataclass
class CronField:
    """
    Cron 单个字段的解析结果。

    字段范围：
    - second (秒):     0-59
    - minute (分):     0-59
    - hour (时):       0-23
    - day (日):        1-31
    - month (月):      1-12
    - weekday (周几):  0-6 (0=周日, 或 1-7 其中7=周日)

    支持的语法：
    - *        : 匹配所有值
    - ?        : 不指定（仅日和周几字段，表示不关心）
    - N        : 具体值，如 5
    - N-M      : 范围，如 1-5
    - N,M,K    : 枚举列表，如 1,3,5
    - */N      : 步长，从最小值开始每 N 个，如 */5
    - N-M/S    : 在范围内按步长，如 10-30/5
    """

    name: str
    min_value: int
    max_value: int
    values: Set[int] = field(default_factory=set)
    any: bool = False
    unspecified: bool = False

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

        name_map = {}
        if name == "month":
            name_map = cls.MONTH_NAMES
        elif name == "weekday":
            name_map = cls.WEEKDAY_NAMES

        parts = expr.split(",")
        for part in parts:
            values.update(cls._parse_part(part, min_value, max_value, name_map))

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
                return {val}

        for v in range(start, end + 1, step):
            result.add(v)

        return result

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
        """
        result = []
        for part in token.split(","):
            dash_parts = part.split("/")
            range_expr = dash_parts[0]

            def convert_val(v: str) -> str:
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

            if "-" in range_expr:
                r_start, r_end = range_expr.split("-", 1)
                range_expr = f"{convert_val(r_start)}-{convert_val(r_end)}"
            else:
                range_expr = convert_val(range_expr)

            if len(dash_parts) > 1:
                result.append(f"{range_expr}/{dash_parts[1]}")
            else:
                result.append(range_expr)

        return ",".join(result)

    def _day_weekday_match(self, day: int, weekday: int) -> bool:
        """
        日和周几的联合匹配逻辑。

        Quartz Cron 规则：
        - 若 day 或 weekday 其中一个是 ?（unspecified）或 *（any），另一个指定具体值，
          则只需匹配那个指定具体值的（AND 逻辑的退化 - 因为另一个是全匹配）。
        - 若两者都指定了具体值（非 * 非 ?），则 OR 匹配（任一满足即可）。
        - 若两者都是 ? 或 *，则都匹配。
        """
        day_is_specific = not self.day.any and not self.day.unspecified
        weekday_is_specific = not self.weekday.any and not self.weekday.unspecified

        day_match = day in self.day
        weekday_match = weekday in self.weekday

        if day_is_specific and weekday_is_specific:
            return day_match or weekday_match
        elif day_is_specific:
            return day_match
        elif weekday_is_specific:
            return weekday_match
        else:
            return day_match and weekday_match

    def matches(self, dt: datetime) -> bool:
        """判断给定时间是否匹配此 Cron 表达式。"""
        weekday = (dt.weekday() + 1) % 7

        month_match = dt.month in self.month
        hour_match = dt.hour in self.hour
        minute_match = dt.minute in self.minute
        second_match = dt.second in self.second

        day_weekday_match = self._day_weekday_match(dt.day, weekday)

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

            weekday = (candidate.weekday() + 1) % 7

            day_ok = self._day_weekday_match(candidate.day, weekday)
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
    ) -> List[datetime]:
        """获取接下来 n 个触发时间。"""
        result = []
        current = base
        for _ in range(n):
            current = self.next_trigger(current)
            result.append(current)
        return result

    def __str__(self) -> str:
        return f"CronExpression('{self.raw_expression}')"

    def __repr__(self) -> str:
        return str(self)
