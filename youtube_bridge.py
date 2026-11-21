"""Owner-authorized YouTube connection and checked Studio uploads.

No credentials are returned in messages, URLs, or logs. Google consent is
completed on Google's website and the code is exchanged on the server.
"""
import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path

CALLBACK = 'https://smart-prime.onrender.com/youtube/callback'
SCOPES = ['https://www.googleapis.com/auth/youtube.upload',
          'https://www.googleapis.com/auth/youtube.readonly',
          'https://www.googleapis.com/auth/yt-analytics.readonly']


class YouTubeError(Exception):
    """Only safe, owner-readable messages may be raised here."""


class YouTubeBridge:
    def __init__(self, get, put, env=None, clock=time.time):
        self.get, self.put = get, put
        self.env = os.environ if env is None else env
        self.clock = clock
        self.pending = {}
        self.backups = {}
        self.auth_lock = threading.Lock()
        self.upload_lock = threading.Lock()

    def configured(self):
        return bool(self.env.get('YT_CLIENT_ID') and self.env.get('YT_CLIENT_SECRET'))

    def start(self):
        if not self.configured():
            raise YouTubeError('Google OAuth client settings are missing in Render.')
        from google_auth_oauthlib.flow import Flow
        config = {'web': {'client_id': self.env['YT_CLIENT_ID'],
                          'client_secret': self.env['YT_CLIENT_SECRET'],
                          'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                          'token_uri': 'https://oauth2.googleapis.com/token',
                          'redirect_uris': [CALLBACK]}}
        flow = Flow.from_client_config(config, scopes=SCOPES, autogenerate_code_verifier=True)
        flow.redirect_uri = CALLBACK
        state = secrets.token_urlsafe(32)
        url, _ = flow.authorization_url(state=state, access_type='offline', prompt='consent')
        with self.auth_lock:
            self.pending.clear()  # A new owner request invalidates the previous link.
            self.pending[state] = (self.clock()+600, flow)
        return url

    def finish(self, state, code):
        with self.auth_lock:
            pending = self.pending.pop(state, None) if isinstance(state, str) else None
        if not pending or pending[0] < self.clock() or not code:
            raise YouTubeError('This connection link expired or was already used. Request /connect_youtube again.')
        try:
            flow = pending[1]
            flow.fetch_token(code=code, timeout=30)
            creds = flow.credentials
            if not creds.refresh_token:
                raise YouTubeError('Google did not grant offline access. The connection was not saved.')
            channel = self.channel(creds)
            self.put('yt_token', creds.to_json())
            self.put('yt_channel_id', channel['id'])
            return channel
        except YouTubeError:
            raise
        except Exception:
            raise YouTubeError('Google authorization could not be completed. Check the OAuth client and enabled YouTube APIs.') from None

    def persistent_token(self):
        raw = self.env.get('YT_TOKEN', '')
        if raw:
            return raw
        path = Path(self.env.get('YT_TOKEN_FILE', '/etc/secrets/YT_TOKEN.json'))
        try:
            return path.read_text()
        except OSError:
            return ''

    def backup_ticket(self):
        """Short-lived browser-only credential transfer to Render secret storage."""
        raw = self.get('yt_token')
        if not raw:
            raise YouTubeError('No new connection is available to save.')
        ticket = secrets.token_urlsafe(32)
        with self.auth_lock:
            self.backups.clear()
            self.backups[ticket] = (self.clock()+600, raw)
        return ticket

    def take_backup(self, ticket):
        with self.auth_lock:
            item = self.backups.pop(ticket, None)
        if not item or item[0] < self.clock():
            raise YouTubeError('The secure connection download expired or was already used.')
        return item[1]

    def credentials(self):
        raw = self.get('yt_token') or self.persistent_token()
        if not raw:
            raise YouTubeError('YouTube is not connected. Use /connect_youtube.')
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            creds = Credentials.from_authorized_user_info(json.loads(raw))
            if not creds.valid and creds.refresh_token:
                creds.refresh(Request())
                self.put('yt_token', creds.to_json())
            if not creds.valid:
                raise ValueError('Invalid credential')
            return creds
        except Exception:
            raise YouTubeError('YouTube authorization is expired or unavailable. Reconnect with /connect_youtube.') from None

    def client(self, creds):
        from googleapiclient.discovery import build
        return build('youtube', 'v3', credentials=creds, cache_discovery=False)

    def channel(self, creds=None):
        creds = creds or self.credentials()
        if not creds.has_scopes(SCOPES[:2]):
            raise YouTubeError('Google must grant upload and channel-read permission. Reconnect YouTube.')
        try:
            items = self.client(creds).channels().list(part='snippet', mine=True).execute()['items']
            if len(items) != 1:
                raise YouTubeError('Select the FIRST STAGE channel during Google authorization.')
            channel = items[0]
            expected_id = self.env.get('YT_CHANNEL_ID') or self.get('yt_channel_id')
            expected_handle = self.env.get('YT_EXPECTED_HANDLE', '@FirstStageOfficial').lower().lstrip('@')
            actual_handle = channel['snippet'].get('customUrl', '').lower().lstrip('@')
            if (expected_id and channel['id'] != expected_id) or (not expected_id and actual_handle != expected_handle):
                raise YouTubeError('The authorized channel is not FIRST STAGE. No upload was made; reconnect using the correct channel.')
            return {'id': channel['id'], 'title': channel['snippet']['title'], 'handle': actual_handle}
        except YouTubeError:
            raise
        except Exception:
            raise YouTubeError('Could not verify the YouTube channel. Check Google authorization and the YouTube Data API.') from None

    def status(self):
        channel = self.channel()
        try:
            current = json.loads(self.get('yt_token') or self.persistent_token())
            persistent = json.loads(self.persistent_token() or '{}')
            durable = bool(current.get('refresh_token') and current.get('refresh_token') == persistent.get('refresh_token'))
        except (ValueError, TypeError):
            durable = False
        return {**channel, 'persistent': durable}

    def auto_enabled(self):
        return (self.get('yt_auto_publish') or self.env.get('YT_AUTO_PUBLISH', '0')) == '1'

    def upload(self, result, title, report, stopped=lambda: False):
        if not self.upload_lock.acquire(blocking=False):
            raise YouTubeError('A YouTube upload is already running.')
        try:
            return self._upload(result, title, report, stopped)
        finally:
            self.upload_lock.release()

    def _upload(self, result, title, report, stopped):
        if (report.get('technical_checks') != 'passed'
                or not str(report.get('editorial_check', '')).startswith('Source quotes matched; second model pass approved.')
                or not str(report.get('rendered_picture_review', '')).startswith('Passed separate review')):
            raise YouTubeError('Only a completed Studio video that passed evidence, technical and final picture checks can be uploaded.')
        result = Path(result)
        video = result/'FIRST_STAGE.mp4'
        description = (result/'FIRST_STAGE_description.txt').read_text(encoding='utf-8')
        if not title.strip() or len(title)>100 or len(description)>5000:
            raise YouTubeError('YouTube metadata exceeds its limits. Credits were not truncated; upload stopped.')
        with video.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        key = 'yt_upload_'+digest
        prior = self.get(key)
        if prior:
            data = json.loads(prior)
            if data.get('id'):
                return data
            raise YouTubeError('An earlier upload of this video has an uncertain outcome. Check YouTube Studio before retrying; no duplicate was sent.')
        creds = self.credentials()
        channel = self.channel(creds)
        if stopped():
            raise YouTubeError('Upload stopped before sending the video.')
        from googleapiclient.http import MediaFileUpload
        body = {'snippet': {'title': title, 'description': description, 'categoryId': '28', 'defaultLanguage': 'en'},
                'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False, 'containsSyntheticMedia': True}}
        request = self.client(creds).videos().insert(part='snippet,status', body=body,
            media_body=MediaFileUpload(str(video), mimetype='video/mp4', chunksize=1024*1024, resumable=True))
        # Reserve before the first request: an uncertain acknowledgement must never
        # cause a blind duplicate/publication on the next command.
        self.put(key, json.dumps({'state': 'started', 'channel_id': channel['id']}))
        try:
            response = None
            while response is None:
                if stopped():
                    raise YouTubeError('Upload stopped. Check YouTube Studio for a partial upload before retrying.')
                _, response = request.next_chunk(num_retries=0)
            outcome = {'id': response['id'], 'privacy': response.get('status', {}).get('privacyStatus', 'unconfirmed'),
                       'upload_status': response.get('status', {}).get('uploadStatus', 'unconfirmed'), 'channel_id': channel['id']}
            self.put(key, json.dumps(outcome))
            return outcome
        except YouTubeError:
            raise
        except Exception:
            raise YouTubeError('YouTube did not confirm the upload. The finished video is saved; check YouTube Studio before retrying to avoid duplicates.') from None
