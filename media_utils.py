import webview
import threading
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
import re
import requests
import urllib3
from bs4 import BeautifulSoup
import json

# SSL 인증서 경고 무시
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def find_key_recursive(obj, target_key):
    """JSON 객체에서 키를 재귀적으로 찾음"""
    if isinstance(obj, dict):
        if target_key in obj and obj[target_key]:
            return obj[target_key]
        for k, v in obj.items():
            result = find_key_recursive(v, target_key)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = find_key_recursive(item, target_key)
            if result:
                return result
    return None

def run_webview(url, title, x=None, y=None):
    """별도 프로세스에서 pywebview 실행"""
    try:
        # YouTube Embed URL인 경우 로컬 서버를 통해 iframe으로 서빙
        if "youtube.com/embed/" in url:
            class VideoHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    
                    html_content = f"""
                    <!DOCTYPE html>
                    <html style="width:100%; height:100%; margin:0; padding:0; overflow:hidden;">
                    <head>
                        <meta name="referrer" content="strict-origin-when-cross-origin" />
                    </head>
                    <body style="width:100%; height:100%; margin:0; padding:0; background-color:black;">
                        <iframe 
                            width="100%" 
                            height="100%" 
                            src="{url}" 
                            frameborder="0" 
                            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
                            allowfullscreen>
                        </iframe>
                    </body>
                    </html>
                    """
                    self.wfile.write(html_content.encode('utf-8'))
                
                def log_message(self, format, *args):
                    pass

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
            sock.close()

            server = HTTPServer(('127.0.0.1', port), VideoHandler)
            thread = threading.Thread(target=server.serve_forever)
            thread.daemon = True
            thread.start()

            final_url = f'http://127.0.0.1:{port}'
        else:
            final_url = url

        webview.create_window(title, final_url, width=800, height=450, x=x, y=y, on_top=True)
        
        user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        webview.start(user_agent=user_agent, debug=False)
    except Exception as e:
        print(f"Webview error: {e}")

def parse_media_url(url):
    """URL에서 미디어 정보 추출"""
    youtube_patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})',
        r'm\.youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})'
    ]

    for pattern in youtube_patterns:
        match = re.search(pattern, url)
        if match:
            return {'platform': 'youtube', 'id': match.group(1), 'url': url}

    if 'chzzk.naver.com' in url:
        return {'platform': 'chzzk', 'url': url}

    if 'twitch.tv' in url or 'clips.twitch.tv' in url:
        return {'platform': 'twitch', 'url': url}

    return None

def get_thumbnail_url(media_info):
    """썸네일 URL 가져오기"""
    platform = media_info['platform']

    if platform == 'youtube':
        return f"https://img.youtube.com/vi/{media_info['id']}/mqdefault.jpg"

    elif platform == 'chzzk':
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Referer': 'https://chzzk.naver.com/',
                'Accept': 'application/json, text/plain, */*',
            }
            
            url = media_info['url']
            
            # 1. 비디오 (v2 API)
            video_match = re.search(r'/video/(\d+)', url)
            if video_match:
                video_no = video_match.group(1) 
                api_url = f"https://api.chzzk.naver.com/service/v2/videos/{video_no}"
                try:
                    res = requests.get(api_url, headers=headers, timeout=3, verify=False)
                    if res.status_code == 200:
                        content = res.json().get('content', {})
                        thumb = content.get('thumbnailImageUrl') or (content.get('video') or {}).get('thumbnailImageUrl')
                        if thumb: return thumb
                except: pass

            # 2. 클립 (v1 API)
            clip_match = re.search(r'/clips/([a-zA-Z0-9_-]+)', url)
            if clip_match:
                clip_uid = clip_match.group(1)
                api_url = f"https://api.chzzk.naver.com/service/v1/clips/{clip_uid}/detail"
                try:
                    res = requests.get(api_url, headers=headers, timeout=3, verify=False)
                    if res.status_code == 200:
                        content = res.json().get('content', {})
                        thumb = content.get('thumbnailImageUrl')
                        if thumb: return thumb
                except: pass

            # 3. 채널/라이브 (v2 API)
            id_match = re.search(r'([a-fA-F0-9]{32})', url)
            if id_match:
                channel_id = id_match.group(1)
                api_url = f"https://api.chzzk.naver.com/service/v2/channels/{channel_id}/live-detail"
                try:
                    res = requests.get(api_url, headers=headers, timeout=5, verify=False)
                    if res.status_code == 200:
                        content = res.json().get('content', {})
                        if content.get('liveImageUrl'):
                            return content['liveImageUrl'].replace('{type}', '480')
                        if content.get('channel') and content['channel'].get('channelImageUrl'):
                            return content['channel']['channelImageUrl']
                except: pass
                
                # Fallback
                api_url_basic = f"https://api.chzzk.naver.com/service/v2/channels/{channel_id}"
                try:
                    res = requests.get(api_url_basic, headers=headers, timeout=5, verify=False)
                    if res.status_code == 200:
                        content = res.json().get('content', {})
                        if content.get('channelImageUrl'):
                            return content['channelImageUrl']
                except: pass

            # 4. 스크래핑 & __NEXT_DATA__
            response = requests.get(url, headers=headers, timeout=5, verify=False)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # __NEXT_DATA__
            script_tag = soup.find('script', id='__NEXT_DATA__')
            if script_tag:
                try:
                    data = json.loads(script_tag.string)
                    thumb = find_key_recursive(data, 'thumbnailImageUrl')
                    if thumb: return thumb
                except: pass

            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                return og_image['content']
        except Exception as e:
            print(f"[DEBUG] Failed to get thumbnail: {e}")

    elif platform == 'twitch':
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
            response = requests.get(media_info['url'], headers=headers, timeout=5)
            soup = BeautifulSoup(response.text, 'html.parser')
            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                return og_image['content']
        except Exception as e:
            print(f"[DEBUG] Twitch thumbnail fetch failed: {e}")

    return None

def get_media_metadata(media_info):
    """미디어 메타데이터(제목, 채널명, 재생시간) 가져오기"""
    metadata = {'title': '', 'channel': '', 'duration': ''}
    platform = media_info['platform']
    url = media_info['url']

    if platform not in ['youtube', 'chzzk']:
        return metadata

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Referer': 'https://chzzk.naver.com/',
            'Accept': 'application/json, text/plain, */*',
        }
        
        if platform == 'youtube':
            res = requests.get(url, headers=headers, timeout=3, verify=False)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                og_title = soup.find('meta', property='og:title')
                metadata['title'] = og_title['content'] if og_title else ""
                
                author_tag = soup.find(itemprop='author')
                if author_tag:
                    name_tag = author_tag.find(itemprop='name')
                    if name_tag:
                        metadata['channel'] = name_tag.get('content') or name_tag.get_text(strip=True)
                
                dur_meta = soup.find('meta', itemprop='duration')
                if dur_meta:
                    iso_dur = dur_meta['content']
                    match = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_dur)
                    if match:
                        h, m, s = match.groups()
                        h, m, s = int(h or 0), int(m or 0), int(s or 0)
                        metadata['duration'] = f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"

        elif platform == 'chzzk':
            # 4. Fallback: __NEXT_DATA__ 파싱 (가장 확실한 방법)
            try:
                res = requests.get(url, headers=headers, timeout=3, verify=False)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, 'html.parser')
                    script_tag = soup.find('script', id='__NEXT_DATA__')
                    if script_tag:
                        data = json.loads(script_tag.string)
                        
                        metadata['title'] = find_key_recursive(data, 'clipTitle') or \
                                            find_key_recursive(data, 'videoTitle') or \
                                            find_key_recursive(data, 'liveTitle')
                        
                        metadata['channel'] = find_key_recursive(data, 'channelName')
                        metadata['duration'] = "CHZZK"
            except: pass

    except Exception as e:
        print(f"[DEBUG] Metadata fetch failed: {e}")

    return metadata