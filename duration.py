from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Union

from calendar_utils import CalendarArithmetic


@dataclass
class ISODuration:
    """
    ISO 8601 时间间隔（Duration）表示。

    标准格式：P[n]Y[n]M[n]DT[n]H[n]M[n]S

    说明：
    - P 是 Duration 标识（Period）
    - T 是日期和时间部分的分隔符（Time）
    - Y: 年, M(在T前): 月, D: 日
    - H: 时, M(在T后): 分, S: 秒
    - W: 周（单独使用，不与其他单位混用）

    日历时长 vs 绝对时长：
    - 年、月是日历单位（calendar-based）：1个月不是固定天数，需要基于基准日期计算
    - 周、日、时、分、秒是固定单位（absolute）：1天=24小时=86400秒

    这两者的本质区别：
    - 日历运算（年/月）：需要一个基准日期才能确定实际时长。"加1个月"在1月和2月结果不同。
    - 绝对时长（周/日/时/分/秒）：不依赖基准日期，是固定的秒数。
    """

    years: int = 0
    months: int = 0
    weeks: int = 0
    days: int = 0
    hours: int = 0
    minutes: int = 0
    seconds: Union[int, float] = 0

    _PATTERN = re.compile(
        r"^P"
        r"(?:(?P<years>-?\d+(?:\.\d+)?)Y)?"
        r"(?:(?P<months>-?\d+(?:\.\d+)?)M)?"
        r"(?:(?P<weeks>-?\d+(?:\.\d+)?)W)?"
        r"(?:(?P<days>-?\d+(?:\.\d+)?)D)?"
        r"(?:"
        r"T"
        r"(?:(?P<hours>-?\d+(?:\.\d+)?)H)?"
        r"(?:(?P<minutes>-?\d+(?:\.\d+)?)M)?"
        r"(?:(?P<seconds>-?\d+(?:\.\d+)?)S)?"
        r")?$"
    )

    _RANGE_PATTERN = re.compile(
        r"^(?P<start>.*?)/(?P<end_or_duration>.*)$"
    )

    @classmethod
    def parse(cls, text: str) -> "ISODuration":
        """
        解析 ISO 8601 Duration 字符串。

        支持的格式：
        - P1Y2M3D -> 1年2个月3天
        - PT4H5M6S -> 4小时5分钟6秒
        - P1Y2M3DT4H5M6S -> 组合
        - P4W -> 4周
        - P0.5Y -> 半年（小数部分只对绝对单位有精确定义，年月日的小数会转为整数）
        - P-1D -> 负时长

        不支持的格式（ISO 8601 允许但罕见）：
        - P0003-06-04T12:30:05  替代格式
        """
        if not text or not text.startswith("P"):
            raise ValueError(f"无效的 ISO 8601 Duration: {text}")

        match = cls._PATTERN.match(text)
        if not match:
            raise ValueError(f"无效的 ISO 8601 Duration: {text}")

        groups = match.groupdict()

        def _parse_val(key: str) -> Union[int, float]:
            val_str = groups.get(key)
            if val_str is None:
                return 0
            if "." in val_str:
                return float(val_str)
            return int(val_str)

        years = _parse_val("years")
        months = _parse_val("months")
        weeks = _parse_val("weeks")
        days = _parse_val("days")
        hours = _parse_val("hours")
        minutes = _parse_val("minutes")
        seconds = _parse_val("seconds")

        if isinstance(years, float):
            years = int(years)
        if isinstance(months, float):
            months = int(months)
        if isinstance(days, float):
            days = int(days)
        if isinstance(weeks, float):
            weeks = int(weeks)
        if isinstance(hours, float):
            hours = int(hours)
        if isinstance(minutes, float):
            minutes = int(minutes)

        if weeks and (years or months or days):
            raise ValueError(
                "ISO 8601: 周(W)不能与年(Y)/月(M)/日(D)同时使用"
            )

        if not any([years, months, weeks, days, hours, minutes, seconds]):
            if text not in ("P", "PT"):
                raise ValueError(f"无效的 ISO 8601 Duration: {text}")

        return cls(
            years=years,
            months=months,
            weeks=weeks,
            days=days,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
        )

    def to_timedelta(self, base: Optional[datetime] = None) -> timedelta:
        """
        转换为 timedelta。

        注意：年、月是日历单位，必须有基准日期才能精确转换。
        如果没有提供 base，会假设 1年=365天，1月=30天（这是粗略估计）。

        这就是日历运算和绝对时长运算的本质区别：
        - timedelta 只能表示绝对时长（固定秒数）
        - ISODuration 可以表示日历时长（年、月依赖基准日期）
        """
        if self.years or self.months:
            if base is None:
                total_days = self.days + self.weeks * 7 + self.years * 365 + self.months * 30
            else:
                result = CalendarArithmetic.add_calendar_duration(
                    base,
                    years=self.years,
                    months=self.months,
                    weeks=self.weeks,
                    days=self.days,
                )
                return (result - base) + timedelta(
                    hours=self.hours,
                    minutes=self.minutes,
                    seconds=self._seconds_as_float(),
                )
        else:
            total_days = self.days + self.weeks * 7

        return timedelta(
            days=total_days,
            hours=self.hours,
            minutes=self.minutes,
            seconds=self._seconds_as_float(),
        )

    def _seconds_as_float(self) -> float:
        if isinstance(self.seconds, int):
            return float(self.seconds)
        return self.seconds

    def apply_to(self, dt: datetime) -> datetime:
        """
        将此时长应用到给定的 datetime，返回新的 datetime。

        这是正确使用日历时长的方法：基于一个基准日期进行日历运算。

        运算顺序：年 -> 月 -> 周 -> 日 -> 时 -> 分 -> 秒
        （先处理日历单位，再处理绝对单位）
        """
        return CalendarArithmetic.add_calendar_duration(
            dt,
            years=self.years,
            months=self.months,
            weeks=self.weeks,
            days=self.days,
            hours=self.hours,
            minutes=self.minutes,
            seconds=int(self._seconds_as_float()),
        )

    def is_zero(self) -> bool:
        return not any(
            [
                self.years,
                self.months,
                self.weeks,
                self.days,
                self.hours,
                self.minutes,
                self.seconds,
            ]
        )

    def has_calendar_components(self) -> bool:
        """是否包含日历单位（年或月）。"""
        return bool(self.years or self.months)

    def has_time_components(self) -> bool:
        """是否包含时间单位（时分秒）。"""
        return bool(self.hours or self.minutes or self.seconds)

    def __str__(self) -> str:
        """序列化为 ISO 8601 格式字符串。"""
        parts = ["P"]

        if self.years:
            parts.append(f"{self.years}Y")
        if self.months:
            parts.append(f"{self.months}M")
        if self.weeks:
            parts.append(f"{self.weeks}W")
        if self.days:
            parts.append(f"{self.days}D")

        time_parts = []
        if self.hours:
            time_parts.append(f"{self.hours}H")
        if self.minutes:
            time_parts.append(f"{self.minutes}M")
        if self.seconds:
            secs = self.seconds
            if isinstance(secs, float) and secs.is_integer():
                secs = int(secs)
            time_parts.append(f"{secs}S")

        if time_parts:
            parts.append("T")
            parts.extend(time_parts)

        result = "".join(parts)
        if result == "P":
            return "PT0S"
        return result

    def __repr__(self) -> str:
        return f"ISODuration('{self}')"

    def __add__(self, other: "ISODuration") -> "ISODuration":
        if not isinstance(other, ISODuration):
            return NotImplemented
        return ISODuration(
            years=self.years + other.years,
            months=self.months + other.months,
            weeks=self.weeks + other.weeks,
            days=self.days + other.days,
            hours=self.hours + other.hours,
            minutes=self.minutes + other.minutes,
            seconds=self._seconds_as_float() + other._seconds_as_float(),
        )

    def __neg__(self) -> "ISODuration":
        return ISODuration(
            years=-self.years,
            months=-self.months,
            weeks=-self.weeks,
            days=-self.days,
            hours=-self.hours,
            minutes=-self.minutes,
            seconds=-self._seconds_as_float(),
        )

    def __sub__(self, other: "ISODuration") -> "ISODuration":
        return self + (-other)

    def __mul__(self, scalar: Union[int, float]) -> "ISODuration":
        if not isinstance(scalar, (int, float)):
            return NotImplemented
        return ISODuration(
            years=int(self.years * scalar),
            months=int(self.months * scalar),
            weeks=int(self.weeks * scalar),
            days=int(self.days * scalar),
            hours=int(self.hours * scalar),
            minutes=int(self.minutes * scalar),
            seconds=self._seconds_as_float() * scalar,
        )
