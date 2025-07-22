import cv2
import numpy as np
import os
import glob
import shutil

def load_binary_lut(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()
    lut = [int(line.strip(), 2) for line in lines if line.strip()]
    return np.array(lut, dtype=np.uint16)  # Q8.10 格式，2040 個項

#----- 如果要換更亮或更暗，用LUT.py生其他的 weight.dat -----#
# 載入單一 gain LUT
gain_LUT = load_binary_lut("weight.dat")

# 固定 1D kernel（大小 = 7）
fixed_kernel_1d = np.array([1, 3, 7, 10, 7, 3, 1], dtype=np.float32)
pad = fixed_kernel_1d.size // 2

# 閾值
TH_Y = 32     # 垂直方向 threshold
TH_X = 1024   # 水平方向 threshold

#---------------- 改這裡就好 ------------------#
#(input 資料夾,              "my_alg_img/output 資料夾", "副檔名"),
# 資料集路徑
datasets = [
    # ("LOLdataset/eval15/low", "my_alg_img/LOL", "*.png"),
    # ("DICM",              "my_alg_img/DICM", "*.JPG"),
    # ("LIME",              "my_alg_img/LIME", "*.bmp"),
    # ("flood",              "my_alg_img/flood", "*.JPG"),
    ("normal",              "my_alg_img/normal_high", "*.JPG"),
]
#---------------- 改這裡就好 ------------------#

# datasets = [
#     ("DEMO_IMG/123", "my_alg_img", "*.jpg")
# ]

for input_folder, output_folder, pattern in datasets:
    os.makedirs(output_folder, exist_ok=True)
    for filepath in glob.glob(os.path.join(input_folder, pattern)):
        # 讀圖
        img = cv2.imread(filepath, cv2.IMREAD_COLOR).astype(np.float32)
        if img is None:
            print("無法讀取:", filepath)
            continue

        H, W, _ = img.shape
        # Step 1: 轉到Y Channel
        # weights = np.array([306, 601, 117], dtype=np.float32)
        # Gi = np.tensordot(img, weights, axes=([2], [0])) / 1024  # shape: (H, W)
        # Step 1: 計算 RGB 的最大值 → Gi 單通道
        Gi = np.max(img, axis=2).astype(np.float32)
        # Step 2: 垂直方向 7×1 卷積前，對 window 中差異過大的像素先替換
        Gi_pad = cv2.copyMakeBorder(Gi, pad, pad, 0, 0, borderType=cv2.BORDER_REFLECT_101)
        blur_y = np.zeros_like(Gi)
        for x in range(H):
            window = Gi_pad[x:x+2*pad+1, :]     # (7, W)
            center = Gi[x, :][None, :]          # (1, W)
            center_mat = np.tile(center, (7, 1))# (7, W)
            w = window.copy()
            diff = np.abs(w - center_mat)
            # 替換超過 TH_Y 的值
            w[diff >= TH_Y] = center_mat[diff >= TH_Y]
            # 加權求和
            blur_y[x, :] = (w * fixed_kernel_1d[:, None]).sum(axis=0)

        # Step 3: 水平方向 1×7 卷積前，對 window 中差異過大的像素先替換
        blur_pad = cv2.copyMakeBorder(blur_y, 0, 0, pad, pad, borderType=cv2.BORDER_REFLECT_101)
        blur_final = np.zeros_like(blur_y)
        for y in range(W):
            window = blur_pad[:, y:y+2*pad+1]   # (H, 7)
            center = blur_y[:, y][:, None]      # (H, 1)
            center_mat = np.tile(center, (1, 7))# (H, 7)
            w = window.copy()
            diff = np.abs(w - center_mat)
            # 替換超過 TH_X 的值
            w[diff >= TH_X] = center_mat[diff >= TH_X]
            # 加權求和
            blur_final[:, y] = (w * fixed_kernel_1d[None, :]).sum(axis=1)

        # Step 4: Normalization & 防除以零
        blur_norm = blur_final / 128.0
        safe_blur = np.maximum(blur_norm, 1.0)

        # Step 5: 四捨五入取整、Clip 到 [1,2040] → LUT index
        safe_int = np.floor(safe_blur).astype(np.int32)
        safe_int = np.clip(safe_int, 1, 2040)

        # Step 6: 查表 (Q8.10 → float)
        gain_map = gain_LUT[safe_int - 1].astype(np.float32) / (1 << 10)

        # Step 7: 套用增益
        gain_map_3c = np.repeat(gain_map[:, :, None], 3, axis=2)
        img_enhance = np.clip(img * gain_map_3c, 0, 255).astype(np.uint8)

        # Step 8: 儲存
        out_path = os.path.join(output_folder, os.path.basename(filepath))
        cv2.imwrite(out_path, img_enhance)
        # print(f"✅ 處理完成: {filepath} → {out_path}")

# 複製 LUT 檔案到 my_alg_img
os.makedirs("my_alg_img", exist_ok=True)
shutil.copy("weight.dat", "my_alg_img/weight.dat")
print("✅ 已將 weight.dat 複製到 my_alg_img/")
