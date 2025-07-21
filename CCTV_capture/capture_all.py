import os
import time
import requests
import logging
import json
import urllib3
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import re

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 全域設定
IMAGE_DIR = "downloaded_images"
DELAY_BETWEEN_CAMERAS = 1  # 每個攝影機之間的延遲（秒）- 從3秒改為1秒
DELAY_BETWEEN_ROUNDS = 5   # 每輪之間的延遲（秒）- 從10秒改為5秒

def setup_logger():
    os.makedirs("logs", exist_ok=True)
    log_file = os.path.join("logs", f"cyclic_capture_{datetime.now().strftime('%Y%m%d')}.log")
    
    logger = logging.getLogger("cyclic_capture")
    logger.setLevel(logging.INFO)
    
    # 清除舊的handler避免重複
    if logger.handlers:
        logger.handlers.clear()
    
    handler_file = logging.FileHandler(log_file, encoding="utf-8")
    handler_console = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler_file.setFormatter(formatter)
    handler_console.setFormatter(formatter)
    logger.addHandler(handler_file)
    logger.addHandler(handler_console)
    return logger

def extract_camera_id(cam_url):
    """從URL中提取攝影機編號"""
    match = re.search(r'tnn-(\d+)', cam_url)
    if match:
        return f"tnn_{match.group(1)}"
    return "unknown"

def get_latest_image_url(driver, logger, cam_name):
    logger.info(f"[{cam_name}] Waiting for img.video_obj ...")
    try:
        # 直接尋找影像元素
        img_elem = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "img.video_obj"))
        )
        
        # 嘗試多次獲取動態URL
        for _ in range(5):
            img_url = img_elem.get_attribute("src")
            if img_url and "t=" in img_url:
                logger.info(f"[{cam_name}] Found image URL: {img_url}")
                return img_url
            time.sleep(0.3)
        
        # 如果沒有動態URL，返回靜態URL
        img_url = img_elem.get_attribute("src")
        if img_url:
            logger.info(f"[{cam_name}] Found static image URL: {img_url}")
            return img_url
        else:
            logger.warning(f"[{cam_name}] No image URL found")
            return None
            
    except Exception as e:
        logger.warning(f"[{cam_name}] Image not found: {e}")
        return None

def download_first_jpeg_from_mjpeg(url, filename, logger, cam_name):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': 'https://www.1968services.tw/cam/',
        'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
        'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
        'Connection': 'keep-alive',
    }
    
    try:
        session = requests.Session()
        session.verify = False
        
        response = session.get(url, headers=headers, stream=True, timeout=10)  # 從15秒減少到10秒
        
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '').lower()
            
            if 'image/jpeg' in content_type or 'image/jpg' in content_type:
                # 直接是JPEG圖片
                with open(filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                logger.info(f"[{cam_name}] Saved as direct JPEG: {filename}")
                return True
                
            elif 'multipart' in content_type or 'video' in content_type:
                # MJPEG串流處理
                bytes_data = b""
                max_size = 2 * 1024 * 1024  # 2MB限制
                
                for chunk in response.iter_content(chunk_size=1024):
                    if not chunk:
                        continue
                        
                    bytes_data += chunk
                    
                    if len(bytes_data) > max_size:
                        bytes_data = bytes_data[-max_size//2:]
                    
                    start = bytes_data.find(b'\xff\xd8')
                    end = bytes_data.find(b'\xff\xd9')
                    
                    if start != -1 and end != -1 and end > start:
                        jpg_data = bytes_data[start:end+2]
                        
                        if len(jpg_data) > 1000:  # 至少1KB
                            with open(filename, 'wb') as f:
                                f.write(jpg_data)
                            logger.info(f"[{cam_name}] Saved from MJPEG: {filename}")
                            return True
                        else:
                            continue
            else:
                # 嘗試直接保存
                with open(filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                logger.info(f"[{cam_name}] Saved as unknown format: {filename}")
                return True
                
        else:
            logger.error(f"[{cam_name}] HTTP error {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"[{cam_name}] Download error: {e}")
        return False
    
    return False

def capture_single_camera(driver, cam_url, cam_name, camera_id, logger):
    """抓取單個攝影機的圖片"""
    
    # 使用攝影機名稱作為資料夾名稱（相同名稱的攝影機會放在同一個資料夾）
    safe_cam_name = re.sub(r'[<>:"/\\|?*]', '_', cam_name)
    cam_dir = os.path.join(IMAGE_DIR, safe_cam_name)
    os.makedirs(cam_dir, exist_ok=True)
    
    try:
        driver.get(cam_url)
        logger.info(f"[{camera_id}] Navigated to {cam_url}")
        time.sleep(2)  # 等待頁面載入
        
        image_url = get_latest_image_url(driver, logger, camera_id)
        
        if image_url:
            # 正常情況下載圖片
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(cam_dir, f"{camera_id}_{timestamp}.jpg")
            
            if download_first_jpeg_from_mjpeg(image_url, filename, logger, camera_id):
                # 驗證文件
                if os.path.exists(filename):
                    file_size = os.path.getsize(filename)
                    if file_size < 1000:
                        logger.warning(f"[{camera_id}] File too small, removing: {filename}")
                        os.remove(filename)
                        return False
                    else:
                        logger.info(f"[{camera_id}] ✅ Success: {filename} ({file_size} bytes)")
                        return True
            else:
                logger.warning(f"[{camera_id}] ❌ Download failed")
                return False
        else:
            logger.warning(f"[{camera_id}] ❌ No image URL found")
            return False
            
    except Exception as e:
        logger.error(f"[{camera_id}] ❌ Error: {e}")
        return False

def load_cameras_from_json():
    """從JSON檔案載入攝影機清單"""
    logger = setup_logger()
    
    json_files = ["all_cameras.json", "discovered_cameras.json"]
    
    for json_file in json_files:
        if os.path.exists(json_file):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    cameras_data = json.load(f)
                
                logger.info(f"從 {json_file} 載入 {len(cameras_data)} 個攝影機")
                
                # 處理相同名稱的攝影機，確保每個都有唯一識別
                processed_cameras = []
                
                for name, url in cameras_data.items():
                    camera_id = extract_camera_id(url)
                    
                    # 移除名稱中可能已經存在的編號後綴
                    clean_name = re.sub(r'\s*\([^)]*\)$', '', name)
                    
                    # 創建唯一的攝影機條目
                    processed_cameras.append({
                        'name': clean_name,
                        'url': url,
                        'camera_id': camera_id,
                        'unique_name': f"{clean_name} ({camera_id})"
                    })
                
                # 按攝影機編號排序
                processed_cameras.sort(key=lambda x: int(re.search(r'(\d+)', x['camera_id']).group(1)))
                
                return processed_cameras
                
            except Exception as e:
                logger.error(f"讀取 {json_file} 時發生錯誤: {e}")
                continue
    
    # 如果沒有找到JSON檔案，使用預設攝影機
    logger.warning("未找到攝影機清單檔案，使用預設攝影機")
    default_cameras = [
        {
            'name': "勝利路小東路交叉路口",
            'url': "https://www.1968services.tw/cam/tnn-00138",
            'camera_id': "tnn_00138",
            'unique_name': "勝利路小東路交叉路口 (tnn_00138)"
        },
        {
            'name': "東門路中華東路",
            'url': "https://www.1968services.tw/cam/tnn-00036",
            'camera_id': "tnn_00036",
            'unique_name': "東門路中華東路 (tnn_00036)"
        },
        {
            'name': "前鋒路",
            'url': "https://www.1968services.tw/cam/tnn-00133",
            'camera_id': "tnn_00133",
            'unique_name': "前鋒路 (tnn_00133)"
        },
        {
            'name': "小東路地下道",
            'url': "https://www.1968services.tw/cam/tnn-00110",
            'camera_id': "tnn_00110",
            'unique_name': "小東路地下道 (tnn_00110)"
        }
    ]
    return default_cameras

def main():
    print("=== 快速循環抓取攝影機監控系統 ===")
    print("特色：高速循環抓取所有攝影機，完成一輪後重新開始")
    print("檔名格式：攝影機編號_時間戳記.jpg")
    print("資料夾格式：攝影機名稱（相同名稱的攝影機放在同一資料夾）")
    print("⚡ 已優化速度：攝影機間隔1秒，輪次間隔5秒")
    
    # 創建圖片存放目錄
    os.makedirs(IMAGE_DIR, exist_ok=True)
    
    logger = setup_logger()
    
    # 載入攝影機清單
    camera_list = load_cameras_from_json()
    
    if not camera_list:
        print("❌ 沒有找到任何攝影機")
        return
    
    # 顯示攝影機統計
    total_cameras = len(camera_list)
    logger.info(f"載入完成，總共 {total_cameras} 個攝影機")
    
    # 統計相同名稱的攝影機
    name_count = {}
    for cam in camera_list:
        name_count[cam['name']] = name_count.get(cam['name'], 0) + 1
    
    duplicate_names = {name: count for name, count in name_count.items() if count > 1}
    if duplicate_names:
        logger.info("發現相同名稱的攝影機：")
        for name, count in duplicate_names.items():
            logger.info(f"  {name}: {count} 個")
    
    # 選擇模式
    print(f"\n發現 {total_cameras} 個攝影機")
    print("\n請選擇模式:")
    print("1. 監控所有攝影機")
    print("2. 監控前10個攝影機（測試）")
    print("3. 監控前30個攝影機")
    print("4. 自訂監控數量")
    
    choice = input("請輸入選項 (1-4): ").strip()
    
    if choice == "1":
        selected_cameras = camera_list
        print(f"使用所有 {total_cameras} 個攝影機...")
    elif choice == "2":
        selected_cameras = camera_list[:10]
        print("使用前10個攝影機...")
    elif choice == "3":
        selected_cameras = camera_list[:30]
        print("使用前30個攝影機...")
    elif choice == "4":
        try:
            num = int(input(f"請輸入要監控的攝影機數量 (1-{total_cameras}): "))
            if 1 <= num <= total_cameras:
                selected_cameras = camera_list[:num]
                print(f"使用前{num}個攝影機...")
            else:
                selected_cameras = camera_list[:10]
                print("數量超出範圍，使用前10個攝影機...")
        except ValueError:
            selected_cameras = camera_list[:10]
            print("輸入無效，使用前10個攝影機...")
    else:
        selected_cameras = camera_list[:10]
        print("使用前10個攝影機...")
    
    total_selected = len(selected_cameras)
    
    print(f"\n開始循環監控 {total_selected} 個攝影機")
    print(f"每個攝影機間隔: {DELAY_BETWEEN_CAMERAS} 秒")
    print(f"每輪間隔: {DELAY_BETWEEN_ROUNDS} 秒")
    print("按 Ctrl+C 停止\n")
    
    # 顯示前5個攝影機作為範例
    print("監控清單範例（前5個）:")
    for i, cam in enumerate(selected_cameras[:5], 1):
        print(f"  {i}. {cam['camera_id']} - {cam['name']}")
    if total_selected > 5:
        print(f"  ... 還有 {total_selected - 5} 個攝影機")
    print()
    
    # 設定Chrome選項
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--ignore-ssl-errors")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--disable-default-apps")
    
    driver = None
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        logger.info("Chrome瀏覽器已啟動")
        
        round_number = 1
        while True:
            logger.info(f"🔄 開始第 {round_number} 輪抓取")
            success_count = 0
            failed_count = 0
            
            for i, cam in enumerate(selected_cameras, 1):
                logger.info(f"📷 [{i}/{total_selected}] 正在抓取 {cam['camera_id']} - {cam['name']}")
                
                result = capture_single_camera(
                    driver, 
                    cam['url'], 
                    cam['name'], 
                    cam['camera_id'], 
                    logger
                )
                
                if result == True:
                    success_count += 1
                else:
                    failed_count += 1
                
                # 攝影機之間的延遲（除了最後一個）
                if i < total_selected:
                    time.sleep(DELAY_BETWEEN_CAMERAS)
            
            logger.info(f"✅ 第 {round_number} 輪完成：成功 {success_count}/{total_selected}，失敗 {failed_count}")
            
            # 輪次之間的延遲
            logger.info(f"⏳ 等待 {DELAY_BETWEEN_ROUNDS} 秒後開始下一輪...")
            time.sleep(DELAY_BETWEEN_ROUNDS)
            
            round_number += 1
            
    except KeyboardInterrupt:
        logger.info("\n收到中斷信號，正在停止...")
    except Exception as e:
        logger.error(f"程式發生錯誤: {e}")
    finally:
        if driver:
            driver.quit()
            logger.info("瀏覽器已關閉")
        
        print("\n程式已停止")

if __name__ == "__main__":
    main()