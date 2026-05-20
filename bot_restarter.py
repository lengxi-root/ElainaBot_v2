import os, sys, time, subprocess
def main():
    time.sleep(3)
    main_path = r"main.py"
    os.chdir(os.path.dirname(main_path))
    subprocess.Popen([sys.executable, main_path], creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),  # 旧版Python没有这个字段，进行兼容
                     cwd=os.path.dirname(main_path))
    time.sleep(1)
    try: os.remove(__file__)
    except: pass
    sys.exit(0)
if __name__ == "__main__":
    main()
