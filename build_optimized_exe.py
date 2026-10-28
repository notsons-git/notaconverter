import os
import sys
import shutil
import subprocess
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def fmt_size(n_bytes: int) -> str:
    if n_bytes < 1024:
        return f"{n_bytes} B"
    if n_bytes < 1024 ** 2:
        return f"{n_bytes / 1024:.1f} KB"
    return f"{n_bytes / (1024 ** 2):.1f} MB"

def main():
    print("=" * 60)
    print("  🚀 NotAconverter - Optimized Exe Builder")
    print("=" * 60)

    # 1. Clean previous build artifacts
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            print(f"Cleaning previous {folder}/...")
            shutil.rmtree(folder, ignore_errors=True)

    spec_file = "notaconverter.spec"
    if not os.path.exists(spec_file):
        print(f"Error: {spec_file} not found!")
        sys.exit(1)

    print("\n📦 Compiling optimized executable with PyInstaller...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        spec_file
    ]

    res = subprocess.run(cmd)
    if res.returncode != 0:
        print("\n❌ Build failed!")
        sys.exit(res.returncode)

    exe_path = Path("dist/NotAconverter-1.1.1.exe")
    if exe_path.exists():
        size_bytes = exe_path.stat().st_size
        print("\n" + "=" * 60)
        print("  🎉 BUILD SUCCESSFUL!")
        print("=" * 60)
        print(f"Output File : {exe_path.resolve()}")
        print(f"Final Size  : {fmt_size(size_bytes)} ({size_bytes:,} bytes)")
        print("\nOptimization Highlights:")
        print("  ✓ Stripped 35+ MB of unused Qt6 language translation packs")
        print("  ✓ Excluded heavy Qt modules (Qt6Qml, Qt6Quick, Qt6Pdf, Qt6Network, etc.)")
        print("  ✓ Excluded unused Python stdlib modules (Tkinter, Unittest, Pydoc, etc.)")
        print("  ✓ Standalone single-file executable, ready for distribution")
        print("=" * 60)
    else:
        print("\n❌ Warning: NotAconverter.exe not found in dist/!")

if __name__ == "__main__":
    main()
