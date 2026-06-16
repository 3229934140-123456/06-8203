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

SYM_OK = "[PASS]"
SYM_FAIL = "[FAIL]"
SYM_LINE = "-"
SYM_DOUBLE = "="


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
                f"     ACTUAL:   {self.actual}\n"
                f"     EXPECTED: {self.expected}"
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
        print(f"\n{SYM_LINE * 68}")
        print(f"  模块: {self.name}  ({len(self.cases)} 条用例)")
        print(f"{SYM_LINE * 68}")
        for idx, c in enumerate(self.cases):
            ok, detail = c.run()
            tag = f"[{idx + 1:>3}/{len(self.cases)}]"
            if ok:
                self.passed += 1
                print(f"  {SYM_OK} {tag} {c.name}")
            else:
                self.failed += 1
                msg = f"  {SYM_FAIL} {tag} {c.name}\n{detail}"
                print(msg)
                self.failures.append(f"[{self.name}] {c.name}\n{detail}")
        self._summary()

    def _summary(self):
        total = len(self.cases)
        if total == 0:
            return
        pct = self.passed * 100 // total
        mark = "OK" if self.failed == 0 else "WARN"
        print(
            f"  >> 汇总: [{mark}] {self.passed} 通过 / "
            f"{self.failed} 失败 / "
            f"{total} 总计  ({pct}%)"
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
        print(f"\n{SYM_DOUBLE * 68}")
        print(f"  时间表达式解析引擎 - 回归测试")
        print(f"{SYM_DOUBLE * 68}")
        for m in self.modules:
            m.run()
            self.all_failures.extend(m.failures)
        self._grand_summary()

    def _grand_summary(self):
        total = sum(len(m.cases) for m in self.modules)
        passed = sum(m.passed for m in self.modules)
        failed = sum(m.failed for m in self.modules)
        pct = (passed * 100 // total) if total else 0
        print(f"\n{SYM_DOUBLE * 68}")
        print(f"  总体汇总")
        print(f"{SYM_DOUBLE * 68}")
        for m in self.modules:
            mark = SYM_OK if m.failed == 0 else SYM_FAIL
            print(
                f"  {mark} {m.name:<22s}  "
                f"{m.passed:>3}OK  "
                f"{m.failed:>3}FAIL  "
                f"{len(m.cases):>3}"
            )
        print(
            f"  {SYM_LINE * 66}"
        )
        overall_mark = "OK" if failed == 0 else "FAIL"
        print(
            f"  [{overall_mark}] {'总计':<20s}  "
            f"{passed:>3}OK  "
            f"{failed:>3}FAIL  "
            f"{total:>3}   {pct}%"
        )
        if self.all_failures:
            print(f"\n  失败列表 ({len(self.all_failures)}):")
            for i, f in enumerate(self.all_failures, 1):
                print(f"    {i}. {f}")
        else:
            print(f"\n  ALL PASSED!")
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
    m7.add(Case("[6] 带偏移 ISO -> OK",
               results[6].ok, True))

    # ========================================================
    # 模块 8: DST 诊断字段 & JSON 序列化
    # ========================================================
    m8 = suite.module("DST 诊断字段 & JSON 序列化")

    # Gap 场景：2024-03-10 02:30 forward
    gap_items = [
        {"expr": "2024-03-10T02:30:00", "tz": NY, "gap_strategy": "forward",
         "type": "iso_datetime"},
    ]
    gap_res = engine.parse_many(gap_items, base=base_batch, tz_name=NY)
    m8.add(Case("Gap 02:30 forward: dst_status=gap",
               gap_res[0].dst_status, DST_STATUS_GAP))
    m8.add(Case("Gap 02:30 forward: is_missing=True",
               gap_res[0].is_missing, True))
    m8.add(Case("Gap 02:30 forward: gap_applied=forward",
               gap_res[0].gap_applied, "forward"))
    m8.add(Case("Gap 02:30 forward: adjustment_minutes=30",
               gap_res[0].adjustment_minutes, 30))
    m8.add(Case("Gap 02:30 forward: fold_used=None",
               gap_res[0].fold_used, None))

    # Ambiguity 场景：2024-11-03 01:30 fold=1
    ambig_items = [
        {"expr": "2024-11-03T01:30:00", "tz": NY, "fold": 1,
         "type": "iso_datetime"},
    ]
    ambig_res = engine.parse_many(ambig_items, base=base_batch, tz_name=NY)
    m8.add(Case("Ambig 01:30 fold=1: dst_status=ambiguous",
               ambig_res[0].dst_status, DST_STATUS_AMBIGUOUS))
    m8.add(Case("Ambig 01:30 fold=1: is_ambiguous=True",
               ambig_res[0].is_ambiguous, True))
    m8.add(Case("Ambig 01:30 fold=1: fold_used=1",
               ambig_res[0].fold_used, 1))
    m8.add(Case("Ambig 01:30 fold=1: is_missing=False",
               ambig_res[0].is_missing, False))

    # JSON 序列化验证
    import json as _json
    gap_dict = gap_res[0].as_dict()
    m8.add(Case("JSON: as_dict 包含 dst_status 键",
               "dst_status" in gap_dict, True))
    m8.add(Case("JSON: as_dict result 为字符串",
               isinstance(gap_dict["result"], str), True))
    json_str = gap_res[0].to_json()
    parsed_back = _json.loads(json_str)
    m8.add(Case("JSON: to_json 可 round-trip",
               parsed_back["type"], "iso_datetime"))
    m8.add(Case("JSON: round-trip dst_status 保留",
               parsed_back["dst_status"], DST_STATUS_GAP))

    # parse_many_json 验证
    json_batch = engine.parse_many_json(
        ["3天后", "P1D"], base=base_batch, tz_name=NY,
    )
    batch_parsed = _json.loads(json_batch)
    m8.add(Case("JSON batch: results 长度=2",
               len(batch_parsed["results"]), 2))
    m8.add(Case("JSON batch: [0] result 为字符串",
               isinstance(batch_parsed["results"][0]["result"], str), True))

    # ========================================================
    # 模块 9: Cron next_n_triggers with max_span
    # ========================================================
    m9 = suite.module("Cron next_n_triggers (max_span)")

    # 正常: 每分钟 5 次
    cron_min = CronExpression.parse("0 * * * * ?")
    m9.add(Case("next_n 5: 每分钟, 长度=5",
               len(cron_min.next_n_triggers(5, datetime(2024, 6, 17, 10, 0, 0))),
               5))

    # 稀疏规则: 2月29日零点, max_span=1年 应该只找到1次
    cron_leap = CronExpression.parse("0 0 0 29 2 ?")
    n_triggers = cron_leap.next_n_triggers(
        10, datetime(2024, 1, 1), max_span=timedelta(days=365),
    )
    m9.add(Case("2/29 规则 max_span=1年: 仅找到1次",
               len(n_triggers), 1))
    m9.add(Case("2/29 规则: 2024-02-29 (首次匹配)",
               n_triggers[0], datetime(2024, 2, 29, 0, 0, 0)))

    # 无限制: 应找到更多
    n_triggers_no_limit = cron_leap.next_n_triggers(
        3, datetime(2024, 1, 1),
    )
    m9.add(Case("2/29 规则 无 max_span: 找到3次",
               len(n_triggers_no_limit), 3))

    # max_span=0: 不应找到任何
    n_triggers_zero = cron_leap.next_n_triggers(
        5, datetime(2024, 1, 1), max_span=timedelta(0),
    )
    m9.add(Case("max_span=0: 找到0次",
               len(n_triggers_zero), 0))

    # start/end 范围查询
    cron_hourly = CronExpression.parse("0 0 * * * ?")
    hourly_in_range = cron_hourly.next_n_triggers(
        100,
        start=datetime(2024, 6, 17, 0, 0, 0),
        end=datetime(2024, 6, 17, 5, 0, 0),
    )
    m9.add(Case("每小时 start/end: 0:00-5:00 内共4次 (end不含)",
               len(hourly_in_range), 4))
    m9.add(Case("每小时 start/end: 首次=06-17 01:00",
               hourly_in_range[0], datetime(2024, 6, 17, 1, 0, 0)))
    m9.add(Case("每小时 start/end: 末次=06-17 04:00",
               hourly_in_range[-1], datetime(2024, 6, 17, 4, 0, 0)))

    # 稀疏规则 + 短窗口: 立即返回空列表
    empty_range = cron_leap.next_n_triggers(
        10,
        start=datetime(2024, 6, 1),
        end=datetime(2024, 6, 30),
    )
    m9.add(Case("2/29 规则 窗口6月: 返回空列表",
               empty_range, []))

    # end 严格不包含
    end_exclusive = cron_hourly.next_n_triggers(
        100,
        start=datetime(2024, 6, 17, 0, 0, 0),
        end=datetime(2024, 6, 17, 3, 0, 0),
    )
    m9.add(Case("每小时 end=3:00 不含: 仅2次",
               len(end_exclusive), 2))

    # ========================================================
    # 模块 10: parse_many_json 带 summary
    # ========================================================
    m10 = suite.module("parse_many_json 批量结果")

    import json as _json
    json_str = engine.parse_many_json(
        ["3天后", "0 0 0 L * ?", "P1D"],
        base=base_batch,
    )
    payload = _json.loads(json_str)
    m10.add(Case("JSON payload 含 results 键",
               "results" in payload, True))
    m10.add(Case("JSON payload 含 summary 键",
               "summary" in payload, True))
    m10.add(Case("JSON payload 含 elapsed_ms 键",
               "elapsed_ms" in payload, True))
    m10.add(Case("JSON payload 含 fail_count 键",
               "fail_count" in payload, True))
    m10.add(Case("JSON payload results 长度=3",
               len(payload["results"]), 3))
    m10.add(Case("JSON summary.total=3",
               payload["summary"]["total"], 3))
    m10.add(Case("JSON summary.ok=3",
               payload["summary"]["ok"], 3))
    m10.add(Case("JSON summary.fail=0",
               payload["summary"]["fail"], 0))
    m10.add(Case("JSON elapsed_ms 为数值",
               isinstance(payload["elapsed_ms"], (int, float)), True))
    m10.add(Case("JSON fail_count 为 0",
               payload["fail_count"], 0))

    # 带错误的 JSON
    json_err = engine.parse_many_json(
        ["BAD_CRON!!!", "3天后"],
        base=base_batch,
    )
    payload_err = _json.loads(json_err)
    m10.add(Case("JSON 带错误: fail_count=1",
               payload_err["fail_count"], 1))
    m10.add(Case("JSON 带错误: [0] ok=False",
               payload_err["results"][0]["ok"], False))
    m10.add(Case("JSON 带错误: [0] error 非空",
               bool(payload_err["results"][0]["error"]), True))
    m10.add(Case("JSON 带错误: [1] ok=True",
               payload_err["results"][1]["ok"], True))

    return suite


def main() -> int:
    suite = build_suite()
    ok = suite.run()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
