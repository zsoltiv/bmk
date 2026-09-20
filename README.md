# Bürokratikus Műegyetemi Kitakaró

Automatizált dokumentum kitakarás BME-s pályázatokhoz.

## Futtatás

```
python3 -m bmk [Dokumentum] [kitakaró_folyamat] [kimenet]
```

## Támogatott dokumentum típusok

|Név|`kitakaró_folyamat`|
|---|-------------------|
|Unicredit elektronikus számlakivonat|`unicredit`|
|OTP elektronikus számlakivonat|`otp`|
|MBH szkennelt bankszámlakivonat|`mbh-ocr`|
|Erste elektronikus számlakivonat|`erste`|

## Függőségek

- Python 3.14
- pymupdf

Ezen túl szkennelt dokumentumok feldolgozásához:

- OpenCV
- numpy
- tesseract-data-hun


## Licensz

GPL
