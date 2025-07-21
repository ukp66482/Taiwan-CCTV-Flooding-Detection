import subprocess
import glob
import time
from multiprocessing import Process

def run_capture(json_file):
    try:
        print(f"啟動子進程: {json_file}")
        subprocess.run(["python", "capture_all.py", "--json", json_file])
    except Exception as e:
        print(f"執行 {json_file} 發生錯誤: {e}")

if __name__ == "__main__":
    json_files = sorted(glob.glob("*_cameras.json"))
    processes = []

    for json_file in json_files:
        p = Process(target=run_capture, args=(json_file,))
        p.start()
        processes.append(p)
        time.sleep(1) # 避免過快啟動多個進程

    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        print("\n收到中斷，正在終止所有子進程...")
        for p in processes:
            p.terminate()
        print("已全部停止。")
