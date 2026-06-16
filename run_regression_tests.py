"""
时间表达式解析引擎 - 完整回归测试
用法: python run_regression_tests.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, List, Optional, Tuple


# ============================================================
# 测试框架
# ============================================================

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
RESET = "\033[0m"


@dataclass
class Case:
    name: str
    actual: Any
    expected: Any
    compare: Optional[Callable[[Any, Any], bool]] = None

    def run(self) -> Tuple[bool, str]:
        cmp = self.compare or (lambda a, b: a == b)
        ok = cmp(self.actual, self.expected)
        detail = ""
        if not ok:
            detail = (
                f"     实际值: {RED}{self.actual}{RESET}\n"
                f"     期望值: {GREEN}{self.expected}{RESET}"
            )
        return ok, detail


@dataclass
class TestModule:
    name: str
    cases: List[Case] = field(default_factory=list)
    passed: int = 0
    failed: int = 0
    failures: List[str] = field(default_factory=list)

    def add(self, case: Case):
        self.cases.append(case)

    def run(self):
        print(f"\n{'─' * 68}")
        print(f"  {BOLD}{CYAN}模块: {self.name}{RESET}  ({len(self.cases)} 条用例)")
        print(f"{'─' * 68}")
        for idx, c in enumerate(self.cases):
            ok, detail = c.run()
            tag = f"[{idx + 1:>3}/{len(self.cases)}]"
            if ok:
                self.passed += 1
                print(f"  {GREEN}✓{RESET} {tag} {c.name}")
            else:
                self.failed += 1
                msg = f"  {RED}✗{RESET} {tag} {c.name}\n{detail}"
                print(msg)
                self.failures.append(f"[{self.name}] {c.name}\n{detail}")
        self._summary()

    def _summary(self):
        total = len(self.cases)
        if total == 0:
            return
        pct = self.passed * 100 // total
        color = GREEN if self.failed == 0 else (YELLOW if self.passed > 0 else RED)
        print(
            f"  ╰ 汇总: {color}{self.passed} 通过{RESET} / "
            f"{RED if self.failed else CYAN}{self.failed} 失败{RESET} / "
            f"{total} 总计  ({color}{pct}%{RESET})"
        )


@dataclass
class TestSuite:
    modules: List[TestModule] = field(default_factory=list)
    all_failures: List[str] = field(default_factory=list)

    def module(self, name: str) -> TestModule:
        m = TestModule(name=name)
        self.modules.append(m)
        return m

    def run(self):
        print(f"\n{'═' * 68}")
        print(f"  {BOLD}{CYAN}时间表达式解析引擎 - 回归测试{RESET}")
        print(f"{'═' * 68}")
        for m in self.modules:
            m.run()
            self.all_failures.extend(m.failures)
        self._grand_summary()

    def _grand_summary(self):
        total = sum(len(m.cases) for m in self.modules)
        passed = sum(m.passed for m in self.modules)
        failed = sum(m.failed for m in self.modules)
        pct = (passed * 100 // total) if total else 0
        print(f"\n{'═' * 68}")
        print(f"  {BOLD}总体汇总{RESET}")
        print(f"{'═' * 68}")
        for m in self.modules:
            mark = f"{GREEN}✓{RESET}" if m.failed == 0 else f"{RED}✗{RESET}"
            print(
                f"  {mark} {m.name:<22s}  "
                f"{GREEN}{m.passed:>3}✓{RESET}  "
                f"{RED}{m.failed:>3}✗{RESET}  "
                f"{CYAN}{len(m.cases):>3}{RESET}"
            )
        print(
            f"  {'─' * 66}"
        )
        print(
            f"  {BOLD}{'总计':<22s}  "
            f"{GREEN}{passed:>3}✓{RESET}  "
            f"{RED}{failed:>3}✗{RESET}  "
            f"{CYAN}{total:>3}{RESET}   "
            f"{BOLD}{GREEN if failed == 0 else RED}{pct}%{RESET}{BOLD}{RESET}"
        )
        if self.all_failures:
            print(f"\n  {RED}{BOLD}失败列表 ({len(self.all_failures)}):{RESET}")
            for i, f in enumerate(self.all_failures, 1):
                print(f"    {RED}{i}.{RESET} {f}")
        else:
            print(f"\n  {GREEN}{BOLD}🎉 全部通过！{RESET}")
        return failed == 0


# ============================================================
# 测试模块定义
# ============================================================

def build_suite() -> TestSuite:
    from calendar_utils import CalendarArithmetic
    from duration import ISODuration
    from relative_time import RelativeTimeParser
    from cron_parser import CronExpression
    from timezone_utils import (
        TimezoneHandler, LocalizeResult,
        DST_STATUS_GAP, DST_STATUS_AMBIGUOUS, DST_STATUS_NORMAL,
    )
    from engine import TimeExpressionEngine

    suite = TestSuite()

    # ========================================================
    # 模块 1: 日历运算
    # ========================================================
    m1 = suite.module("日历运算 (月末保留)")
    cal = CalendarArithmetic

    # 月末保留核心
    m1.add(Case("1月31日 +1月 = 闰年2月29日",
               cal.add_months(datetime(2024, 1, 31), 1),
               datetime(2024, 2, 29)))
    m1.add(Case("1月31日 +2月 = 3月31日",
               cal.add_months(datetime(2024, 1, 31), 2),
               datetime(2024, 3, 31)))
    m1.add(Case("平年 1月31日 +1月 = 2月28日",
               cal.add_months(datetime(2023, 1, 31), 1),
               datetime(2023, 2, 28)))
    m1.add(Case("3月31日 -1月 = 2月29日(闰年)",
               cal.add_months(datetime(2024, 3, 31), -1),
               datetime(2024, 2, 29)))
    m1.add(Case("1月15日 +1月 = 2月15日 (非月末保留)",
               cal.add_months(datetime(2024, 1, 15), 1),
               datetime(2024, 2, 15)))
    m1.add(Case("1年 + 闰年2月29日 = 平年2月28日",
               cal.add_years(datetime(2024, 2, 29), 1),
               datetime(2025, 2, 28)))
    m1.add(Case("days_in_month 闰年2月=29",
               cal.days_in_month(2024, 2), 29))
    m1.add(Case("days_in_month 平年2月=28",
               cal.days_in_month(2023, 2), 28))

    # ========================================================
    # 模块 2: ISO 8601 Duration
    # ========================================================
    m2 = suite.module("ISO 8601 Duration")
    base_dur = datetime(2024, 1, 15, 10, 30, 0)

    d = ISODuration.parse("P1Y2M3D")
    m2.add(Case("P1Y2M3D apply = 2025-03-18",
               d.apply_to(base_dur),
               datetime(2025, 3, 18, 10, 30, 0)))
    d = ISODuration.parse("PT4H5M6S")
    m2.add(Case("PT4H5M6S apply = +4:05:06",
               d.apply_to(base_dur),
               base_dur + timedelta(hours=4, minutes=5, seconds=6)))
    d = ISODuration.parse("P1Y2M3DT4H5M6S")
    m2.add(Case("P1Y2M3DT4H5M6S 组合",
               d.apply_to(base_dur),
               datetime(2025, 3, 18, 14, 35, 6)))
    d = ISODuration.parse("P4W")
    m2.add(Case("P4W = 28 天",
               d.apply_to(base_dur),
               base_dur + timedelta(days=28)))
    d = ISODuration.parse("P-1D")
    m2.add(Case("P-1D 负时长",
               d.apply_to(base_dur),
               base_dur - timedelta(days=1)))
    d = ISODuration.parse("P1M")
    m2.add(Case("P1M applied to Jan 31 = Feb 29 (月末保留)",
               d.apply_to(datetime(2024, 1, 31)),
               datetime(2024, 2, 29)))

    # ========================================================
    # 模块 3: 中文相对时间
    # ========================================================
    m3 = suite.module("中文相对时间")
    rp = RelativeTimeParser
    base_rt = datetime(2024, 6, 17, 14, 30, 0)  # 周一

    m3.add(Case("'3天后' = 6/20 同时间",
               rp.parse("3天后", base_rt),
               base_rt + timedelta(days=3)))
    m3.add(Case("'下周一中午12点'",
               rp.parse("下周一中午12点", base_rt),
               datetime(2024, 6, 24, 12, 0, 0)))
    m3.add(Case("'明天下午3点半'",
               rp.parse("明天下午3点半", base_rt),
               datetime(2024, 6, 18, 15, 30, 0)))
    m3.add(Case("'今早8点' 别名",
               rp.parse("今早8点", base_rt),
               datetime(2024, 6, 17, 8, 0, 0)))
    m3.add(Case("'昨晚8点'",
               rp.parse("昨晚8点", base_rt),
               datetime(2024, 6, 16, 20, 0, 0)))
    m3.add(Case("'下周五'",
               rp.parse("下周五", base_rt),
               datetime(2024, 6, 21)))
    m3.add(Case("'2周后'",
               rp.parse("2周后", base_rt),
               base_rt + timedelta(weeks=2)))
    m3.add(Case("'3月前'",
               rp.parse("3月前", base_rt),
               datetime(2024, 3, 17, 14, 30, 0)))

    # ========================================================
    # 模块 4: Cron 基础 & 进位
    # ========================================================
    m4 = suite.module("Cron 基础与跨单位进位")

    def cron_next(expr, base):
        return CronExpression.parse(expr).next_trigger(base)

    m4.add(Case("每小时整点: 23:59:30 → 次日 00:00:00",
               cron_next("0 0 * * * ?", datetime(2024, 6, 17, 23, 59, 30)),
               datetime(2024, 6, 18, 0, 0, 0)))
    m4.add(Case("每分钟: 10:30:59 → 10:31:00",
               cron_next("* * * * * ?", datetime(2024, 6, 17, 10, 30, 59)),
               datetime(2024, 6, 17, 10, 31, 0)))
    m4.add(Case("每小时: 10:59:59 → 11:00:00",
               cron_next("0 0 * * * ?", datetime(2024, 6, 17, 10, 59, 59)),
               datetime(2024, 6, 17, 11, 0, 0)))
    m4.add(Case("每天零点: 23:59:59 → 次日 00:00:00",
               cron_next("0 0 0 * * ?", datetime(2024, 6, 17, 23, 59, 59)),
               datetime(2024, 6, 18, 0, 0, 0)))
    m4.add(Case("月底跨月: 1/31 → 2/1",
               cron_next("0 0 0 * * ?", datetime(2024, 1, 31, 23, 59, 59)),
               datetime(2024, 2, 1, 0, 0, 0)))
    m4.add(Case("跨年: 12/31 → 次年 1/1",
               cron_next("0 0 0 * * ?", datetime(2024, 12, 31, 23, 59, 59)),
               datetime(2025, 1, 1, 0, 0, 0)))
    m4.add(Case("闰年 2/29 → 3/1",
               cron_next("0 0 0 * * ?", datetime(2024, 2, 29, 23, 59, 59)),
               datetime(2024, 3, 1, 0, 0, 0)))
    m4.add(Case("每周一零点: 周日 → 周一",
               cron_next("0 0 0 ? * MON", datetime(2024, 6, 16, 23, 59, 59)),
               datetime(2024, 6, 17, 0, 0, 0)))
    m4.add(Case("工作日早9点: 周五下午 → 下周一",
               cron_next("0 0 9 ? * MON-FRI", datetime(2024, 6, 14, 17, 0, 0)),
               datetime(2024, 6, 17, 9, 0, 0)))

    # ========================================================
    # 模块 5: Cron 高级语法 (L / W / #N / NL)
    # ========================================================
    m5 = suite.module("Cron 高级语法 (L / W / #N / NL)")

    m5.add(Case("L 月末: 6月 = 30号",
               cron_next("0 0 0 L * ?", datetime(2024, 6, 15)),
               datetime(2024, 6, 30, 0, 0, 0)))
    m5.add(Case("L 月末: 闰年2月 = 29号",
               cron_next("0 0 0 L * ?", datetime(2024, 2, 15)),
               datetime(2024, 2, 29, 0, 0, 0)))
    m5.add(Case("15W: 15号周六 → 周五 14号",
               cron_next("0 0 0 15W * ?", datetime(2024, 6, 1)),
               datetime(2024, 6, 14, 0, 0, 0)))
    m5.add(Case("16W: 16号周日 → 周一 17号",
               cron_next("0 0 0 16W * ?", datetime(2024, 6, 1)),
               datetime(2024, 6, 17, 0, 0, 0)))
    m5.add(Case("1W: 1号周六 → 周一 3号 (跨月边界)",
               cron_next("0 0 0 1W * ?", datetime(2025, 2, 1)),  # 2025-02-01 周六
               datetime(2025, 2, 3, 0, 0, 0)))
    m5.add(Case("MON#3: 6月第3个周一 = 17号",
               cron_next("0 0 0 ? * MON#3", datetime(2024, 6, 1)),
               datetime(2024, 6, 17, 0, 0, 0)))
    m5.add(Case("FRI#5: 3月第5个周五 = 29号",
               cron_next("0 0 0 ? * FRI#5", datetime(2024, 3, 1)),
               datetime(2024, 3, 29, 0, 0, 0)))
    m5.add(Case("FRI#5: 2月无第5个 → 跳到3月29",
               cron_next("0 0 0 ? * FRI#5", datetime(2024, 2, 1)),
               datetime(2024, 3, 29, 0, 0, 0)))
    m5.add(Case("MONL: 6月最后一个周一 = 24号",
               cron_next("0 0 0 ? * MONL", datetime(2024, 6, 1)),
               datetime(2024, 6, 24, 0, 0, 0)))
    m5.add(Case("4#2 (数值写法第2个周四)",
               cron_next("0 0 0 ? * 4#2", datetime(2024, 6, 1)),  # 周四=4
               datetime(2024, 6, 13, 0, 0, 0)))  # 6/6 第1个, 6/13 第2个

    # ========================================================
    # 模块 6: 时区 & 夏令时诊断
    # ========================================================
    m6 = suite.module("时区本地化 & 夏令时诊断")
    H = TimezoneHandler()
    NY = "America/New_York"

    # --- Gap forward ---
    r = H.localize_with_diagnosis(datetime(2024, 3, 10, 2, 30), NY, gap_strategy="forward")
    m6.add(Case("Gap 02:30 forward → 时间 03:00:00",
               r.datetime.replace(tzinfo=None), datetime(2024, 3, 10, 3, 0, 0)))
    m6.add(Case("Gap 02:30 → dst_status='gap'",
               r.dst_status, DST_STATUS_GAP))
    m6.add(Case("Gap 02:30 → is_missing=True",
               r.is_missing, True))
    m6.add(Case("Gap 02:30 forward → gap_applied='forward'",
               r.gap_applied, "forward"))
    m6.add(Case("Gap 02:30 forward → 调整+30分钟",
               r.adjustment_minutes, 30))

    # --- Gap shift ---
    r = H.localize_with_diagnosis(datetime(2024, 3, 10, 2, 30), NY, gap_strategy="shift")
    m6.add(Case("Gap 02:30 shift → 时间 03:30:00",
               r.datetime.replace(tzinfo=None), datetime(2024, 3, 10, 3, 30, 0)))
    m6.add(Case("Gap 02:30 shift → gap_applied='shift'",
               r.gap_applied, "shift"))
    m6.add(Case("Gap 02:30 shift → 调整+60分钟",
               r.adjustment_minutes, 60))

    # --- Gap 边界 02:00 ---
    r = H.localize_with_diagnosis(datetime(2024, 3, 10, 2, 0, 0), NY)
    m6.add(Case("Gap 02:00 forward → 03:00",
               r.datetime.replace(tzinfo=None), datetime(2024, 3, 10, 3, 0, 0)))

    # --- Ambiguity fold=0 / fold=1 ---
    r0 = H.localize_with_diagnosis(datetime(2024, 11, 3, 1, 30), NY, fold=0)
    r1 = H.localize_with_diagnosis(datetime(2024, 11, 3, 1, 30), NY, fold=1)
    m6.add(Case("Fall Back: dst_status='ambiguous'",
               r0.dst_status, DST_STATUS_AMBIGUOUS))
    m6.add(Case("Fall Back: fold=0 属性正确",
               r0.fold_used, 0))
    m6.add(Case("Fall Back: fold=1 属性正确",
               r1.fold_used, 1))
    m6.add(Case("Fall Back: fold0 / fold1 UTC 差 1 小时",
               (r1.datetime.astimezone() - r0.datetime.astimezone()).total_seconds() / 3600,
               1.0))

    # --- 正常时间 ---
    r = H.localize_with_diagnosis(datetime(2024, 6, 17, 12, 0), NY)
    m6.add(Case("Normal: dst_status='normal'",
               r.dst_status, DST_STATUS_NORMAL))
    m6.add(Case("Normal: is_missing=False",
               r.is_missing, False))
    m6.add(Case("Normal: is_ambiguous=False",
               r.is_ambiguous, False))
    m6.add(Case("Normal: 调整分钟 = 0",
               r.adjustment_minutes, 0))

    # --- 时区转换 ---
    bj = H.localize(datetime(2024, 6, 17, 18, 0, 0), "Asia/Shanghai")
    ny = H.convert_between_timezones(bj, to_tz=NY)
    m6.add(Case("北京 18:00 → 纽约 06:00 (夏令时 UTC-4)",
               ny.replace(tzinfo=None), datetime(2024, 6, 17, 6, 0, 0)))

    # ========================================================
    # 模块 7: 批量解析入口 parse_many
    # ========================================================
    m7 = suite.module("批量解析 parse_many")
    engine = TimeExpressionEngine()
    base_batch = datetime(2024, 6, 17, 10, 0, 0)

    items = [
        "3天后",
        "下周一中午12点",
        "0 0 0 L * ?",
        "P1Y2M",
        {"expr": "2024-03-10T02:30:00", "tz": NY, "gap_strategy": "forward"},
        {"expr": "* * * * * invalid !@#", "type": "cron"},
        "2024-06-17T18:00:00+08:00",
    ]
    results = engine.parse_many(items, base=base_batch, tz_name=NY)
    summary = engine.summarize(results)

    m7.add(Case("批量总数 = 7",
               summary["total"], 7))
    m7.add(Case("失败数 = 1 (故意写错 cron)",
               summary["fail"], 1))
    m7.add(Case("[0] 类型=relative_time & OK",
               (results[0].type, results[0].ok),
               ("relative_time", True)))
    m7.add(Case("[0] 3天后 = 06-20",
               results[0].result.replace(tzinfo=None),
               datetime(2024, 6, 20, 10, 0, 0)))
    m7.add(Case("[1] 下周一中午 = 06-24 12:00",
               results[1].result.replace(tzinfo=None),
               datetime(2024, 6, 24, 12, 0, 0)))
    m7.add(Case("[2] Cron L 类型=cron & OK",
               (results[2].type, results[2].ok),
               ("cron", True)))
    m7.add(Case("[2] Cron L = 6/30 零点",
               results[2].result.replace(tzinfo=None),
               datetime(2024, 6, 30, 0, 0, 0)))
    m7.add(Case("[3] ISO P1Y2M = 2025-08-17",
               results[3].result.replace(tzinfo=None),
               datetime(2025, 8, 17, 10, 0, 0)))
    m7.add(Case("[4] Gap 时间 forward → 03:00",
               results[4].result.replace(tzinfo=None),
               datetime(2024, 3, 10, 3, 0, 0)))
    m7.add(Case("[5] 非法 cron → ok=False",
               results[5].ok, False))
    m7.add(Case("[5] 非法 cron → error 非空",
               bool(results[5].error), True))
    m7.add(Case("[6] 带 Z/偏移 ISO → 类型=zoned_datetime",
               results[6].type, "zoned_datetime"))
    m7.add(Case("[6] 带偏移 ISO → OK",
               results[6].ok, True))

    return suite


def main() -> int:
    suite = build_suite()
    ok = suite.run()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
