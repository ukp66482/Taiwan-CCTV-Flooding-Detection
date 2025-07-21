import os, time, json, re, requests, urllib3, argparse
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

IMAGE_DIR = "downloaded_images"
DELAY_BETWEEN_CAMERAS = 1
DELAY_BETWEEN_ROUNDS = 5
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def extract_camera_id(url):
    m = re.search(r"(tnn|khh)-(\d+)", url)
    return f"{m.group(1)}_{m.group(2)}" if m else "unknown"

def load_cameras_from_json(json_path):
    if not os.path.exists(json_path):
        print(f"找不到指定的 JSON 檔案：{json_path}")
        return []
    try:
        with open(json_path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        print(f"讀取 JSON 發生錯誤: {e}")
        return []
    flat = {}
    for city, cams in raw.items():
        if isinstance(cams, dict):
            flat.update(cams)
    processed = []
    for name, url in flat.items():
        if not isinstance(url, str): continue
        cid = extract_camera_id(url)
        cname = re.sub(r"\s*\([^)]*\)$", "", name)
        processed.append({"name": cname, "url": url, "camera_id": cid, "unique_name": f"{cname} ({cid})"})
    def _key(cam):
        m = re.search(r"(\d+)", cam["camera_id"])
        return int(m.group(1)) if m else 10**9
    processed.sort(key=_key)
    return processed

def download_first_jpeg_from_mjpeg(url, filename):
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://www.1968services.tw/cam/',
    }
    try:
        session = requests.Session()
        session.verify = False
        response = session.get(url, headers=headers, stream=True, timeout=10)
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '').lower()
            if 'image/jpeg' in content_type:
                with open(filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk: f.write(chunk)
                return True
            elif 'multipart' in content_type or 'video' in content_type:
                bytes_data = b""
                for chunk in response.iter_content(chunk_size=1024):
                    if not chunk: continue
                    bytes_data += chunk
                    if len(bytes_data) > 2 * 1024 * 1024:
                        bytes_data = bytes_data[-1024*1024:]
                    start = bytes_data.find(b'\xff\xd8')
                    end = bytes_data.find(b'\xff\xd9')
                    if start != -1 and end != -1 and end > start:
                        jpg_data = bytes_data[start:end+2]
                        if len(jpg_data) > 1000:
                            with open(filename, 'wb') as f:
                                f.write(jpg_data)
                            return True
            else:
                with open(filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk: f.write(chunk)
                return True
    except:
        return False
    return False

def capture_single_camera(driver, cam_url, cam_name, camera_id):
    safe_cam_name = re.sub(r'[<>:"/\\|?*]', '_', cam_name)
    cam_dir = os.path.join(IMAGE_DIR, safe_cam_name)
    os.makedirs(cam_dir, exist_ok=True)
    try:
        driver.get(cam_url)
        time.sleep(2)
        image_url = get_latest_image_url(driver)
        if image_url:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(cam_dir, f"{camera_id}_{timestamp}.jpg")
            if download_first_jpeg_from_mjpeg(image_url, filename):
                if os.path.exists(filename) and os.path.getsize(filename) > 1000:
                    return True
                else:
                    os.remove(filename)
        return False
    except:
        return False

def get_latest_image_url(driver):
    try:
        img_elem = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.CSS_SELECTOR, "img.video_obj")))
        for _ in range(5):
            img_url = img_elem.get_attribute("src")
            if img_url and "t=" in img_url:
                return img_url
            time.sleep(0.3)
        return img_elem.get_attribute("src")
    except:
        return None

def main():
    parser = argparse.ArgumentParser(description="循環抓取攝影機圖片")
    parser.add_argument("--json", default="all_cameras.json", help="攝影機 JSON 檔案路徑")
    args = parser.parse_args()

    os.makedirs(IMAGE_DIR, exist_ok=True)
    camera_list = load_cameras_from_json(args.json)
    if not camera_list:
        print("沒有找到任何攝影機")
        return

    selected_cameras = camera_list
    print(f"\n開始監控 {len(selected_cameras)} 個攝影機")

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    driver = None
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        round_number = 1
        while True:
            print(f"-- 第 {round_number} 輪開始 --")
            success = 0
            for i, cam in enumerate(selected_cameras, 1):
                print(f"[{i}/{len(selected_cameras)}] {cam['camera_id']} - {cam['name']}")
                if capture_single_camera(driver, cam['url'], cam['name'], cam['camera_id']):
                    success += 1
                time.sleep(DELAY_BETWEEN_CAMERAS)
            print(f"完成第 {round_number} 輪，成功 {success}/{len(selected_cameras)}")
            round_number += 1
            time.sleep(DELAY_BETWEEN_ROUNDS)
    except KeyboardInterrupt:
        print("\n已停止監控")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    main()
