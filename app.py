from flask import Flask, render_template, request, jsonify, session
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
import os
import time
import threading
import json
import tempfile
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.urandom(24)

# YouTube API credentials
SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

# Global variables
comment_thread = None
should_comment = False
commented_videos = set()  # Yorum yapılan videoları takip etmek için
log_entries = []  # Log kayıtlarını tutmak için

def get_data_dir():
    """Get the data directory based on environment"""
    if 'PYTHONANYWHERE_DOMAIN' in os.environ:
        # PythonAnywhere'de isek
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    else:
        # Lokal geliştirme ortamında isek
        return tempfile.gettempdir()

# Uygulama başladığında data klasörünü oluştur
if 'PYTHONANYWHERE_DOMAIN' in os.environ:
    data_dir = get_data_dir()
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

def save_credentials_temp(client_id, client_secret):
    credentials = {
        "installed": {
            "client_id": client_id,
            "project_id": "youtube-commenter",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": client_secret,
            "redirect_uris": ["http://localhost"]
        }
    }
    
    data_dir = get_data_dir()
    credentials_path = os.path.join(data_dir, 'client_secrets.json')
    
    with open(credentials_path, 'w') as f:
        json.dump(credentials, f)
    
    return credentials_path

def get_youtube_credentials():
    creds = None
    data_dir = get_data_dir()
    token_path = os.path.join(data_dir, 'token.pickle')
    
    if os.path.exists(token_path):
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            credentials_path = os.path.join(data_dir, 'client_secrets.json')
            if not os.path.exists(credentials_path):
                return None
                
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)
    
    return creds

def add_log_entry(video_id, video_title, comment_text, success=True, error_message=None):
    global log_entries
    entry = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'video_id': video_id,
        'video_title': video_title,
        'video_url': f'https://youtube.com/watch?v={video_id}',
        'comment': comment_text,
        'success': success,
        'error_message': error_message
    }
    log_entries.insert(0, entry)  # En yeni log en üstte olsun
    if len(log_entries) > 100:  # Maksimum 100 log tutalım
        log_entries.pop()

def comment_worker(search_query, comment_text, interval):
    global should_comment, commented_videos
    credentials = get_youtube_credentials()
    
    if not credentials:
        add_log_entry("", "Kimlik Doğrulama Hatası", comment_text, 
                     success=False, error_message="YouTube kimlik bilgileri bulunamadı")
        return
        
    youtube = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)
    
    # Temp dosyadan önceki yorumları yükle
    data_dir = get_data_dir()
    comments_file = os.path.join(data_dir, 'commented_videos.json')
    if os.path.exists(comments_file):
        with open(comments_file, 'r') as f:
            commented_videos = set(json.load(f))
    
    while should_comment:
        try:
            # Her döngüde 5 yeni video ara
            search_response = youtube.search().list(
                q=search_query,
                part='id,snippet',
                maxResults=5,
                type='video',
                order='date'
            ).execute()

            if not search_response.get('items'):
                add_log_entry("", "Arama Sonucu Bulunamadı", comment_text,
                            success=False, error_message=f"'{search_query}' için video bulunamadı")
                time.sleep(interval * 60)
                continue

            for video in search_response.get('items', []):
                if not should_comment:
                    break
                    
                video_id = video['id']['videoId']
                video_title = video['snippet']['title']
                
                if video_id in commented_videos:
                    continue
                
                try:
                    video_response = youtube.videos().list(
                        part='status',
                        id=video_id
                    ).execute()
                    
                    if not video_response.get('items'):
                        add_log_entry(video_id, video_title, comment_text,
                                    success=False, error_message="Video bulunamadı")
                        continue
                        
                    video_status = video_response['items'][0]['status']
                    if not video_status.get('commentable', True):
                        add_log_entry(video_id, video_title, comment_text,
                                    success=False, error_message="Video yorumlara kapalı")
                        continue

                    youtube.commentThreads().insert(
                        part="snippet",
                        body={
                            "snippet": {
                                "videoId": video_id,
                                "topLevelComment": {
                                    "snippet": {
                                        "textOriginal": comment_text
                                    }
                                }
                            }
                        }
                    ).execute()
                    
                    commented_videos.add(video_id)
                    
                    # Yorum yapılan videoları kaydet
                    with open(comments_file, 'w') as f:
                        json.dump(list(commented_videos), f)
                    
                    # Log dosyasını kaydet
                    add_log_entry(video_id, video_title, comment_text, success=True)
                    
                    # Log dosyasını diske yaz
                    log_file = os.path.join(data_dir, 'comment_logs.json')
                    with open(log_file, 'w', encoding='utf-8') as f:
                        json.dump(log_entries, f, ensure_ascii=False, indent=2)
                    
                except Exception as e:
                    error_msg = str(e)
                    if "quotaExceeded" in error_msg:
                        error_msg = "YouTube API kotası aşıldı. Lütfen yarın tekrar deneyin."
                        should_comment = False
                    elif "commentsDisabled" in error_msg:
                        error_msg = "Video yorumlara kapalı"
                    elif "invalidCredentials" in error_msg:
                        error_msg = "Geçersiz kimlik bilgileri. Lütfen yeniden giriş yapın."
                        should_comment = False
                    elif "not connected to Google+" in error_msg or "ineligibleAccount" in error_msg:
                        error_msg = "YouTube hesabınız yorum yapmaya uygun değil. Lütfen YouTube kanalınızı kontrol edin."
                        should_comment = False
                    
                    add_log_entry(video_id, video_title, comment_text,
                                success=False, error_message=error_msg)
                    
                    # Hata loglarını da diske yaz
                    log_file = os.path.join(data_dir, 'comment_logs.json')
                    with open(log_file, 'w', encoding='utf-8') as f:
                        json.dump(log_entries, f, ensure_ascii=False, indent=2)
                    
                    if not should_comment:
                        break
            
            time.sleep(interval * 60)

        except Exception as e:
            error_msg = str(e)
            if "quotaExceeded" in error_msg:
                error_msg = "YouTube API kotası aşıldı. Lütfen yarın tekrar deneyin."
                should_comment = False
            elif "invalidCredentials" in error_msg:
                error_msg = "Geçersiz kimlik bilgileri. Lütfen yeniden giriş yapın."
                should_comment = False
            elif "not connected to Google+" in error_msg or "ineligibleAccount" in error_msg:
                error_msg = "YouTube hesabınız yorum yapmaya uygun değil. Lütfen YouTube kanalınızı kontrol edin."
                should_comment = False
            
            add_log_entry("", "API Hatası", comment_text,
                         success=False, error_message=error_msg)
            
            # Hata loglarını diske yaz
            log_file = os.path.join(data_dir, 'comment_logs.json')
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(log_entries, f, ensure_ascii=False, indent=2)
            
            if not should_comment:
                break
            time.sleep(60)

@app.route('/')
def home():
    data_dir = get_data_dir()
    credentials_path = os.path.join(data_dir, 'client_secrets.json')
    has_credentials = os.path.exists(credentials_path)
    
    # Log dosyasını oku
    log_file = os.path.join(data_dir, 'comment_logs.json')
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            global log_entries
            log_entries = json.load(f)
    
    if has_credentials:
        with open(credentials_path, 'r') as f:
            creds = json.load(f)
            client_id = creds['installed']['client_id']
            client_secret = creds['installed']['client_secret']
    else:
        client_id = ''
        client_secret = ''
    
    return render_template('index.html', 
                         has_credentials=has_credentials,
                         client_id=client_id,
                         client_secret=client_secret,
                         log_entries=log_entries,
                         is_running=bool(comment_thread and comment_thread.is_alive()))

@app.route('/save_credentials', methods=['POST'])
def save_credentials():
    client_id = request.json.get('client_id')
    client_secret = request.json.get('client_secret')
    
    if not client_id or not client_secret:
        return jsonify({'error': 'Missing credentials'}), 400
    
    try:
        credentials_path = save_credentials_temp(client_id, client_secret)
        return jsonify({'message': 'Credentials saved successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/start_commenting', methods=['POST'])
def start_commenting():
    global comment_thread, should_comment, commented_videos
    
    data = request.json
    search_query = data.get('search_query')
    comment_text = data.get('comment_text')
    interval = int(data.get('interval', 5))
    
    if not all([search_query, comment_text]):
        return jsonify({'error': 'Missing required parameters'}), 400
    
    if comment_thread and comment_thread.is_alive():
        return jsonify({'error': 'Comment bot is already running'}), 400
    
    should_comment = True
    commented_videos.clear()  # Yeni başlangıçta listeyi temizle
    comment_thread = threading.Thread(
        target=comment_worker,
        args=(search_query, comment_text, interval)
    )
    comment_thread.start()
    
    return jsonify({'message': 'Comment bot started successfully'})

@app.route('/stop_commenting', methods=['POST'])
def stop_commenting():
    global should_comment
    should_comment = False
    return jsonify({'message': 'Comment bot will stop after current operation'})

@app.route('/get_logs', methods=['GET'])
def get_logs():
    return jsonify({
        'logs': log_entries,
        'is_running': bool(comment_thread and comment_thread.is_alive())
    })

@app.route('/reset_google_auth', methods=['POST'])
def reset_google_auth():
    try:
        temp_dir = tempfile.gettempdir()
        token_path = os.path.join(temp_dir, 'token.pickle')
        
        if os.path.exists(token_path):
            os.remove(token_path)
            
        return jsonify({'message': 'Google hesap bilgileri başarıyla sıfırlandı'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True) 