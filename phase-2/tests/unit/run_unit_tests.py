"""
Simple test runner for ToolResult system unit tests.

This script runs the comprehensive unit test suite for the ToolResult system
without requiring actual OpenShift cluster access or external dependencies.

Usage:
    python tests/unit/run_unit_tests.py [--verbose] [--specific-test-module]
"""

import argparse
import subprocess
import sys
from pathlib import Path


def get_directories():
    """Get project directories for display purposes only"""
    # Get the root directory (parent of tests) - now we're in tests/unit/
    root_dir = Path(__file__).parent.parent.parent.resolve()
    app_dir = root_dir / "app"
    return root_dir, app_dir


def check_dependencies():
    """Check if required testing dependencies are available"""
    required_packages = [
        "pytest",
        "pytest-asyncio",
        "pydantic",
    ]

    missing = []
    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
        except ImportError:
            missing.append(package)

    if missing:
        print(f"❌ Missing required packages: {', '.join(missing)}")
        print("Install with: pip install " + " ".join(missing))
        return False

    return True


def discover_test_modules():
    """Discover available test modules"""
    # Unit tests are in the same directory as this script
    test_dir = Path(__file__).parent
    test_modules = []

    if test_dir.exists():
        for test_file in test_dir.glob("test_*.py"):
            module_name = test_file.stem
            test_modules.append(module_name)

    return sorted(test_modules)


def run_tests(verbose=False, specific_module=None):
    """Run the test suite using pytest"""
    root_dir, app_dir = get_directories()

    if not check_dependencies():
        return False

    # Python path is now configured in pytest.ini

    # Build pytest command
    cmd = ["python", "-m", "pytest"]

    if verbose:
        cmd.append("-v")
    else:
        cmd.append("-q")

    # Add async support
    cmd.extend(["--tb=short", "-p", "no:warnings"])

    # Determine what to test - unit tests are in the same directory as this script
    test_dir = Path(__file__).parent
    if specific_module:
        test_file = test_dir / f"{specific_module}.py"
        if test_file.exists():
            cmd.append(str(test_file))
            print(f"🧪 Running tests for {specific_module}")
        else:
            print(f"❌ Test module {specific_module} not found")
            return False
    else:
        cmd.append(str(test_dir))
        print("🧪 Running all ToolResult system unit tests")

    print(f"📁 Test directory: {test_dir}")
    print(f"📁 App directory: {app_dir}")
    print()

    # Run pytest
    try:
        result = subprocess.run(cmd, cwd=root_dir, check=False)
        return result.returncode == 0
    except FileNotFoundError:
        print("❌ pytest not found. Install with: pip install pytest pytest-asyncio")
        return False
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Run ToolResult system unit tests")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Run tests in verbose mode"
    )
    parser.add_argument(
        "-m",
        "--module",
        help="Run specific test module (e.g., test_models, test_pod_tools)",
    )
    parser.add_argument(
        "--list-modules", action="store_true", help="List available test modules"
    )

    args = parser.parse_args()

    if args.list_modules:
        print("Available test modules:")
        modules = discover_test_modules()
        for module in modules:
            print(f"  - {module}")
        return 0

    print("🚀 ToolResult System Unit Test Runner")
    print("=" * 50)

    success = run_tests(verbose=args.verbose, specific_module=args.module)

    print("\n" + "=" * 50)
    if success:
        print("✅ All tests passed!")
        return 0
    else:
        print("❌ Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
