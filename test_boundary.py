from datetime import datetime
from cron_parser import CronExpression
from timezone_utils import TimezoneHandler


def sep(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def make_cron(expr):
    return CronExpression.parse(expr)


def check(name, actual, expected):
    ok = actual == expected
    status = "✓ PASS" if ok else "✗ FAIL"
    print(f"{status}  {name}")
    print(f"         实际: {actual}")
    print(f"         期望: {expected}")
    return ok


def run_cron_boundary():
    sep("一、Cron 进位边界测试")

    # 1. 59秒进位
    t = datetime(2024, 6, 17, 10, 30, 59)
    cron = make_cron("* * * * * ?")
    check("59秒下一秒进位到下一分钟",
          cron.next_trigger(t),
          datetime(2024, 6, 17, 10, 31, 0))

    # 2. 每小时整点（59分59秒进位到下一小时整点）
    t = datetime(2024, 6, 17, 10, 59, 59)
    cron = make_cron("0 0 * * * ?")
    check("每小时整点: 10:59:59 -> 11:00:00",
          cron.next_trigger(t),
          datetime(2024, 6, 17, 11, 0, 0))

    # 3. 23:59:30 -> 次日 00:00:00（用户核心需求）
    t = datetime(2024, 6, 17, 23, 59, 30)
    cron = make_cron("0 0 * * * ?")
    check("每小时整点: 23:59:30 -> 次日 00:00:00",
          cron.next_trigger(t),
          datetime(2024, 6, 18, 0, 0, 0))

    # 4. 59分进位到下一小时
    t = datetime(2024, 6, 17, 10, 59, 30)
    cron = make_cron("0 30 * * * ?")
    check("每小时30分: 10:59:30 -> 11:30:00",
          cron.next_trigger(t),
          datetime(2024, 6, 17, 11, 30, 0))

    # 5. 23:59 跨天到次日 00:00（5字段格式）
    t = datetime(2024, 6, 17, 23, 59, 59)
    cron = make_cron("0 0 * * *")
    check("每天零点: 23:59:59 -> 次日 00:00:00",
          cron.next_trigger(t),
          datetime(2024, 6, 18, 0, 0, 0))

    # 6. 月底跨月（1月31日 -> 2月1日）
    t = datetime(2024, 1, 31, 23, 59, 59)
    cron = make_cron("0 0 0 * * ?")
    check("每天零点: 1月31日 -> 2月1日",
          cron.next_trigger(t),
          datetime(2024, 2, 1, 0, 0, 0))

    # 7. 年底跨年（12月31日 -> 次年1月1日）
    t = datetime(2024, 12, 31, 23, 59, 59)
    cron = make_cron("0 0 0 * * ?")
    check("每天零点: 12月31日 -> 次年1月1日",
          cron.next_trigger(t),
          datetime(2025, 1, 1, 0, 0, 0))

    # 8. 每周一零点（周日到周一跨周）
    t = datetime(2024, 6, 16, 23, 59, 59)  # 周日
    cron = make_cron("0 0 0 ? * MON")
    check("每周一零点: 周日23:59:59 -> 周一零点",
          cron.next_trigger(t),
          datetime(2024, 6, 17, 0, 0, 0))

    # 9. 2月28日/29日跨月（闰年）
    t = datetime(2024, 2, 29, 23, 59, 59)
    cron = make_cron("0 0 0 * * ?")
    check("闰年2月29日 -> 3月1日",
          cron.next_trigger(t),
          datetime(2024, 3, 1, 0, 0, 0))

    # 10. 每月最后一天（* / L 行为测试：用每天触发验证）
    t = datetime(2024, 4, 30, 23, 59, 59)
    cron = make_cron("0 0 0 * * ?")
    check("4月30日 -> 5月1日",
          cron.next_trigger(t),
          datetime(2024, 5, 1, 0, 0, 0))


def run_dst_boundary():
    sep("二、夏令时边界测试")

    handler = TimezoneHandler()
    NY = "America/New_York"

    try:
        # ===== Spring Forward (Gap) 2024-03-10 纽约 02:00 -> 03:00 =====

        # 1. Gap 内的时间 forward 策略 -> 跳到 03:00:00
        naive = datetime(2024, 3, 10, 2, 30, 0)
        result = handler.localize(naive, NY, gap_strategy="forward")
        check("Spring Forward gap: 02:30 forward -> 03:00:00",
              result.replace(tzinfo=None),
              datetime(2024, 3, 10, 3, 0, 0))

        # 2. Gap 内的时间 shift 策略 -> +1小时 平移到 03:30:00
        result = handler.localize(naive, NY, gap_strategy="shift")
        check("Spring Forward gap: 02:30 shift -> 03:30:00",
              result.replace(tzinfo=None),
              datetime(2024, 3, 10, 3, 30, 0))

        # 3. Gap 开始边界 02:00 forward -> 03:00
        naive = datetime(2024, 3, 10, 2, 0, 0)
        result = handler.localize(naive, NY, gap_strategy="forward")
        check("Spring Forward gap: 02:00 forward -> 03:00:00",
              result.replace(tzinfo=None),
              datetime(2024, 3, 10, 3, 0, 0))

        # 4. Gap 结束边界 02:59:59 forward -> 03:00
        naive = datetime(2024, 3, 10, 2, 59, 59)
        result = handler.localize(naive, NY, gap_strategy="forward")
        check("Spring Forward gap: 02:59:59 forward -> 03:00:00",
              result.replace(tzinfo=None),
              datetime(2024, 3, 10, 3, 0, 0))

        # 5. Gap 前时间正常本地化
        naive = datetime(2024, 3, 10, 1, 59, 59)
        result = handler.localize(naive, NY)
        check("Spring Forward gap前: 01:59:59 正常本地化",
              result.replace(tzinfo=None),
              datetime(2024, 3, 10, 1, 59, 59))

        # 6. Gap 后时间正常本地化
        naive = datetime(2024, 3, 10, 3, 0, 1)
        result = handler.localize(naive, NY)
        check("Spring Forward gap后: 03:00:01 正常本地化",
              result.replace(tzinfo=None),
              datetime(2024, 3, 10, 3, 0, 1))

        # ===== Fall Back (Ambiguity) 2024-11-03 纽约 02:00 -> 01:00 =====

        # 7. fold=0 取第一个（DST 前，较早，UTC 偏移-4）
        naive = datetime(2024, 11, 3, 1, 30, 0)
        result_fold0 = handler.localize(naive, NY, fold=0)
        check("Fall Back ambiguity: 01:30 fold=0 (DST前)",
              result_fold0.fold, 0)

        # 8. fold=1 取第二个（DST 后，较晚，UTC 偏移-5）
        result_fold1 = handler.localize(naive, NY, fold=1)
        check("Fall Back ambiguity: 01:30 fold=1 (DST后)",
              result_fold1.fold, 1)

        # 9. fold0 和 fold1 对应的 UTC 时间相差 1 小时
        utc0 = TimezoneHandler.to_utc(result_fold0)
        utc1 = TimezoneHandler.to_utc(result_fold1)
        diff_hours = (utc1 - utc0).total_seconds() / 3600
        check("Fall Back: fold0 与 fold1 UTC 相差 1 小时",
              diff_hours, 1.0)

        # 10. 模糊时间前（00:59:59）正常无歧义
        naive = datetime(2024, 11, 3, 0, 59, 59)
        is_ambig = handler._is_ambiguous_time(naive, handler.get_timezone(NY))
        check("Fall Back 前: 00:59:59 无歧义", is_ambig, False)

        # 11. 模糊时间后（02:00:01）正常无歧义
        naive = datetime(2024, 11, 3, 2, 0, 1)
        is_ambig = handler._is_ambiguous_time(naive, handler.get_timezone(NY))
        check("Fall Back 后: 02:00:01 无歧义", is_ambig, False)

    except Exception as e:
        if "time zone" in str(e).lower() or "No time zone" in str(e):
            print(f"\n  ! 时区数据库不可用（tzdata 未安装），夏令时测试跳过: {e}")
            print("    安装: pip install tzdata")
        else:
            raise


def run_summary():
    sep("测试完成")
    print("  所有边界用例已执行。如全部 PASS，说明：")
    print("    1. Cron 跨秒/分/时/日/月/年进位全部正常")
    print("    2. 夏令时 Spring Forward forward/shift 策略符合预期")
    print("    3. 夏令时 Fall Back fold=0/fold=1 模糊处理正确")


if __name__ == "__main__":
    run_cron_boundary()
    run_dst_boundary()
    run_summary()
