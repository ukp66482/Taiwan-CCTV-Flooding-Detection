# 監視器爬蟲程式使用說明

本專案能自動從 `1968services.tw` 擷取台灣各地路口攝影機的即時影像。

## 1.擷取單一縣市攝影機圖片

```shell
python capture.py --json cameras_by_city/台南市_cameras.json
```

## 2.多城市同時擷取（Multiprocess）

```shell
python run_all.py
```
