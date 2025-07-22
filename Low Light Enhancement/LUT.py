import cv2
import numpy as np
import os
import glob

# 產生 gain_map LUT（Q8.10，整數 + 小數）
# t 最高到1(最亮) 最低到0
def generate_gain_LUT(m_min=1, m_max=2040, frac_bits=10,t = 1):
    LUT = []
    for m in range(m_min, m_max + 1):
        raw = 4080.0 / m - 1.0
        raw = max(0.0, raw)
        gain = np.sqrt(raw)
        gain = gain * t + (1-t)
        fixed_point = int((gain * (1 << frac_bits)))  # Q8.10
        LUT.append(fixed_point)
    return np.array(LUT, dtype=np.uint16)

# 輸出 LUT 為 .dat 檔（二進位，每行 16 位補齊）
def save_LUT_to_dat_binary(lut_array, filename):
    with open(filename, "w") as f:
        for val in lut_array:
            bin_str = format(val, '016b')  # 轉成二進位並補足16位
            f.write(f"{bin_str}\n")

# 建立 LUT 並儲存
gain_LUT = generate_gain_LUT()
save_LUT_to_dat_binary(gain_LUT, "weight_1.dat")