from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional, Tuple

from calendar_utils import CalendarArithmetic


class RelativeTimeParser:
    """
    相对时间表达式解析器。

    核心原理：
    相对时间解析的本质是"在基准时间上应用一系列日历运算"。
    运算顺序遵循从大到小的原则：年 -> 月 -> 周 -> 日 -> 时 -> 分 -> 秒。

    支持的表达式类型：

    1. 偏移型：N + 单位 + 方向
       - "3天后"、"2个月前"、"1周后"、"5小时前"、"30分钟后"
       - "明年"、"下个月"、"下周"、"明天"、"后天"、"昨天"、"前天"

    2. 星期型：指示词 + 星期
       - "下周一"、"上周三"、"本周五"、"这周六"
       - "下星期一"、"下礼拜一"

    3. 月度/年度锚点：
       - "月初"、"月末"、"年底"、"下个月初"、"上月底"

    4. 时间锚点：
       - "今早8点"、"明天下午3点半"、"后天中午12点"
       - "早上"、"上午"、"中午"、"下午"、"晚上"、"凌晨"
    """

    WEEKDAY_MAP = {
        "一": 0, "1": 0, "1号": 0, "周一": 0, "礼拜一": 0, "星期一": 0,
        "二": 1, "2": 1, "2号": 1, "周二": 1, "礼拜二": 1, "星期二": 1,
        "三": 2, "3": 2, "3号": 2, "周三": 2, "礼拜三": 2, "星期三": 2,
        "四": 3, "4": 3, "4号": 3, "周四": 3, "礼拜四": 3, "星期四": 3,
        "五": 4, "5": 4, "5号": 4, "周五": 4, "礼拜五": 4, "星期五": 4,
        "六": 5, "6": 5, "6号": 5, "周六": 5, "礼拜六": 5, "星期六": 5,
        "日": 6, "天": 6, "7": 6, "周日": 6, "周天": 6, "礼拜天": 6,
        "礼拜日": 6, "星期日": 6, "星期天": 6,
    }

    TIME_PERIOD_MAP = {
        "凌晨": 0, "早上": 6, "早晨": 7, "早": 7, "上午": 9,
        "中午": 12, "午": 12, "下午": 14, "晚": 19, "晚上": 19, "傍晚": 18, "深夜": 23,
    }

    UNIT_PATTERNS = [
        ("years", ["年", "年度"]),
        ("months", ["个月", "月"]),
        ("weeks", ["周", "礼拜", "星期"]),
        ("days", ["天", "日"]),
        ("hours", ["小时", "个小时", "钟点"]),
        ("minutes", ["分钟", "分"]),
        ("seconds", ["秒", "秒钟"]),
    ]

    _SIMPLE_ALIASES = {
        "今天": lambda dt: CalendarArithmetic.start_of_day(dt),
        "今日": lambda dt: CalendarArithmetic.start_of_day(dt),
        "今": lambda dt: CalendarArithmetic.start_of_day(dt),
        "明天": lambda dt: CalendarArithmetic.start_of_day(dt + timedelta(days=1)),
        "明日": lambda dt: CalendarArithmetic.start_of_day(dt + timedelta(days=1)),
        "明": lambda dt: CalendarArithmetic.start_of_day(dt + timedelta(days=1)),
        "后天": lambda dt: CalendarArithmetic.start_of_day(dt + timedelta(days=2)),
        "大后天": lambda dt: CalendarArithmetic.start_of_day(dt + timedelta(days=3)),
        "昨天": lambda dt: CalendarArithmetic.start_of_day(dt - timedelta(days=1)),
        "昨日": lambda dt: CalendarArithmetic.start_of_day(dt - timedelta(days=1)),
        "昨": lambda dt: CalendarArithmetic.start_of_day(dt - timedelta(days=1)),
        "前天": lambda dt: CalendarArithmetic.start_of_day(dt - timedelta(days=2)),
        "大前天": lambda dt: CalendarArithmetic.start_of_day(dt - timedelta(days=3)),
        "明年": lambda dt: CalendarArithmetic.add_years(
            CalendarArithmetic.start_of_day(dt), 1
        ),
        "今年": lambda dt: dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0),
        "去年": lambda dt: CalendarArithmetic.add_years(
            CalendarArithmetic.start_of_day(dt), -1
        ).replace(month=1, day=1),
        "下个月": lambda dt: CalendarArithmetic.start_of_month(
            CalendarArithmetic.add_months(CalendarArithmetic.start_of_day(dt), 1)
        ),
        "这个月": lambda dt: CalendarArithmetic.start_of_month(dt),
        "本月": lambda dt: CalendarArithmetic.start_of_month(dt),
        "上个月": lambda dt: CalendarArithmetic.start_of_month(
            CalendarArithmetic.add_months(CalendarArithmetic.start_of_day(dt), -1)
        ),
        "下周": lambda dt: CalendarArithmetic.next_weekday(dt, 0),
        "这周": lambda dt: CalendarArithmetic.this_weekday(dt, 0),
        "本周": lambda dt: CalendarArithmetic.this_weekday(dt, 0),
        "上周": lambda dt: CalendarArithmetic.last_weekday(dt, 0),
        "月初": lambda dt: CalendarArithmetic.start_of_month(dt),
        "月底": lambda dt: CalendarArithmetic.end_of_month(dt),
        "月末": lambda dt: CalendarArithmetic.end_of_month(dt),
    }

    @classmethod
    def parse(cls, expression: str, base: Optional[datetime] = None) -> datetime:
        """
        解析相对时间表达式，返回计算后的 datetime。

        参数:
            expression: 相对时间表达式，如 "3天后"、"下周一"、"明天下午3点"
            base: 基准时间，默认为当前时间

        返回:
            计算后的 datetime

        核心运算逻辑：
        相对时间是在基准时间上做日历运算。
        日历运算 vs 绝对时长运算的区别：
        - "加1个月"：目标月没有对应日期时调整到月末（日历运算）
        - "加30天"：固定加30*86400秒（绝对时长）
        """
        if base is None:
            base = datetime.now()

        expr = expression.strip()
        if not expr:
            raise ValueError("表达式不能为空")

        result = base

        for alias, handler in cls._SIMPLE_ALIASES.items():
            if expr == alias:
                return handler(base)

        result = cls._parse_offset_expression(expr, result)
        if result != base:
            return result

        result = cls._parse_weekday_expression(expr, base)
        if result != base:
            return result

        result = cls._parse_combined_expression(expr, base)
        if result != base:
            return result

        raise ValueError(f"无法解析的相对时间表达式: {expression}")

    @classmethod
    def _parse_offset_expression(
        cls, expr: str, base: datetime
    ) -> datetime:
        """
        解析偏移型表达式：N + 单位 + 方向
        例如: "3天后", "2个月前", "5小时后"

        关键处理：月份的日历运算
        "1个月后"不是加30天，而是日历月份加1。
        当目标月没有对应日期时（如1月31日+1月），调整到目标月最后一天。
        """
        pattern = re.compile(
            r"^(?P<num>\d+)?\s*"
            r"(?P<unit>年|年度|个月|月|周|礼拜|星期|天|日|小时|个小时|钟点|分钟|分|秒|秒钟)\s*"
            r"(?P<direction>之后|以前|之前|后|前)$"
        )

        match = pattern.match(expr)
        if not match:
            return base

        num = int(match.group("num") or 1)
        unit_text = match.group("unit")
        direction = match.group("direction")

        direction_sign = 1 if direction in ("后", "之后") else -1
        amount = num * direction_sign

        unit = None
        for unit_key, unit_aliases in cls.UNIT_PATTERNS:
            if unit_text in unit_aliases:
                unit = unit_key
                break

        if unit is None:
            return base

        params = {unit: amount}

        return CalendarArithmetic.add_calendar_duration(base, **params)

    @classmethod
    def _parse_weekday_expression(
        cls, expr: str, base: datetime
    ) -> datetime:
        """
        解析星期型表达式：指示词 + 星期
        例如: "下周一", "上周三", "本周五", "下礼拜一"

        实现逻辑：
        - "下X" = 从明天开始找第一个X
        - "上X" = 从昨天开始往回找第一个X
        - "本X"/"这X" = 本周的X（可能已过，也可能在未来）
        """
        pattern = re.compile(
            r"^(?P<scope>下|上|本|这|下个|上个|这个)"
            r"(?:个|周|星期|礼拜)?"
            r"(?P<weekday>[" + "".join(set(
                k for k in cls.WEEKDAY_MAP.keys() if len(k) == 1
            )) + r"]|周一|周二|周三|周四|周五|周六|周日|周天|礼拜一|礼拜二|礼拜三|礼拜四|礼拜五|礼拜六|礼拜天|礼拜日|星期一|星期二|星期三|星期四|星期五|星期六|星期日|星期天|[1-7])$"
        )

        match = pattern.match(expr)
        if not match:
            return base

        scope = match.group("scope")
        weekday_text = match.group("weekday")

        if weekday_text not in cls.WEEKDAY_MAP:
            return base

        target_weekday = cls.WEEKDAY_MAP[weekday_text]

        if scope in ("下", "下个"):
            return CalendarArithmetic.next_weekday(base, target_weekday)
        elif scope in ("上", "上个"):
            return CalendarArithmetic.last_weekday(base, target_weekday)
        elif scope in ("本", "这", "这个"):
            return CalendarArithmetic.this_weekday(base, target_weekday)

        return base

    _WEEKDAY_BOUNDARY = set("一二三四五六日天1234567")

    @classmethod
    def _parse_combined_expression(
        cls, expr: str, base: datetime
    ) -> datetime:
        """
        解析组合表达式：日期锚点 + 时间锚点
        例如: "明天下午3点半", "今早8点", "下周一中午12点"
        """
        date_part = None
        time_part = None

        WEEKDAY_MAP = cls.WEEKDAY_MAP
        single_chars = "".join(set(
            k for k in WEEKDAY_MAP.keys() if len(k) == 1
        ))
        weekday_pattern = re.compile(
            r"^(?:下|上|本|这|下个|上个|这个)?(?:个|周|星期|礼拜)?"
            r"(?:[" + single_chars + r"]|周一|周二|周三|周四|周五|周六|周日|周天|礼拜一|礼拜二|礼拜三|礼拜四|礼拜五|礼拜六|礼拜天|礼拜日|星期一|星期二|星期三|星期四|星期五|星期六|星期日|星期天|[1-7])"
        )
        wm = weekday_pattern.match(expr)
        if wm:
            date_part = wm.group()
            time_part = expr[len(date_part):].strip()

        if not date_part:
            for alias in sorted(cls._SIMPLE_ALIASES.keys(), key=len, reverse=True):
                if not expr.startswith(alias):
                    continue
                rest = expr[len(alias):]
                if rest and rest[0] in cls._WEEKDAY_BOUNDARY:
                    continue
                date_part = alias
                time_part = rest.strip()
                break

        if date_part is None:
            offset_match = re.match(
                r"^(\d+)?\s*(年|年度|个月|月|周|礼拜|星期|天|日|小时|个小时|钟点|分钟|分|秒|秒钟)\s*(之后|以前|之前|后|前)",
                expr,
            )
            if offset_match:
                date_part = offset_match.group()
                time_part = expr[len(date_part):].strip()

        if not date_part:
            return base

        try:
            date_result = cls.parse(date_part, base)
        except ValueError:
            return base

        if not time_part:
            return date_result

        time_result = cls._parse_time_anchor(time_part, date_result)
        return time_result if time_result != date_result else date_result

    @classmethod
    def _parse_time_anchor(cls, time_expr: str, date_base: datetime) -> datetime:
        """
        解析时间锚点表达式。
        例如: "早上8点", "下午3点半", "8:30", "12点15分"
        """
        if not time_expr:
            return date_base

        result = date_base

        period = None
        for period_name in sorted(cls.TIME_PERIOD_MAP.keys(), key=len, reverse=True):
            if time_expr.startswith(period_name):
                period = period_name
                time_expr = time_expr[len(period_name):].strip()
                break

        hhmm_match = re.match(
            r"^(?P<hour>\d{1,2})[:：点时]"
            r"(?:\s*(?P<minute>\d{1,2})(?:[:：分])?)?"
            r"(?:\s*(?P<second>\d{1,2})秒?)?"
            r"(?P<half>半)?$",
            time_expr,
        )

        if hhmm_match:
            hour = int(hhmm_match.group("hour"))
            minute = int(hhmm_match.group("minute") or 0)
            second = int(hhmm_match.group("second") or 0)
            if hhmm_match.group("half"):
                minute = 30

            if period and period in cls.TIME_PERIOD_MAP:
                period_hour = cls.TIME_PERIOD_MAP[period]
                if hour < 12 and period_hour >= 12:
                    hour += 12
                elif hour > 12:
                    hour = hour

            if hour > 23 or minute > 59 or second > 59:
                return date_base

            result = result.replace(
                hour=hour, minute=minute, second=second, microsecond=0
            )
            return result

        if period and period in cls.TIME_PERIOD_MAP:
            result = result.replace(
                hour=cls.TIME_PERIOD_MAP[period],
                minute=0,
                second=0,
                microsecond=0,
            )
            return result

        return date_base
