# YouTube Otomatik Yorum Botu

YouTube'da belirli arama sorgularına göre videolar bulup otomatik yorum yapan web uygulaması.

## Özellikler

- YouTube video araması
- Otomatik yorum yapma
- Özelleştirilebilir yorum aralığı
- Yorum yapılan videoları takip etme
- Detaylı log sistemi
- Kullanıcı dostu arayüz

## Kurulum

1. Gerekli paketleri yükleyin:
```bash
pip install -r requirements.txt
```

2. YouTube API kimlik bilgilerini ayarlayın:
   - [Google Cloud Console](https://console.cloud.google.com)'a gidin
   - Yeni bir proje oluşturun
   - YouTube Data API v3'ü etkinleştirin
   - OAuth 2.0 kimlik bilgileri oluşturun

3. Uygulamayı çalıştırın:
```bash
python app.py
```

## Kullanım

1. Web arayüzünden YouTube API kimlik bilgilerini girin
2. Arama sorgusunu ve yorum metnini belirleyin
3. Yorum aralığını ayarlayın
4. Başlat butonuna tıklayın

## Teknik Detaylar

- Flask web framework
- YouTube Data API v3
- OAuth 2.0 kimlik doğrulama
- Temp dosya sistemi ile yorum takibi
- Çoklu iş parçacığı desteği

## Güvenlik

- API anahtarları ve token'lar güvenli şekilde saklanır
- Temp klasörü kullanılır
- OAuth 2.0 güvenli kimlik doğrulama

## Lisans

MIT License 