#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Run - 测试运行入口
一键运行 pytest 并生成 Allure 报告

Usage:
    python run.py all              # 运行所有测试
    python run.py smoke            # 运行冒烟测试
    python run.py login            # 运行登录模块测试
    python run.py project          # 运行项目模块测试
    python run.py report           # 运行测试并生成 Allure 报告
    python run.py open            # 打开 Allure 报告
    python run.py clean           # 清理报告和缓存
    python run.py help            # 显示帮助信息
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path


# ============================================================================
# 项目根目录
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================================
# 路径配置
# ============================================================================

TESTCASES_DIR = PROJECT_ROOT / "testcases"
REPORTS_DIR = PROJECT_ROOT / "reports"
ALLURE_RESULTS = REPORTS_DIR / "allure-results"
ALLURE_REPORT = REPORTS_DIR / "allure-report"
HTML_REPORT = REPORTS_DIR / "report.html"
LOGS_DIR = PROJECT_ROOT / "logs"


# ============================================================================
# pytest 配置
# ============================================================================

def get_pytest_args(test_path: str = None, markers: str = None, keyword: str = None) -> list:
    """
    构建 pytest 命令行参数

    Args:
        test_path: 测试路径（默认为 testcases）
        markers: pytest markers 表达式
        keyword: 测试函数关键字过滤

    Returns:
        pytest 命令行参数列表
    """
    args = ["pytest"]

    if test_path:
        args.append(str(test_path))

    if markers:
        args.extend(["-m", markers])

    if keyword:
        args.extend(["-k", keyword])

    args.extend([
        "--alluredir", str(ALLURE_RESULTS),
        "--tb=short",
        "-v",
        "--color=yes",
    ])

    return args


# ============================================================================
# 命令执行
# ============================================================================

def run_command(cmd: list, description: str = "") -> int:
    """
    执行命令并输出结果

    Args:
        cmd: 命令列表
        description: 命令描述

    Returns:
        返回码
    """
    print()
    print("=" * 70)
    print(f"🚀 {description}")
    print(f"📝 命令: {' '.join(cmd)}")
    print("=" * 70)

    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    return result.returncode


def clean_reports():
    """清理报告和缓存"""
    print()
    print("=" * 70)
    print("🧹 清理报告和缓存...")
    print("=" * 70)

    dirs_to_clean = [REPORTS_DIR, LOGS_DIR, PROJECT_ROOT / "__pycache__"]
    cache_dirs = list(PROJECT_ROOT.glob("**/__pycache__"))

    dirs_to_clean.extend(cache_dirs)

    for directory in dirs_to_clean:
        if directory.exists():
            if directory.is_dir():
                shutil.rmtree(directory, ignore_errors=True)
                print(f"   ✅ 删除目录: {directory}")
            else:
                directory.unlink()
                print(f"   ✅ 删除文件: {directory}")

    for pyc_file in PROJECT_ROOT.glob("**/*.pyc"):
        pyc_file.unlink(missing_ok=True)

    print()
    print("✅ 清理完成!")


# ============================================================================
# 测试运行函数
# ============================================================================

def run_all_tests():
    """运行所有测试"""
    return run_command(
        get_pytest_args(test_path=str(TESTCASES_DIR)),
        "运行所有测试"
    )


def run_smoke_tests():
    """运行冒烟测试"""
    return run_command(
        get_pytest_args(test_path=str(TESTCASES_DIR), markers="smoke"),
        "运行冒烟测试"
    )


def run_regression_tests():
    """运行回归测试"""
    return run_command(
        get_pytest_args(test_path=str(TESTCASES_DIR), markers="regression"),
        "运行回归测试"
    )


def run_by_module(module: str):
    """按模块运行测试"""
    return run_command(
        get_pytest_args(test_path=str(TESTCASES_DIR), markers=module),
        f"运行 {module} 模块测试"
    )


def run_by_keyword(keyword: str):
    """按关键字运行测试"""
    return run_command(
        get_pytest_args(test_path=str(TESTCASES_DIR), keyword=keyword),
        f"运行包含 '{keyword}' 的测试"
    )


def run_with_allure_report():
    """运行测试并生成 Allure 报告"""
    exit_code = run_command(
        get_pytest_args(test_path=str(TESTCASES_DIR)),
        "运行所有测试并生成 Allure 报告"
    )

    if exit_code == 0:
        print()
        print("✅ 测试执行完成，正在生成报告...")

        if ALLURE_RESULTS.exists() and any(ALLURE_RESULTS.iterdir()):
            generate_allure_report()
        else:
            print()
            print("⚠️ 未找到测试结果，跳过报告生成")
            print(f"   结果目录: {ALLURE_RESULTS}")

    return exit_code


def generate_allure_report():
    """生成 Allure 报告"""
    if not ALLURE_RESULTS.exists():
        print()
        print("⚠️ Allure 结果目录不存在")
        return

    print()
    print("=" * 70)
    print("📊 生成 Allure 报告...")
    print("=" * 70)

    result = subprocess.run(
        ["allure", "generate", str(ALLURE_RESULTS), "-o", str(ALLURE_REPORT), "--clean"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print()
        print("✅ Allure 报告生成成功!")
        print(f"   报告路径: {ALLURE_REPORT}")
        print()
        print("💡 使用以下命令打开报告:")
        print(f"   allure open {ALLURE_REPORT}")
        print(f"   或者直接打开: {ALLURE_REPORT / 'index.html'}")
    else:
        print()
        print("⚠️ Allure 报告生成失败")
        print(f"   错误: {result.stderr}")


def open_allure_report():
    """打开 Allure 报告"""
    if not ALLURE_REPORT.exists():
        print()
        print("⚠️ Allure 报告不存在，请先运行测试生成报告")
        print("   命令: python run.py report")
        return

    print()
    print("=" * 70)
    print("🌐 打开 Allure 报告...")
    print("=" * 70)

    subprocess.run(
        ["allure", "open", str(ALLURE_REPORT)],
        cwd=str(PROJECT_ROOT)
    )


def open_html_report():
    """打开 HTML 报告"""
    if not HTML_REPORT.exists():
        print()
        print("⚠️ HTML 报告不存在，请先运行测试生成报告")
        return

    print()
    print(f"🌐 打开 HTML 报告: {HTML_REPORT}")

    if sys.platform == "win32":
        os.startfile(HTML_REPORT)
    elif sys.platform == "darwin":
        subprocess.run(["open", HTML_REPORT])
    else:
        subprocess.run(["xdg-open", HTML_REPORT])


def show_help():
    """显示帮助信息"""
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                    API 自动化测试运行器                                ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  用法: python run.py [命令] [选项]                                   ║
║                                                                      ║
║  命令:                                                                ║
║    all        运行所有测试                                            ║
║    smoke      运行冒烟测试 (-m smoke)                                 ║
║    regression 运行回归测试 (-m regression)                            ║
║    login      运行登录模块测试 (-m login)                             ║
║    project    运行项目模块测试 (-m project)                           ║
║    user       运行用户模块测试 (-m user)                              ║
║    order      运行订单模块测试 (-m order)                             ║
║    product    运行商品模块测试 (-m product)                           ║
║                                                                      ║
║    report     运行所有测试并生成 Allure 报告                           ║
║    open       打开 Allure 报告                                        ║
║    html       打开 HTML 报告                                          ║
║                                                                      ║
║    clean      清理报告和缓存                                          ║
║    help       显示帮助信息                                            ║
║                                                                      ║
║  选项:                                                                ║
║    -k <关键字>  按测试函数名关键字过滤                                 ║
║                                                                      ║
║  示例:                                                                ║
║    python run.py all                    # 运行所有测试              ║
║    python run.py smoke                   # 运行冒烟测试              ║
║    python run.py login                   # 运行登录测试              ║
║    python run.py report                 # 运行并生成报告              ║
║    python run.py open                   # 打开报告                   ║
║    python run.py clean                  # 清理缓存                   ║
║                                                                      ║
║  环境变量:                                                            ║
║    API_BASE_URL   覆盖 API 基础 URL                                   ║
║    TEST_ENV       测试环境 (dev/test/staging)                         ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
    """)


def show_test_summary():
    """显示测试摘要信息"""
    print()
    print("=" * 70)
    print("📋 测试配置摘要")
    print("=" * 70)
    print(f"   项目根目录: {PROJECT_ROOT}")
    print(f"   测试目录:   {TESTCASES_DIR}")
    print(f"   报告目录:   {REPORTS_DIR}")
    print(f"   日志目录:   {LOGS_DIR}")
    print()

    test_files = list(TESTCASES_DIR.glob("test_*.py"))
    print(f"   测试文件:   {len(test_files)} 个")
    for f in test_files:
        print(f"     - {f.name}")

    print()
    print("=" * 70)


# ============================================================================
# 主函数
# ============================================================================

def main():
    """主入口函数"""
    if len(sys.argv) < 2:
        show_help()
        show_test_summary()
        sys.exit(0)

    command = sys.argv[1].lower()

    if command == "help" or command == "h" or command == "?":
        show_help()

    elif command == "all":
        exit_code = run_all_tests()
        sys.exit(exit_code)

    elif command == "smoke":
        exit_code = run_smoke_tests()
        sys.exit(exit_code)

    elif command == "regression":
        exit_code = run_regression_tests()
        sys.exit(exit_code)

    elif command in ["login", "project", "user", "order", "product", "api"]:
        exit_code = run_by_module(command)
        sys.exit(exit_code)

    elif command == "report":
        exit_code = run_with_allure_report()
        sys.exit(exit_code)

    elif command == "open":
        open_allure_report()

    elif command == "html":
        open_html_report()

    elif command == "clean":
        clean_reports()

    elif command == "-k" and len(sys.argv) >= 3:
        keyword = sys.argv[2]
        exit_code = run_by_keyword(keyword)
        sys.exit(exit_code)

    elif command == "summary":
        show_test_summary()

    else:
        print()
        print(f"⚠️ 未知命令: {command}")
        print()
        show_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
