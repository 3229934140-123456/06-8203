from __future__ import annotations

from datetime import datetime, timedelta, timezone as tz
from typing import Optional, Union

try:
    from zoneinfo import ZoneInfo, available_timezones
    HAS_ZONEINFO = True
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo, available_timezones
        HAS_ZONEINFO = True
    except ImportError:
        HAS_ZONEINFO = False
        ZoneInfo = None
        available_timezones = None


class TimezoneHandler:
    """
    时区和夏令时处理器。

    核心概念：
    1. 本地时间 (naive datetime)：不带时区信息的时间，可能因夏令时而模糊或不存在。
    2. UTC 时间 (aware datetime with UTC)：全球统一的时间，不会有歧义。
    3. 时区感知时间 (aware datetime with tz)：带时区的本地时间。

    夏令时问题：
    - 春季前调（Spring Forward）：某一天凌晨2点拨到3点，导致2:00-2:59:59这一小时的本地时间不存在。
      例如 US Eastern Time 2024-03-10 02:30:00 不存在。
    - 秋季回拨（Fall Back）：某一天凌晨2点拨回1点，导致1:00-1:59:59这一小时的本地时间出现两次。
      例如 US Eastern Time 2024-11-03 01:30:00 对应两个 UTC 时间。

    处理策略：
    - 不存在的时间（Spring Forward gap）：向前调整到过渡后的第一个有效时间。
      例如 02:30 -> 03:00（或按偏移量调整到 03:30，取决于策略）。
    - 重复的时间（Fall Back ambiguity）：默认取第一个（DST 生效前，即"较早"的那个）。
      可以通过参数选择取第二个。
    """

    FOLD_FIRST = 0
    FOLD_SECOND = 1

    def __init__(self):
        if not HAS_ZONEINFO:
            raise RuntimeError(
                "zoneinfo 模块不可用，请安装 backports.zoneinfo 或使用 Python 3.9+"
            )

    @staticmethod
    def get_timezone(tz_name: str) -> "ZoneInfo":
        """获取时区对象。"""
        if not HAS_ZONEINFO:
            raise RuntimeError("zoneinfo 模块不可用")
        return ZoneInfo(tz_name)

    @staticmethod
    def list_timezones() -> list:
        """列出所有可用时区。"""
        if not HAS_ZONEINFO:
            return []
        return sorted(available_timezones())

    @staticmethod
    def to_utc(dt: datetime) -> datetime:
        """
        将任意时区感知时间转换为 UTC。

        时区换算的核心：
        UTC = 本地时间 - UTC偏移量
        例如：北京时间(UTC+8) 10:00 -> UTC 02:00
        """
        if dt.tzinfo is None:
            raise ValueError("必须提供带时区的 datetime")
        return dt.astimezone(tz.utc)

    @staticmethod
    def from_utc(utc_dt: datetime, target_tz: Union[str, "ZoneInfo"]) -> datetime:
        """
        将 UTC 时间转换为目标时区的本地时间。

        时区换算的核心：
        本地时间 = UTC + UTC偏移量
        这个方向通常没有问题，因为 UTC 是唯一的。
        """
        if utc_dt.tzinfo is None:
            utc_dt = utc_dt.replace(tzinfo=tz.utc)
        if isinstance(target_tz, str):
            target_tz = ZoneInfo(target_tz)
        return utc_dt.astimezone(target_tz)

    @classmethod
    def localize(
        cls,
        naive_dt: datetime,
        tz_name: str,
        fold: int = FOLD_FIRST,
        gap_strategy: str = "forward",
    ) -> datetime:
        """
        将不带时区的本地时间"绑定"到指定时区，处理夏令时问题。

        参数：
        - naive_dt: 本地时间（不带时区）
        - tz_name: 时区名称，如 'Asia/Shanghai', 'America/New_York'
        - fold: 当时间重复时（秋季回拨），取第几个：0=第一个（较早，DST前），1=第二个（较晚，DST后）
        - gap_strategy: 当时间不存在时（春季前调）的处理策略：
            * 'forward': 向前跳到过渡后第一个有效时间
            * 'shift': 按 DST 偏移量向后移动（通常+1小时）
            * 'raise': 抛出异常

        实现原理：
        Python 3.9+ 的 zoneinfo 模块通过 fold 属性处理模糊时间。
        - fold=0 表示取第一个实例（DST 切换前）
        - fold=1 表示取第二个实例（DST 切换后）

        对于不存在的时间（gap），Python 的 fromisoformat 和 replace 不会自动报错，
        但我们可以通过检查 UTC 偏移量是否一致来检测。
        """
        if naive_dt.tzinfo is not None:
            raise ValueError("naive_dt 必须是不带时区的 datetime")

        tz_obj = ZoneInfo(tz_name)

        aware_dt = naive_dt.replace(fold=fold, tzinfo=tz_obj)

        if cls._is_missing_time(naive_dt, tz_obj):
            if gap_strategy == "raise":
                raise ValueError(
                    f"时间 {naive_dt} 在时区 {tz_name} 中不存在（夏令时前调）"
                )
            elif gap_strategy == "shift":
                utc_offset_before = cls._get_utc_offset_before_gap(naive_dt, tz_obj)
                utc_offset_after = cls._get_utc_offset_after_gap(naive_dt, tz_obj)
                shift = utc_offset_after - utc_offset_before
                aware_dt = (naive_dt + shift).replace(tzinfo=tz_obj)
            else:
                aware_dt = cls._get_gap_end_time(naive_dt, tz_obj)

        return aware_dt

    @classmethod
    def _is_missing_time(cls, naive_dt: datetime, tz_obj) -> bool:
        """检测一个本地时间是否在 DST gap 中（不存在的时间）。"""
        dt0 = naive_dt.replace(fold=0, tzinfo=tz_obj)
        dt1 = naive_dt.replace(fold=1, tzinfo=tz_obj)

        utc0 = dt0.astimezone(tz.utc)
        utc1 = dt1.astimezone(tz.utc)

        wall0 = utc0.astimezone(tz_obj).replace(tzinfo=None)
        wall1 = utc1.astimezone(tz_obj).replace(tzinfo=None)

        if wall0 == wall1 and wall0 != naive_dt:
            return True

        if utc0 == utc1:
            return False

        delta = abs((utc1 - utc0).total_seconds())
        return delta > 0 and wall0 != naive_dt

    @classmethod
    def _is_ambiguous_time(cls, naive_dt: datetime, tz_obj) -> bool:
        """检测一个本地时间是否模糊（重复出现）。"""
        dt0 = naive_dt.replace(fold=0, tzinfo=tz_obj)
        dt1 = naive_dt.replace(fold=1, tzinfo=tz_obj)
        return dt0.astimezone(tz.utc) != dt1.astimezone(tz.utc)

    @staticmethod
    def _get_utc_offset_before_gap(naive_dt: datetime, tz_obj) -> timedelta:
        year_start = datetime(naive_dt.year, 1, 1, tzinfo=tz_obj)
        return year_start.utcoffset() or timedelta(0)

    @staticmethod
    def _get_utc_offset_after_gap(naive_dt: datetime, tz_obj) -> timedelta:
        mid_year = datetime(naive_dt.year, 7, 1, tzinfo=tz_obj)
        return mid_year.utcoffset() or timedelta(0)

    @classmethod
    def _get_gap_end_time(cls, naive_dt: datetime, tz_obj) -> datetime:
        """
        获取 DST gap 结束后的第一个有效本地时间。

        实现原理（检测跳变法）：
        1. 从 naive_dt 当天 00:00 开始，以 UTC 每分钟递增
        2. 记录前一个 UTC 对应的本地时间 prev_local
        3. 当 (current_local - prev_local) > 1 分钟时，发生了 Spring Forward 跳变
        4. current_local 就是 gap 后的第一个有效本地时间

        例：纽约 2024-03-10 02:30
        - UTC 06:59 → 本地 01:59 (DST前, UTC-5)
        - UTC 07:00 → 本地 03:00 (DST后, UTC-4)
        - 差 61 分钟 > 1 分钟，跳变！返回 03:00
        """
        day_start = naive_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_tz = day_start.replace(fold=0, tzinfo=tz_obj)
        utc_cursor = day_start_tz.astimezone(tz.utc)

        prev_local = None
        for _ in range(1440):
            local_cursor = utc_cursor.astimezone(tz_obj)
            local_naive = local_cursor.replace(tzinfo=None)

            if prev_local is not None:
                diff_minutes = (local_naive - prev_local).total_seconds() / 60
                if diff_minutes > 1.5:
                    if local_naive >= naive_dt or (
                        naive_dt >= prev_local and naive_dt < local_naive
                    ):
                        return local_naive.replace(tzinfo=tz_obj).replace(
                            second=0, microsecond=0
                        )

            prev_local = local_naive
            utc_cursor += timedelta(minutes=1)

        return naive_dt.replace(tzinfo=tz_obj)

    @classmethod
    def convert_between_timezones(
        cls,
        dt: datetime,
        from_tz: Optional[str] = None,
        to_tz: str = "UTC",
    ) -> datetime:
        """
        在两个时区之间转换时间。

        步骤：
        1. 如果源时间不带时区，先用 from_tz 本地化它
        2. 转换为 UTC（中间步骤，避免直接转换的复杂性）
        3. 从 UTC 转换到目标时区

        这是处理时区转换最稳健的方法：始终以 UTC 为中介。
        """
        if dt.tzinfo is None:
            if from_tz is None:
                raise ValueError("naive datetime 需要指定 from_tz")
            dt = cls.localize(dt, from_tz)

        utc_dt = dt.astimezone(tz.utc)
        target_tz_obj = ZoneInfo(to_tz)
        return utc_dt.astimezone(target_tz_obj)

    @staticmethod
    def get_utc_offset(dt: datetime) -> timedelta:
        """获取某个时刻相对于 UTC 的偏移量。"""
        if dt.tzinfo is None:
            raise ValueError("必须提供带时区的 datetime")
        offset = dt.utcoffset()
        return offset or timedelta(0)

    @staticmethod
    def is_dst(dt: datetime) -> bool:
        """判断某个时刻是否处于夏令时。"""
        if dt.tzinfo is None:
            raise ValueError("必须提供带时区的 datetime")
        dst = dt.dst()
        return dst is not None and dst.total_seconds() != 0
