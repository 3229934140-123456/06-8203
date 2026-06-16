from __future__ import annotations

from datetime import datetime, timedelta, timezone as tz
from typing import Optional, Union

from calendar_utils import CalendarArithmetic
from duration import ISODuration
from relative_time import RelativeTimeParser
from cron_parser import CronExpression
from timezone_utils import TimezoneHandler


class TimeExpressionEngine:
    """
    时间表达式解析引擎 - 统一入口类。

    核心功能：
    1. 解析相对时间表达式（中文自然语言）
    2. 解析 Cron 风格的重复规则，计算下次触发时间
    3. 解析 ISO 8601 时间间隔
    4. 处理时区和夏令时
    """

    def __init__(self, default_timezone: Optional[str] = None):
        self.default_timezone = default_timezone

    def parse_relative_time(
        self,
        expression: str,
        base: Optional[datetime] = None,
    ) -> datetime:
        """
        解析相对时间表达式。

        参数:
            expression: 相对时间表达式，如 "3天后"、"下周一"、"明天下午3点半"
            base: 基准时间，默认为当前时间

        返回:
            计算后的 datetime

        相对时间如何在基准时间上做日历运算？
        ----------------------------------------
        核心：相对时间解析本质上是"在基准时间上应用一系列日历字段的增/减运算"。

        运算顺序（从大单位到小单位）：
        年 -> 月 -> 周 -> 日 -> 时 -> 分 -> 秒

        关键处理 - 加月份时目标月没有对应日期怎么办？
        采用"月末保留策略"（End-of-Month Preservation）：
        - 如果原日期是当月最后一天，结果调整为目标月最后一天
        - 如果原日期不是月末但目标月没有这一天（如1月31日+1月），也调整为目标月最后一天

        示例：
        - 2024-01-31 + 1个月 = 2024-02-29（闰年2月最后一天）
        - 2024-01-31 + 2个月 = 2024-03-31（3月有31天，保留）
        - 2024-03-31 - 1个月 = 2024-02-29
        - 2024-01-15 + 1个月 = 2024-02-15（15日存在，直接保留）
        """
        if base is None:
            base = self._now_with_tz()
        return RelativeTimeParser.parse(expression, base)

    def parse_iso_duration(self, text: str) -> ISODuration:
        """
        解析 ISO 8601 时间间隔表达式。

        支持格式：
        - P1Y2M3D: 1年2个月3天（日历时长）
        - PT4H5M6S: 4小时5分6秒（绝对时长）
        - P1Y2M3DT4H5M6S: 组合形式
        - P4W: 4周
        - P-1D: 负时长

        ISO 间隔如何解析成日历时长？
        ----------------------------------------
        ISO 8601 格式: P[n]Y[n]M[n]DT[n]H[n]M[n]S

        解析步骤：
        1. 验证以 'P' 开头
        2. 在 'T' 之前解析日期部分（Y年, M月, W周, D日）
        3. 在 'T' 之后解析时间部分（H时, M分, S秒）
        4. 年、月是日历单位（非固定时长）；周、日、时、分、秒是绝对单位（固定时长）

        日历运算 vs 绝对时长运算的本质区别：
        ----------------------------------------
        - 日历运算（年/月）：依赖基准日期，一个月不是固定天数
          * "加1个月"在1月31日和2月1日结果不同
          * 1月31日 + 1月 = 2月28/29日（不是3月2日或3日）
          * 需要基于具体基准日期计算

        - 绝对时长运算（日/时/分/秒）：不依赖基准日期
          * "加1天" = 加 86400 秒（固定值）
          * 但需注意：夏令时切换日，"加1个日历天"可能不等于加24小时
        """
        return ISODuration.parse(text)

    def apply_duration(
        self,
        duration: Union[ISODuration, str],
        base: Optional[datetime] = None,
    ) -> datetime:
        """将时长应用到基准时间。"""
        if base is None:
            base = self._now_with_tz()
        if isinstance(duration, str):
            duration = ISODuration.parse(duration)
        return duration.apply_to(base)

    def parse_cron(self, expression: str) -> CronExpression:
        """
        解析 Cron 表达式。

        支持格式：
        - 5字段（标准 Unix Cron）: 分 时 日 月 周几
        - 6字段（带秒）: 秒 分 时 日 月 周几

        Cron 表达式各字段如何解析并计算下一个匹配时间？
        ----------------------------------------
        字段说明（6字段格式）：
        ┌───────────── 秒 (0-59)       支持: *, N, N-M, N,M,K, */N, N-M/S
        │ ┌───────────── 分 (0-59)     支持: 同上
        │ │ ┌───────────── 时 (0-23)   支持: 同上
        │ │ │ ┌───────────── 日 (1-31) 支持: 同上 + ? (不指定)
        │ │ │ │ ┌───────────── 月 (1-12) 支持: 同上 + 月份名称 JAN-DEC
        │ │ │ │ │ ┌───────────── 周几 (0-6, 0=周日) 支持: 同上 + ? + 周几名称 SUN-SAT
        │ │ │ │ │ │
        * * * * * *

        计算下一个匹配时间（严格大于当前时刻）的算法：
        "逐字段向上搜索法"（Field-by-Field Advancement）：

        1. 从 base + 1秒 开始（保证严格大于当前）
        2. 从大单位到小单位（年 -> 月 -> 日 -> 时 -> 分 -> 秒）依次检查
        3. 对每个字段：
           a. 若当前值不在允许集合中，找到下一个允许值
           b. 若还有更大允许值，设置为该值，后面小字段设为最小值
           c. 若没有更大允许值，向更大字段进位
        4. 日和周几的特殊规则：
           - 若其中一个为 ?，两者都必须匹配（AND）
           - 若都指定了具体值，任一匹配即可（OR，Quartz 风格）
        5. 注意日的可用值取决于具体年月（2月没有30日）

        为什么要严格大于当前时刻？
        比如当前时间正好是 10:00:00，Cron 是 "0 * * * * ?"（每小时整点），
        下一次应该是 11:00:00 而不是 10:00:00（当前这个已经过去了）。
        """
        return CronExpression.parse(expression)

    def next_cron_trigger(
        self,
        cron: Union[CronExpression, str],
        base: Optional[datetime] = None,
    ) -> datetime:
        """计算 Cron 的下一个触发时间。"""
        if base is None:
            base = self._now_with_tz()
        if isinstance(cron, str):
            cron = CronExpression.parse(cron)
        return cron.next_trigger(base)

    def convert_timezone(
        self,
        dt: datetime,
        to_tz: str,
        from_tz: Optional[str] = None,
    ) -> datetime:
        """
        时区转换。

        时区换算如何进行？
        ----------------------------------------
        核心：任何时区转换都以 UTC 为中介。

        步骤：
        1. 如果源时间不带时区（naive），先用 from_tz 本地化
        2. 将源时间转换为 UTC
           UTC = 本地时间 - UTC偏移量
           例：北京时间(UTC+8) 10:00 -> UTC 02:00
        3. 从 UTC 转换为目标时区
           目标本地时间 = UTC + 目标时区的UTC偏移量
           例：UTC 02:00 -> 纽约时间(UTC-5) 21:00（前一天）

        为什么以 UTC 为中介？
        - UTC 没有夏令时，是唯一确定的时间轴
        - 直接在两个有时区的本地时间之间转换容易出错
        """
        return TimezoneHandler.convert_between_timezones(dt, from_tz, to_tz)

    def localize(
        self,
        naive_dt: datetime,
        tz_name: str,
        fold: int = 0,
        gap_strategy: str = "forward",
    ) -> datetime:
        """
        将不带时区的本地时间绑定到时区，处理夏令时问题。

        夏令时切换日如何处理不存在或重复的本地时间？
        ----------------------------------------
        夏令时有两类问题：

        1. 春季前调（Spring Forward）- 时间缺口（Gap）：
           本地时钟从 02:00 直接拨到 03:00
           导致 02:00-02:59:59 这一小时的本地时间不存在
           例：US Eastern 2024-03-10 02:30:00 不存在

           处理策略（gap_strategy 参数）：
           - 'forward': 向前跳到过渡后第一个有效时间（02:30 -> 03:00）
           - 'shift': 按 DST 偏移量平移（通常+1小时，02:30 -> 03:30）
           - 'raise': 抛出异常

        2. 秋季回拨（Fall Back）- 时间重复（Ambiguity）：
           本地时钟从 02:00 拨回 01:00
           导致 01:00-01:59:59 这一小时出现两次
           例：US Eastern 2024-11-03 01:30:00 对应两个 UTC 时间

           处理策略（fold 参数）：
           - fold=0: 取第一个实例（DST 生效前，较早的那个）
           - fold=1: 取第二个实例（DST 生效后，较晚的那个）
           两者通常相差 1 小时
        """
        return TimezoneHandler.localize(naive_dt, tz_name, fold, gap_strategy)

    def now(self, tz_name: Optional[str] = None) -> datetime:
        """获取当前时间，可选时区。"""
        if tz_name:
            return datetime.now(tz=TimezoneHandler.get_timezone(tz_name))
        if self.default_timezone:
            return datetime.now(tz=TimezoneHandler.get_timezone(self.default_timezone))
        return datetime.now()

    def _now_with_tz(self) -> datetime:
        if self.default_timezone:
            return datetime.now(tz=TimezoneHandler.get_timezone(self.default_timezone))
        return datetime.now()

    def parse(
        self,
        expression: str,
        base: Optional[datetime] = None,
    ) -> datetime:
        """
        智能解析 - 自动识别表达式类型并返回结果 datetime。

        识别顺序：
        1. Cron 表达式（包含空格，形如 "* * * * *"）
        2. ISO 8601 Duration（以 "P" 开头）
        3. 中文相对时间（其他情况）
        """
        stripped = expression.strip()

        if " " in stripped and len(stripped.split()) in (5, 6):
            first_token = stripped.split()[0]
            if (
                first_token in ("*", "?")
                or first_token[0].isdigit()
                or first_token.upper() in CronField.MONTH_NAMES
                or first_token.upper() in CronField.WEEKDAY_NAMES
                or "/" in first_token
                or "-" in first_token
                or "," in first_token
            ):
                try:
                    return self.next_cron_trigger(stripped, base)
                except ValueError:
                    pass

        if stripped.startswith("P"):
            try:
                duration = ISODuration.parse(stripped)
                return self.apply_duration(duration, base)
            except ValueError:
                pass

        return self.parse_relative_time(stripped, base)


from cron_parser import CronField
