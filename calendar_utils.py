from __future__ import annotations

from datetime import datetime, timedelta, timezone as tz
from typing import Optional, Tuple


class CalendarArithmetic:
    """
    日历运算工具类。

    核心思想：
    - 日历运算（Calendar-based arithmetic）：基于日历字段（年、月、日）进行运算，
      例如"加1个月"的结果取决于当前月份的天数。1月31日加1个月不是2月31日（不存在），
      通常会调整为2月的最后一天（28日或29日）。
    - 绝对时长运算（Absolute duration arithmetic）：基于固定秒数/毫秒数进行运算，
      例如"加1天"总是加86400秒，不考虑夏令时和月份天数变化。

    两者的本质区别：日历运算是语义层面的，一个月不是固定天数；绝对时长是物理层面的。
    """

    DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    @staticmethod
    def is_leap_year(year: int) -> bool:
        """判断是否为闰年。"""
        return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)

    @classmethod
    def days_in_month(cls, year: int, month: int) -> int:
        """获取指定年月的天数。"""
        if month == 2 and cls.is_leap_year(year):
            return 29
        return cls.DAYS_IN_MONTH[month - 1]

    @staticmethod
    def normalize_year_month(year: int, month: int) -> Tuple[int, int]:
        """将年月归一化到有效范围。例如 month=13 -> year+1, month=1；month=0 -> year-1, month=12。"""
        year_offset, month = divmod(month - 1, 12)
        return year + year_offset, month + 1

    @classmethod
    def add_years(
        cls,
        dt: datetime,
        years: int,
        preserve_end_of_month: bool = True,
    ) -> datetime:
        """
        在基准时间上增加年数（日历运算）。

        处理规则：
        - 如果原日期是某月的最后一天（或因闰年导致2月29日在目标年不存在），
          则调整为目标月的最后一天。
        - 例如：2024-02-29 加1年 -> 2025-02-28（2025不是闰年）
        """
        was_last_day = (
            preserve_end_of_month
            and dt.day == cls.days_in_month(dt.year, dt.month)
        )

        new_year, new_month = cls.normalize_year_month(
            dt.year + years, dt.month
        )
        max_day = cls.days_in_month(new_year, new_month)

        if was_last_day or dt.day > max_day:
            new_day = max_day
        else:
            new_day = dt.day

        return dt.replace(year=new_year, month=new_month, day=new_day)

    @classmethod
    def add_months(
        cls,
        dt: datetime,
        months: int,
        preserve_end_of_month: bool = True,
    ) -> datetime:
        """
        在基准时间上增加月数（日历运算）。

        关键处理逻辑：当目标月没有对应日期时如何处理？
        - 策略："月末保留"（End-of-Month Preservation）
          如果原日期是某月的最后一天，或者目标月没有这一天，
          则将结果调整为目标月的最后一天。

        示例：
        - 2024-01-31 + 1个月 = 2024-02-29（闰年，2月最后一天）
        - 2024-01-31 + 2个月 = 2024-03-31（3月有31天，保留）
        - 2024-03-31 - 1个月 = 2024-02-29（闰年）
        - 2024-03-31 + 1个月 = 2024-04-30（4月只有30天）
        - 2024-01-15 + 1个月 = 2024-02-15（15日在2月存在，直接保留）
        """
        was_last_day = (
            preserve_end_of_month
            and dt.day == cls.days_in_month(dt.year, dt.month)
        )

        new_year, new_month = cls.normalize_year_month(
            dt.year, dt.month + months
        )
        max_day = cls.days_in_month(new_year, new_month)

        if was_last_day or dt.day > max_day:
            new_day = max_day
        else:
            new_day = dt.day

        return dt.replace(year=new_year, month=new_month, day=new_day)

    @classmethod
    def add_weeks(cls, dt: datetime, weeks: int) -> datetime:
        """增加周数（本质是7天的绝对时长）。"""
        return dt + timedelta(weeks=weeks)

    @classmethod
    def add_days(cls, dt: datetime, days: int) -> datetime:
        """
        增加天数。这里采用"日历天"语义：加1天 = 本地日期加1天。

        注意：在夏令时切换日，本地日期加1天不一定等于加24小时。
        例如春天时钟拨快1小时，加1天实际只加了23小时。
        这是有意为之，因为用户说"明天"通常指日历上的明天，而不是24小时后。
        """
        return cls.add_months(cls.add_years(dt, 0), 0) + timedelta(days=days)

    @classmethod
    def add_calendar_duration(
        cls,
        dt: datetime,
        years: int = 0,
        months: int = 0,
        weeks: int = 0,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
    ) -> datetime:
        """
        应用日历时长到 datetime。

        运算顺序（重要）：先处理大单位，再处理小单位。
        年 -> 月 -> 周 -> 天 -> 时 -> 分 -> 秒

        这个顺序很重要，因为：
        1月31日 + 1个月 + 1天 = 3月1日（或2月29日+1天=3月1日）
        1月31日 + 1天 + 1个月 = 3月2日（2月1日+1个月=3月1日? 不对...）

        实际上标准做法是：年、月先算（日历运算），然后天、时、分、秒（绝对时长）。
        """
        result = dt
        if years:
            result = cls.add_years(result, years)
        if months:
            result = cls.add_months(result, months)
        if weeks or days or hours or minutes or seconds:
            result = result + timedelta(
                weeks=weeks,
                days=days,
                hours=hours,
                minutes=minutes,
                seconds=seconds,
            )
        return result

    @classmethod
    def get_day_of_week(cls, dt: datetime) -> int:
        """获取星期几，0=周一 ... 6=周日（符合 ISO 8601，与 datetime.weekday() 一致）。"""
        return dt.weekday()

    @classmethod
    def next_weekday(
        cls, dt: datetime, target_weekday: int
    ) -> datetime:
        """
        获取下一个指定星期几的日期。
        target_weekday: 0=周一, 6=周日
        如果今天就是目标星期几，则返回下一周的同一天。
        """
        current_weekday = cls.get_day_of_week(dt)
        days_ahead = (target_weekday - current_weekday) % 7
        if days_ahead == 0:
            days_ahead = 7
        return (dt + timedelta(days=days_ahead)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    @classmethod
    def this_weekday(
        cls, dt: datetime, target_weekday: int
    ) -> datetime:
        """
        获取本周指定星期几的日期（本周以周一开始）。
        如果已过，则仍返回本周的那一天（过去的时间）。
        """
        current_weekday = cls.get_day_of_week(dt)
        days_offset = target_weekday - current_weekday
        return (dt + timedelta(days=days_offset)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    @classmethod
    def last_weekday(
        cls, dt: datetime, target_weekday: int
    ) -> datetime:
        """获取上一个指定星期几的日期。"""
        current_weekday = cls.get_day_of_week(dt)
        days_behind = (current_weekday - target_weekday) % 7
        if days_behind == 0:
            days_behind = 7
        return (dt - timedelta(days=days_behind)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    @classmethod
    def start_of_day(cls, dt: datetime) -> datetime:
        """获取当天的开始（00:00:00）。"""
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)

    @classmethod
    def end_of_day(cls, dt: datetime) -> datetime:
        """获取当天的结束（23:59:59.999999）。"""
        return dt.replace(hour=23, minute=59, second=59, microsecond=999999)

    @classmethod
    def start_of_month(cls, dt: datetime) -> datetime:
        """获取当月的第一天。"""
        return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    @classmethod
    def end_of_month(cls, dt: datetime) -> datetime:
        """获取当月的最后一天的结束时刻。"""
        last_day = cls.days_in_month(dt.year, dt.month)
        return dt.replace(
            day=last_day, hour=23, minute=59, second=59, microsecond=999999
        )
