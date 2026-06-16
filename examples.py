"""
时间表达式解析引擎 - 示例与测试代码

运行方式: python examples.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timezone as tz

from calendar_utils import CalendarArithmetic
from duration import ISODuration
from relative_time import RelativeTimeParser
from cron_parser import CronExpression
from timezone_utils import TimezoneHandler
from engine import TimeExpressionEngine


def section(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def demo_calendar_arithmetic():
    section("一、日历运算 - 加月份时目标月没有对应日期的处理")

    print("\n月末保留策略 (End-of-Month Preservation):")
    print("-" * 50)

    test_cases = [
        (datetime(2024, 1, 31), 1, "1月31日 + 1个月"),
        (datetime(2024, 1, 31), 2, "1月31日 + 2个月"),
        (datetime(2024, 3, 31), -1, "3月31日 - 1个月"),
        (datetime(2024, 3, 31), 1, "3月31日 + 1个月"),
        (datetime(2024, 1, 15), 1, "1月15日 + 1个月"),
        (datetime(2024, 2, 29), 1, "2月29日(闰年) + 1个月"),
        (datetime(2024, 2, 29), 12, "2月29日(闰年) + 1年"),
    ]

    for base, months, desc in test_cases:
        result = CalendarArithmetic.add_months(base, months)
        print(f"  {desc:30s} => {result.strftime('%Y-%m-%d')}")

    print("\n日历运算 vs 绝对时长运算:")
    print("-" * 50)

    base = datetime(2024, 1, 31)
    cal_result = CalendarArithmetic.add_months(base, 1)
    abs_result = base + __import__("datetime").timedelta(days=30)
    print(f"  基准时间: {base.strftime('%Y-%m-%d')}")
    print(f"  日历运算 +1个月:  {cal_result.strftime('%Y-%m-%d')} (2月最后一天)")
    print(f"  绝对时长 +30天:   {abs_result.strftime('%Y-%m-%d')} (固定加30天)")
    print(f"  差异: 一个月不是固定天数 = 日历运算依赖基准日期")


def demo_iso_duration():
    section("二、ISO 8601 时间间隔解析 (P1Y2M3D 格式)")

    print("\n解析各种 ISO 8601 Duration:")
    print("-" * 50)

    durations = [
        "P1Y2M3D",
        "PT4H5M6S",
        "P1Y2M3DT4H5M6S",
        "P4W",
        "P-1D",
        "PT0.5S",
    ]

    for dur_str in durations:
        dur = ISODuration.parse(dur_str)
        print(f"  {dur_str:20s} => {dur} "
              f"(年={dur.years}, 月={dur.months}, 周={dur.weeks}, "
              f"日={dur.days}, 时={dur.hours}, 分={dur.minutes}, 秒={dur.seconds})")

    print("\n日历时长应用到具体日期:")
    print("-" * 50)

    dur = ISODuration.parse("P1M")
    for base_str in ["2024-01-31", "2024-02-15", "2024-03-31"]:
        base = datetime.strptime(base_str, "%Y-%m-%d")
        result = dur.apply_to(base)
        td = dur.to_timedelta(base)
        print(f"  {base_str} + P1M = {result.strftime('%Y-%m-%d')} "
              f"(实际时长: {td.total_seconds() / 86400:.1f} 天)")

    print("\n  = 同一个 P1M 应用到不同基准日期，实际天数不同")
    print("  = 这就是日历运算与绝对时长运算的本质区别")


def demo_relative_time():
    section("三、相对时间解析 (3天后 / 下周一 / 明天下午3点半)")

    base = datetime(2024, 6, 17, 10, 30, 0)
    print(f"\n基准时间: {base.strftime('%Y-%m-%d %H:%M:%S %A')}")
    print("-" * 50)

    expressions = [
        "今天",
        "明天",
        "后天",
        "昨天",
        "3天后",
        "2个月前",
        "明年",
        "下个月",
        "下周一",
        "下周三",
        "上周五",
        "本周五",
        "月初",
        "月底",
        "明天下午3点半",
        "今早8点",
        "下周一中午12点",
        "3小时后",
        "30分钟前",
    ]

    for expr in expressions:
        try:
            result = RelativeTimeParser.parse(expr, base)
            print(f"  {expr:15s} => {result.strftime('%Y-%m-%d %H:%M:%S %A')}")
        except ValueError as e:
            print(f"  {expr:15s} => 错误: {e}")


def demo_cron():
    section("四、Cron 表达式解析与下次触发时间计算")

    print("\nCron 各字段解析:")
    print("-" * 50)

    cron_samples = [
        ("0 0 12 * * ?", "每天中午12点"),
        ("0 */5 * * * ?", "每5分钟"),
        ("0 0 0 1 * ?", "每月1号零点"),
        ("0 0 9 ? * MON-FRI", "工作日早上9点"),
        ("30 5 15 * * ?", "每天15:05:30"),
        ("0 0 0 L * ?", "每月最后一天 (简化演示)"),
    ]

    for cron_str, desc in cron_samples:
        try:
            cron = CronExpression.parse(cron_str)
            print(f"  {cron_str:25s} ({desc})")
        except ValueError as e:
            print(f"  {cron_str:25s} ({desc}) => 解析失败: {e}")

    print("\n计算下一个触发时间 (严格大于基准):")
    print("-" * 50)

    base = datetime(2024, 6, 17, 10, 30, 45)
    print(f"基准时间: {base.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    test_cases = [
        ("0 0 * * * ?", "每小时整点"),
        ("0 */15 * * * ?", "每15分钟"),
        ("0 0 12 * * ?", "每天中午12点"),
        ("0 0 0 * * MON", "每周一零点"),
        ("0 30 9 ? * 1-5", "工作日9:30"),
    ]

    for cron_str, desc in test_cases:
        try:
            cron = CronExpression.parse(cron_str)
            next_time = cron.next_trigger(base)
            next_5 = cron.next_n_triggers(3, base)
            print(f"  {desc:15s} [{cron_str}]")
            print(f"    下一次:  {next_time.strftime('%Y-%m-%d %H:%M:%S %A')}")
            print(f"    随后3次: {[t.strftime('%m-%d %H:%M') for t in next_5]}")
        except Exception as e:
            print(f"  {desc:15s} [{cron_str}] => 错误: {e}")


def demo_timezone():
    section("五、时区与夏令时处理")

    handler = TimezoneHandler()

    print("\n1. 时区转换 (以 UTC 为中介):")
    print("-" * 50)

    shanghai = ZoneInfo("Asia/Shanghai")
    beijing_time = datetime(2024, 6, 17, 18, 0, 0, tzinfo=shanghai)
    ny_time = handler.convert_between_timezones(beijing_time, to_tz="America/New_York")
    utc_time = handler.to_utc(beijing_time)

    print(f"  北京时间: {beijing_time.strftime('%Y-%m-%d %H:%M:%S %Z')} (UTC+8)")
    print(f"  UTC时间:  {utc_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"  纽约时间: {ny_time.strftime('%Y-%m-%d %H:%M:%S %Z')} (UTC-4)")

    print("\n2. 夏令时 - 时间缺口 (Spring Forward Gap):")
    print("-" * 50)
    print("  US Eastern 2024-03-10: 02:00 拨到 03:00，02:30 不存在")

    try:
        missing_time = datetime(2024, 3, 10, 2, 30, 0)
        result_forward = handler.localize(
            missing_time, "America/New_York", gap_strategy="forward"
        )
        result_shift = handler.localize(
            missing_time, "America/New_York", gap_strategy="shift"
        )
        print(f"  本地时间 02:30 (不存在):")
        print(f"    forward策略: {result_forward.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"    shift策略:   {result_shift.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    except Exception as e:
        print(f"  错误: {e}")

    print("\n3. 夏令时 - 时间重复 (Fall Back Ambiguity):")
    print("-" * 50)
    print("  US Eastern 2024-11-03: 02:00 拨回 01:00，01:30 出现两次")

    try:
        ambiguous_time = datetime(2024, 11, 3, 1, 30, 0)
        result_first = handler.localize(
            ambiguous_time, "America/New_York", fold=0
        )
        result_second = handler.localize(
            ambiguous_time, "America/New_York", fold=1
        )
        print(f"  本地时间 01:30 (重复出现):")
        print(f"    fold=0 (第一个, DST前): {result_first.strftime('%Y-%m-%d %H:%M:%S %Z')} => UTC: {handler.to_utc(result_first).strftime('%H:%M')}")
        print(f"    fold=1 (第二个, DST后): {result_second.strftime('%Y-%m-%d %H:%M:%S %Z')} => UTC: {handler.to_utc(result_second).strftime('%H:%M')}")
        print(f"    两者相差 1 小时 (DST 偏移量)")
    except Exception as e:
        print(f"  错误: {e}")


def demo_engine():
    section("六、统一引擎 - TimeExpressionEngine 智能解析")

    engine = TimeExpressionEngine(default_timezone="Asia/Shanghai")

    print("\n智能识别表达式类型:")
    print("-" * 50)

    base = datetime(2024, 6, 17, 10, 30, 0)
    print(f"基准时间: {base.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    test_expressions = [
        ("3天后", "相对时间"),
        ("下周一", "相对时间"),
        ("明天下午3点半", "相对时间"),
        ("P1Y2M", "ISO Duration"),
        ("PT4H", "ISO Duration"),
        ("0 */5 * * * ?", "Cron 每5分钟"),
        ("0 0 12 * * ?", "Cron 每天中午12点"),
    ]

    for expr, expr_type in test_expressions:
        try:
            result = engine.parse(expr, base)
            print(f"  [{expr_type:12s}] {expr:20s} => {result.strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as e:
            print(f"  [{expr_type:12s}] {expr:20s} => 错误: {e}")


def demo_concept_explanation():
    section("七、核心概念总结")

    print("""
  1. 日历运算 vs 绝对时长运算
     ------------------------------------
     日历运算 (年/月): 依赖基准日期
       - 1月31日 + 1个月 = 2月28/29日
       - 3月31日 + 1个月 = 4月30日
       = 一个月不是固定天数

     绝对时长 (日/时/分/秒): 不依赖基准日期
       - +1天 = 固定加 86400 秒
       - 但需注意夏令时: "加1个日历天" 可能是23或25小时

  2. Cron 下一个触发时间算法
     ------------------------------------
     "逐字段向上搜索法" (从大到小):
     年 -> 月 -> 日/周几 -> 时 -> 分 -> 秒
     - 从 base+1秒 开始 (保证严格大于当前)
     - 每字段不匹配时找下一个允许值
     - 没有更大值时向高位进位
     - 日和周几: 一个是?时AND, 都指定时OR

  3. 夏令时处理
     ------------------------------------
     Gap (春季前调): 时间不存在
       - forward: 跳到过渡后第一个有效时间
       - shift: 按DST偏移量平移 (通常+1h)
       - raise: 抛异常

     Ambiguity (秋季回拨): 时间重复
       - fold=0: 取第一个 (DST前, 较早)
       - fold=1: 取第二个 (DST后, 较晚)

  4. 时区换算
     ------------------------------------
     始终以 UTC 为中介:
       本地时间 -> (减UTC偏移) -> UTC -> (加目标UTC偏移) -> 目标时间
     避免直接在两个本地时区之间转换。
""")


def demo_cron_advanced():
    """Cron 高级语法演示：L / W / #N / NL"""
    section("六、Cron 高级语法（月末/工作日/第N个周几）")
    NY = "America/New_York"
    base = datetime(2024, 6, 1, 0, 0, 0)

    cases = [
        ("0 0 0 L * ?",          "每月最后一天零点"),
        ("0 0 12 L * ?",         "每月最后一天中午12点"),
        ("0 30 9 15W * ?",       "最接近15号的工作日上午9:30"),
        ("0 0 9 1W * ?",         "每月最接近1号的工作日早9点"),
        ("0 0 0 ? * MON#3",      "每月第3个周一零点"),
        ("0 0 10 ? * FRI#5",     "每月第5个周五上午10点 (若当月有)"),
        ("0 0 0 ? * MONL",       "每月最后一个周一零点"),
        ("0 0 0 ? * FRIL",       "每月最后一个周五零点"),
    ]
    for expr, desc in cases:
        try:
            next_t = CronExpression.parse(expr).next_trigger(base)
            print(f"  {desc:<30s}  [{expr:<22s}]  =>  {next_t.strftime('%Y-%m-%d %A %H:%M:%S')}")
        except Exception as e:
            print(f"  {desc:<30s}  [{expr:<22s}]  =>  ERROR: {e}")


def demo_timezone_diagnosis():
    """时区本地化 + DST 完整诊断输出"""
    section("七、时区本地化 + 夏令时诊断")
    NY = "America/New_York"
    H = TimezoneHandler()
    cases = [
        (datetime(2024, 3, 10, 1, 59, 59), 0, "forward", "DST 切换前 1ms"),
        (datetime(2024, 3, 10, 2, 0, 0),    0, "forward", "DST gap 起始"),
        (datetime(2024, 3, 10, 2, 30, 0),   0, "forward", "DST gap 中间 forward"),
        (datetime(2024, 3, 10, 2, 30, 0),   0, "shift",   "DST gap 中间 shift"),
        (datetime(2024, 3, 10, 2, 59, 59),  0, "forward", "DST gap 结束前"),
        (datetime(2024, 3, 10, 3, 0, 1),    0, "forward", "DST gap 之后"),
        (datetime(2024, 11, 3, 0, 59, 59),  0, "forward", "Fall Back 前"),
        (datetime(2024, 11, 3, 1, 30, 0),   0, "forward", "Fall Back ambiguous fold=0"),
        (datetime(2024, 11, 3, 1, 30, 0),   1, "forward", "Fall Back ambiguous fold=1"),
        (datetime(2024, 11, 3, 2, 0, 1),    0, "forward", "Fall Back 之后"),
    ]
    print(f"  {'场景说明':<28s} {'原始时间':<20s} => 结果时间       dst_status   gap/fold    调整  is_dst")
    print(f"  {'-' * 108}")
    for naive, fold, strat, desc in cases:
        try:
            r = H.localize_with_diagnosis(naive, NY, fold=fold, gap_strategy=strat)
            line = (
                f"  {desc:<28s} "
                f"{r.original_local.strftime('%m-%d %H:%M:%S'):<20s} "
                f"=> {r.datetime.strftime('%m-%d %H:%M:%S%z'):<22s} "
                f"{r.dst_status:<12s} "
                f"{(r.gap_applied or (f'fold={r.fold_used}' if r.fold_used is not None else '—')):<11s} "
                f"{r.adjustment_minutes:+3d}分 "
                f"{r.meta.get('is_dst')}"
            )
            print(line)
        except Exception as e:
            print(f"  {desc:<28s} ERROR: {e}")


def demo_batch_parse():
    """批量解析入口 parse_many 演示"""
    section("八、批量解析入口 parse_many (统一集成入口)")
    NY = "America/New_York"
    engine = TimeExpressionEngine()
    base = datetime(2024, 6, 17, 12, 0, 0)

    expressions = [
        "3天后",
        "下周一中午12点",
        "0 0 0 L * ?",
        "0 0 9 15W * ?",
        "0 0 0 ? * MON#3",
        "P1Y2M3D",
        "P-1D",
        {"expr": "2024-03-10T02:30:00", "tz": NY, "gap_strategy": "forward",
         "type": "iso_datetime"},
        {"expr": "2024-03-10T02:30:00", "tz": NY, "gap_strategy": "shift",
         "type": "iso_datetime"},
        "2024-06-17T18:00:00+08:00",
        {"expr": "0 0 * * * invalid!!!", "type": "cron"},
    ]
    results = engine.parse_many(expressions, base=base, tz_name=NY)
    summary = engine.summarize(results)

    print(f"  共 {summary['total']} 条  "
          f"{summary['ok']} PASS,  {summary['fail']} FAIL")
    print()
    for i, r in enumerate(results):
        flag = "[OK]" if r.ok else "[FAIL]"
        extra = ""
        if r.error:
            extra = f"  err={r.error[:50]}"
        if r.type == "iso_datetime" and r.ok:
            extra = f"  本地化后={r.result.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        if r.type == "cron" and r.ok:
            extra = f"  下次触发={r.result.strftime('%Y-%m-%d %H:%M:%S')}"
        print(
            f"  [{i:>2}] {flag}  "
            f"type={r.type:<16s}  "
            f"raw={r.raw:<35s}"
            f"{extra}"
        )
    print()
    print("  按类型汇总:")
    for t, s in summary["by_type"].items():
        print(f"    - {t:<20s}  {s['ok']}OK / {s['fail']}FAIL / {s['total']}")


def main():
    print("\n" + "#" * 70)
    print("#" + " " * 68 + "#")
    print("#" + "时间表达式解析引擎 - 完整演示".center(68) + "#")
    print("#" + " " * 68 + "#")
    print("#" * 70)

    try:
        demo_calendar_arithmetic()
    except Exception as e:
        print(f"日历运算演示出错: {e}")

    try:
        demo_iso_duration()
    except Exception as e:
        print(f"ISO Duration 演示出错: {e}")

    try:
        demo_relative_time()
    except Exception as e:
        print(f"相对时间演示出错: {e}")

    try:
        demo_cron()
    except Exception as e:
        print(f"Cron 演示出错: {e}")

    try:
        demo_timezone()
    except Exception as e:
        print(f"时区演示出错: {e}")

    try:
        demo_engine()
    except Exception as e:
        print(f"统一引擎演示出错: {e}")

    try:
        demo_cron_advanced()
    except Exception as e:
        print(f"Cron 高级语法演示出错: {e}")

    try:
        demo_timezone_diagnosis()
    except Exception as e:
        print(f"时区诊断演示出错: {e}")

    try:
        demo_batch_parse()
    except Exception as e:
        print(f"批量解析演示出错: {e}")

    demo_concept_explanation()


if __name__ == "__main__":
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo
    main()
