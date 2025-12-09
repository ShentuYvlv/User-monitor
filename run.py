import sys
import os
import subprocess
from pathlib import Path

def main():
    # 获取当前脚本所在目录
    BASE_DIR = Path(__file__).resolve().parent
    
    # 虚拟环境路径 (假设名为 venv)
    VENV_DIR = BASE_DIR / "venv"
    
    # 检查当前是否在虚拟环境中
    # sys.prefix != sys.base_prefix 是判断是否在 venv 的标准方法
    in_venv = sys.prefix != sys.base_prefix

    # 定义启动命令
    # 注意: Windows下通常用 127.0.0.1，Linux服务器部署时建议用 0.0.0.0
    host = "127.0.0.1" if sys.platform == "win32" else "0.0.0.0"
    uvicorn_cmd = [
        "uvicorn", 
        "app.main:app", 
        "--reload", 
        "--host", host, 
        "--port", "8000"
    ]

    if not in_venv:
        # 如果不在虚拟环境中
        print("[-] Current environment: System Python (Not in venv)")
        
        # 检测 Windows 还是 Linux 来决定 python 路径
        if sys.platform == "win32":
            venv_python = VENV_DIR / "Scripts" / "python.exe"
        else:
            venv_python = VENV_DIR / "bin" / "python"

        if venv_python.exists():
            print(f"[+] Found virtual environment at: {VENV_DIR}")
            print("[*] Switching to venv and starting server...\n")
            
            # 使用虚拟环境的 python 来执行 uvicorn 模块
            # 相当于: venv/Scripts/python.exe -m uvicorn app.main:app ...
            cmd = [str(venv_python), "-m"] + uvicorn_cmd
            
            try:
                # 移交控制权给子进程
                subprocess.run(cmd, check=True)
            except KeyboardInterrupt:
                pass # 允许 Ctrl+C 退出不报错
            return
        else:
            print(f"[!] Warning: Virtual environment not found at {VENV_DIR}")
            print("[*] Trying to run with current python anyway...\n")
    
    else:
        print("[+] Current environment: Virtual Environment")
        print("[*] Starting server...\n")

    # 如果已经在 venv 中，或者强制运行
    try:
        subprocess.run(uvicorn_cmd, check=True)
    except KeyboardInterrupt:
        pass
    except FileNotFoundError:
        print("[!] Error: 'uvicorn' not found. Please run: pip install -r requirements.txt")

if __name__ == "__main__":
    main()
