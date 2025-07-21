import requests
import json
import time
import os
from bs4 import BeautifulSoup
import urllib3
from datetime import datetime
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class CameraDiscovery:
    def __init__(self):
        self.base_url = "https://www.1968services.tw/cam/"
        self.session = requests.Session()
        self.session.verify = False
        self.lock = threading.Lock()
        self.progress_count = 0
        
        # 台灣縣市代碼對照表
        self.city_codes = {
            'tnn': '台南市',
            'khh': '高雄市', 
            'tpe': '台北市',
            'nwt': '新北市',
            'tao': '桃園市',
            'tcg': '台中市',
            'chw': '彰化縣',
            'yll': '雲林縣',
            'cyi': '嘉義市',
            'cyq': '嘉義縣',
            'ptf': '屏東縣',
            'ttt': '台東縣',
            'hua': '花蓮縣',
            'ila': '宜蘭縣',
            'hsz': '新竹市',
            'hsc': '新竹縣',
            'mlc': '苗栗縣',
            'nan': '南投縣',
            'pen': '澎湖縣',
            'kmn': '金門縣',
            'lnn': '連江縣'
        }
        
        # 每個縣市的搜尋範圍（基於觀察到的模式）
        self.search_ranges = {
            'tnn': [(1, 200)],      # 台南市
            'khh': [(1, 300)],      # 高雄市
            'tpe': [(1, 500)],      # 台北市
            'nwt': [(1, 400)],     # 新北市
            'tao': [(1, 200)],      # 桃園市
            'tcg': [(1, 300)],      # 台中市
            'chw': [(1, 150)],      # 彰化縣
            'yll': [(1, 100)],      # 雲林縣
            'cyi': [(1, 80)],       # 嘉義市
            'cyq': [(1, 120)],      # 嘉義縣
            'ptf': [(1, 150)],      # 屏東縣
            'ttt': [(1, 80)],       # 台東縣
            'hua': [(1, 100)],      # 花蓮縣
            'ila': [(1, 120)],      # 宜蘭縣
            'hsz': [(1, 80)],       # 新竹市
            'hsc': [(1, 100)],      # 新竹縣
            'mlc': [(1, 100)],      # 苗栗縣
            'nan': [(1, 100)],      # 南投縣
            'pen': [(1, 50)],       # 澎湖縣
            'kmn': [(1, 50)],       # 金門縣
            'lnn': [(1, 30)]        # 連江縣
        }

    def test_camera_url(self, cam_id, timeout=5):
        """測試單個攝影機URL是否有效"""
        test_url = f"{self.base_url}{cam_id}"
        
        try:
            # 先用HEAD請求檢查狀態
            response = self.session.head(test_url, timeout=timeout)
            if response.status_code != 200:
                return None, None
            
            # 如果狀態正常，獲取頁面內容
            page_response = self.session.get(test_url, timeout=timeout)
            
            # 檢查是否包含監視器元素
            if 'video_obj' not in page_response.text:
                return None, None
            
            # 提取標題
            soup = BeautifulSoup(page_response.text, 'html.parser')
            title_elem = soup.find('title')
            
            if title_elem:
                cam_name = title_elem.text.strip()
                return test_url, cam_name
            else:
                return test_url, f"攝影機_{cam_id}"
                
        except requests.RequestException:
            return None, None

    def discover_city_cameras(self, city_code, city_name):
        """發現單一縣市的所有監視器"""
        print(f"\n🔍 搜尋 {city_name} 監視器...")
        
        cameras = {}
        ranges = self.search_ranges.get(city_code, [(1, 100)])
        
        for start, end in ranges:
            print(f"   📍 搜尋範圍 {city_code}-{start:05d} 到 {city_code}-{end:05d}")
            range_count = 0
            
            # 使用線程池加速搜尋
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_id = {}
                
                for i in range(start, end + 1):
                    cam_id = f"{city_code}-{i:05d}"
                    future = executor.submit(self.test_camera_url, cam_id, 3)
                    future_to_id[future] = cam_id
                
                for future in as_completed(future_to_id):
                    cam_id = future_to_id[future]
                    
                    with self.lock:
                        self.progress_count += 1
                        if self.progress_count % 50 == 0:
                            print(f"   ⏳ 已檢查 {self.progress_count} 個...")
                    
                    try:
                        url, name = future.result()
                        if url and name:
                            unique_key = f"{name} ({cam_id})"
                            cameras[unique_key] = url
                            range_count += 1
                            print(f"   ✅ 發現: {name} ({cam_id})")
                    except Exception as e:
                        pass
            
            print(f"   📊 {city_name} 發現 {range_count} 個監視器")
        
        return cameras

    def discover_all_cameras(self, selected_cities=None):
        """發現所有或指定縣市的監視器"""
        print("🎥 開始搜尋台灣監視器...")
        print("請耐心等待，這可能需要一些時間...")
        
        all_cameras = {}
        cities_to_search = selected_cities if selected_cities else self.city_codes.keys()
        
        for city_code in cities_to_search:
            city_name = self.city_codes[city_code]
            self.progress_count = 0
            
            try:
                cameras = self.discover_city_cameras(city_code, city_name)
                if cameras:
                    all_cameras[city_name] = cameras
                    print(f"🎉 {city_name} 完成：共 {len(cameras)} 個監視器")
                else:
                    print(f"❌ {city_name} 沒有發現監視器")
                
                # 在縣市之間稍作停頓
                time.sleep(1)
                
            except KeyboardInterrupt:
                print(f"\n⚠️ 使用者中斷，已完成 {len(all_cameras)} 個縣市")
                break
            except Exception as e:
                print(f"❌ {city_name} 搜尋時發生錯誤: {e}")
        
        return all_cameras

    def save_cameras_by_city(self, all_cameras):
        """按縣市儲存監視器清單"""
        # 創建輸出目錄
        output_dir = "cameras_by_city"
        os.makedirs(output_dir, exist_ok=True)
        
        # 儲存總覽
        total_count = sum(len(cameras) for cameras in all_cameras.values())
        
        # 創建總覽文件
        with open(os.path.join(output_dir, "00_全台總覽.txt"), "w", encoding="utf-8") as f:
            f.write(f"台灣監視器總覽 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"總計：{len(all_cameras)} 個縣市，{total_count} 個監視器\n\n")
            
            for city_name, cameras in sorted(all_cameras.items()):
                f.write(f"{city_name}：{len(cameras)} 個監視器\n")
        
        # 儲存各縣市詳細資料
        for city_name, cameras in all_cameras.items():
            if not cameras:
                continue
                
            # JSON 格式
            json_file = os.path.join(output_dir, f"{city_name}_cameras.json")
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(cameras, f, ensure_ascii=False, indent=2)
            
            # 可讀格式
            txt_file = os.path.join(output_dir, f"{city_name}_清單.txt")
            with open(txt_file, "w", encoding="utf-8") as f:
                f.write(f"{city_name}監視器清單 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n\n")
                f.write(f"總數：{len(cameras)} 個監視器\n\n")
                
                # 按編號排序
                sorted_cameras = []
                for name, url in cameras.items():
                    match = re.search(r'(\w+)-(\d+)', url)
                    cam_num = int(match.group(2)) if match else 999999
                    sorted_cameras.append((cam_num, name, url))
                
                sorted_cameras.sort(key=lambda x: x[0])
                
                for i, (cam_num, name, url) in enumerate(sorted_cameras, 1):
                    # 從名稱中移除編號部分
                    display_name = re.sub(r'\s*\(\w+-\d+\)$', '', name)
                    
                    f.write(f"{i:3d}. {display_name}\n")
                    f.write(f"     網址: {url}\n")
                    f.write("-" * 60 + "\n")
        
        # 儲存總JSON
        total_json = os.path.join(output_dir, "all_cameras.json")
        with open(total_json, "w", encoding="utf-8") as f:
            json.dump(all_cameras, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 結果已儲存到 '{output_dir}' 資料夾")
        print(f"   - 各縣市JSON和TXT檔案")
        print(f"   - all_cameras.json (完整資料)")
        print(f"   - 00_全台總覽.txt (統計摘要)")

    def analyze_all_cameras(self, all_cameras):
        """分析所有監視器統計"""
        print("\n📊 全台監視器分析報告")
        print("=" * 50)
        
        total_cameras = sum(len(cameras) for cameras in all_cameras.values())
        print(f"總監視器數量: {total_cameras} 個")
        print(f"涵蓋縣市數量: {len(all_cameras)} 個")
        print()
        
        # 按縣市統計
        print("📍 各縣市分佈:")
        city_stats = [(city, len(cameras)) for city, cameras in all_cameras.items()]
        city_stats.sort(key=lambda x: x[1], reverse=True)
        
        for city, count in city_stats:
            percentage = (count / total_cameras) * 100
            print(f"  {city}: {count} 個 ({percentage:.1f}%)")
        
        # 顯示前5大縣市
        print(f"\n🏆 監視器數量前5名:")
        for i, (city, count) in enumerate(city_stats[:5], 1):
            print(f"  {i}. {city}: {count} 個")

def main():
    print("🎥 台灣監視器統計程式 - 增強版")
    print("=" * 50)
    
    discovery = CameraDiscovery()
    
    print("\n請選擇搜尋模式:")
    print("1. 搜尋所有縣市（完整搜尋）")
    print("2. 搜尋指定縣市")
    print("3. 僅搜尋主要都會區（台北、新北、桃園、台中、台南、高雄）")
    
    choice = input("請輸入選項 (1-3): ").strip()
    
    if choice == "2":
        print("\n可用縣市代碼:")
        for code, name in discovery.city_codes.items():
            print(f"  {code}: {name}")
        
        input_codes = input("\n請輸入縣市代碼（用逗號分隔，如: tnn,khh,tpe): ").strip()
        selected_cities = [code.strip() for code in input_codes.split(",") if code.strip() in discovery.city_codes]
        
        if not selected_cities:
            print("❌ 沒有有效的縣市代碼")
            return
            
        print(f"✅ 將搜尋: {', '.join([discovery.city_codes[code] for code in selected_cities])}")
        
    elif choice == "3":
        selected_cities = ['tpe', 'ntpc', 'tao', 'tcg', 'tnn', 'khh']
        print("✅ 將搜尋主要都會區")
        
    else:
        selected_cities = None
        print("✅ 將搜尋所有縣市")
    
    # 開始搜尋
    start_time = time.time()
    all_cameras = discovery.discover_all_cameras(selected_cities)
    end_time = time.time()
    
    if not all_cameras:
        print("❌ 沒有發現任何監視器")
        return
    
    total_count = sum(len(cameras) for cameras in all_cameras.values())
    elapsed_time = end_time - start_time
    
    print(f"\n🎉 搜尋完成！")
    print(f"總共發現 {len(all_cameras)} 個縣市的 {total_count} 個監視器")
    print(f"耗時: {elapsed_time:.1f} 秒")
    
    # 儲存結果
    discovery.save_cameras_by_city(all_cameras)
    
    # 顯示分析
    discovery.analyze_all_cameras(all_cameras)
    
    print(f"\n📄 詳細清單請查看 'cameras_by_city' 資料夾")

if __name__ == "__main__":
    main()