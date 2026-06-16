"""
时间表达式解析引擎 - 命令行入口

用法:
  python cli.py "3天后" "0 0 0 L * ?" "P1Y2M3D"
  python cli.py -f expressions.txt
  python cli.py -f expressions.txt --format json
  python cli.py -f expressions.txt --base 2024-06-17T10:00:00 --tz Asia/Shanghai
  python cli.py "3天后" --format json --indent 4

每行一条表达式, 空行和 # 开头的行跳过。
错误项不会中断整批, 结果里保留原始表达式和错误原因。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import List


def _read_lines_from_file(path: str) -> List[str]:
    lines: List[str] = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            stripped = raw.strip()
            if stripped and not stripped.startswith("#"):
                lines.append(stripped)
    return lines


def _print_table(results, summary, elapsed_ms):
    W = 78
    print("=" * W)
    print("  时间表达式批量解析结果")
    print("=" * W)
    print(
        f"  {'#':<4s}  {'类型':<16s}  {'状态':<6s}  "
        f"{'结果 / 错误':<36s}  原始表达式"
    )
    print("-" * W)
    for i, r in enumerate(results):
        status = "OK" if r.ok else "FAIL"
        if r.ok:
            if isinstance(r.result, datetime):
                val = r.result.strftime("%Y-%m-%d %H:%M:%S")
                if r.result.tzinfo:
                    off = r.result.strftime("%z")
                    val += f" {off}"
            else:
                val = str(r.result)[:34]
        else:
            val = (r.error or "")[:34]
        raw_short = r.raw[:18] + (".." if len(r.raw) > 18 else "")
        print(
            f"  {i:<4d}  {r.type:<16s}  {status:<6s}  "
            f"{val:<36s}  {raw_short}"
        )
        if r.dst_status != "normal":
            diag_parts = [f"dst={r.dst_status}"]
            if r.gap_applied:
                diag_parts.append(f"gap={r.gap_applied}")
            if r.fold_used is not None:
                diag_parts.append(f"fold={r.fold_used}")
            if r.adjustment_minutes:
                diag_parts.append(f"adj={r.adjustment_minutes}m")
            print(f"       {'':<16s}  {'':<6s}  {' '.join(diag_parts)}")
    print("-" * W)
    print(
        f"  总计: {summary['total']}  "
        f"OK: {summary['ok']}  "
        f"FAIL: {summary['fail']}  "
        f"耗时: {elapsed_ms:.1f}ms"
    )
    if summary["by_type"]:
        print("  按类型:")
        for t, s in summary["by_type"].items():
            print(f"    {t:<16s}  OK={s['ok']}  FAIL={s['fail']}  total={s['total']}")
    print("=" * W)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="时间表达式解析引擎 - 命令行批量解析工具",
    )
    parser.add_argument(
        "expressions", nargs="*",
        help="要解析的表达式列表",
    )
    parser.add_argument(
        "-f", "--file",
        help="从文件读取表达式 (每行一条, # 开头为注释, 空行跳过)",
    )
    parser.add_argument(
        "--format", choices=["table", "json"], default="table",
        help="输出格式: table (默认) 或 json",
    )
    parser.add_argument(
        "--base",
        help="基准时间 (ISO 格式, 如 2024-06-17T10:00:00)",
    )
    parser.add_argument(
        "--tz", default=None,
        help="默认时区 (如 Asia/Shanghai, America/New_York)",
    )
    parser.add_argument(
        "--indent", type=int, default=2,
        help="JSON 缩进空格数 (仅 --format json, 默认 2)",
    )
    parser.add_argument(
        "--gap-strategy", choices=["forward", "shift"], default="forward",
        help="DST gap 处理策略 (默认 forward)",
    )

    args = parser.parse_args(argv)

    from engine import TimeExpressionEngine

    all_expr: List[str] = list(args.expressions or [])
    if args.file:
        try:
            all_expr.extend(_read_lines_from_file(args.file))
        except FileNotFoundError:
            print(f"[ERROR] 文件不存在: {args.file}", file=sys.stderr)
            return 2
        except Exception as e:
            print(f"[ERROR] 读取文件失败: {e}", file=sys.stderr)
            return 2

    if not all_expr:
        print("[ERROR] 未提供任何表达式。请通过参数或 -f 文件指定。", file=sys.stderr)
        return 1

    base = None
    if args.base:
        try:
            base = datetime.fromisoformat(args.base)
        except ValueError:
            print(f"[ERROR] 无法解析基准时间: {args.base}", file=sys.stderr)
            return 1

    engine = TimeExpressionEngine(default_timezone=args.tz)

    if args.format == "json":
        json_str = engine.parse_many_json(
            all_expr, base=base, tz_name=args.tz,
            gap_strategy=args.gap_strategy, indent=args.indent,
        )
        print(json_str)
        return 0

    results = engine.parse_many(
        all_expr, base=base, tz_name=args.tz,
        gap_strategy=args.gap_strategy,
    )
    summary = engine.summarize(results)
    import time as _time
    _t0 = _time.perf_counter()
    engine.parse_many(
        all_expr, base=base, tz_name=args.tz,
        gap_strategy=args.gap_strategy,
    )
    elapsed_ms = (_time.perf_counter() - _t0) * 1000.0

    _print_table(results, summary, elapsed_ms)
    return 1 if summary["fail"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
