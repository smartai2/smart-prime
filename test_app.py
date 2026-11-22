import asyncio
import importlib.util
import os
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def bot_app(tmp_path,monkeypatch):
    path=Path(__file__).with_name('app.py')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('SMART_TOKEN','123456789:TEST_TOKEN_FOR_LOCAL_TESTS_ONLY')
    monkeypatch.setenv('BRAIN_API_KEY','')
    spec=importlib.util.spec_from_file_location('studio_app_under_test',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.STUDIO_MIN_GAP=0
    yield module
    module._db.close()


def test_delivery_routes_and_expiry(bot_app,tmp_path):
    result=tmp_path/'result';result.mkdir()
    for name in bot_app.SHORT_DOWNLOAD_TYPES:
        (result/name).write_bytes(b'fixture')
    url=bot_app.save_studio_downloads(result,{'title':'Test'},{'duration_seconds':35})
    handle=url.rsplit('/',1)[-1]
    client=TestClient(bot_app.server)
    response=client.get(f'/short-download/{handle}/FIRST_STAGE.mp4')
    assert response.status_code==200
    assert response.headers['cache-control']=='private, no-store'
    assert response.headers['content-type']=='video/mp4'
    assert client.get(f'/short-download/{handle}/FIRST_STAGE_package.zip').status_code==200
    assert client.get(f'/short-download/{handle}/latest.json').status_code==404
    assert client.get('/short-download/not-valid/FIRST_STAGE.mp4').status_code==404
    folder=bot_app.SHORT_EXPORT_ROOT/handle
    old=time.time()-bot_app.SHORT_DOWNLOAD_TTL-1
    os.utime(folder,(old,old))
    assert client.get(f'/short-download/{handle}/FIRST_STAGE.mp4').status_code==404
    assert handle not in client.get('/').text
    assert client.head('/').status_code==200


def test_frozen_and_duplicate_jobs_do_not_start(bot_app):
    reply=AsyncMock()
    u=SimpleNamespace(message=SimpleNamespace(reply_text=reply))
    state={}
    c=SimpleNamespace(application=SimpleNamespace(bot_data=state))
    bot_app.set_setting('frozen','1')
    asyncio.run(bot_app._queue_topic_video(u,c,'Starship'))
    assert 'Frozen' in reply.call_args.args[0]
    bot_app.set_setting('frozen','0')
    state['topic_video_task']=SimpleNamespace(done=lambda:False)
    asyncio.run(bot_app._queue_topic_video(u,c,'Starship'))
    assert 'already in progress' in reply.call_args.args[0]


def test_private_commands_ignore_other_users(bot_app):
    bot_app.set_setting('owner_chat_id',bot_app.JUAN_CHAT_ID)
    u=SimpleNamespace(effective_chat=SimpleNamespace(id=1),message=SimpleNamespace(reply_text=AsyncMock()))
    asyncio.run(bot_app.cmd_video_latest(u,SimpleNamespace()))
    u.message.reply_text.assert_not_called()


def test_youtube_callback_rejects_invalid_state_without_echoing_codes(bot_app):
    client=TestClient(bot_app.server)
    response=client.get('/youtube/callback?state=invalid&code=PRIVATE_AUTH_CODE')
    assert response.status_code==400
    assert 'PRIVATE_AUTH_CODE' not in response.text
    assert response.headers['cache-control']=='no-store'
    assert response.headers['referrer-policy']=='no-referrer'


def test_youtube_callback_removes_code_from_success_url(bot_app,monkeypatch):
    seen=[]
    monkeypatch.setattr(bot_app.youtube,'finish',lambda state,code:seen.append((state,code)))
    monkeypatch.setattr(bot_app.youtube,'backup_ticket',lambda:'TEST_SETUP_COOKIE')
    response=TestClient(bot_app.server).get('/youtube/callback?state=valid&code=PRIVATE_AUTH_CODE',follow_redirects=False)
    assert response.status_code==303
    assert response.headers['location']=='/youtube/connected'
    assert seen==[('valid','PRIVATE_AUTH_CODE')]
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'Secure' in response.headers['set-cookie']
    assert 'SameSite=strict' in response.headers['set-cookie']


def test_connection_backup_requires_secure_cookie_and_is_single_use(bot_app):
    client=TestClient(bot_app.server,base_url='https://smart-prime.onrender.com')
    assert client.get('/youtube/connection-backup').status_code==403
    bot_app.set_setting('yt_token','PRIVATE_FIXTURE_JSON')
    ticket=bot_app.youtube.backup_ticket()
    client.cookies.set('yt_setup',ticket)
    response=client.get('/youtube/connection-backup')
    assert response.status_code==200 and response.text=='PRIVATE_FIXTURE_JSON'
    assert response.headers['cache-control']=='no-store'
    assert 'attachment' in response.headers['content-disposition']
    assert client.get('/youtube/connection-backup').status_code==403


def test_youtube_controls_ignore_other_users_and_export_no_credentials(bot_app):
    bot_app.set_setting('owner_chat_id',bot_app.JUAN_CHAT_ID)
    u=SimpleNamespace(effective_chat=SimpleNamespace(id=1),message=SimpleNamespace(reply_text=AsyncMock()))
    for fn in (bot_app.cmd_yt_status,bot_app.cmd_yt_upload,bot_app.cmd_connect_youtube,bot_app.cmd_yt_auto):
        asyncio.run(fn(u,SimpleNamespace()))
    u.message.reply_text.assert_not_called()
    u.effective_chat.id=int(bot_app.JUAN_CHAT_ID)
    bot_app.set_setting('yt_token','PRIVATE_REFRESH_TOKEN')
    asyncio.run(bot_app.cmd_yt_export(u,SimpleNamespace()))
    assert 'PRIVATE_REFRESH_TOKEN' not in u.message.reply_text.call_args.args[0]


def test_youtube_upload_failure_does_not_invalidate_delivered_video(bot_app,monkeypatch):
    def fail(*args):raise bot_app.YouTubeError('Not connected')
    monkeypatch.setattr(bot_app.youtube,'upload',fail)
    u=SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock()))
    c=SimpleNamespace(application=SimpleNamespace(bot_data={}))
    asyncio.run(bot_app.publish_studio_result(u,c,Path('.'),'Title',{}))
    assert 'completed Telegram video remains available' in u.message.reply_text.call_args.args[0]


@pytest.mark.parametrize('enabled',[False,True])
def test_successful_studio_job_uploads_once_only_when_enabled(bot_app,monkeypatch,tmp_path,enabled):
    events=[]
    async def produce(*args):
        events.append('production')
        return tmp_path,{'title':'Checked video'},{'duration_seconds':40,'bytes':100}
    async def deliver(*args):events.append('telegram');return 'Complete'
    async def publish(*args):events.append('youtube')
    monkeypatch.setattr(bot_app.studio,'produce',produce)
    monkeypatch.setattr(bot_app,'save_studio_downloads',lambda *args:'https://example.test/export')
    monkeypatch.setattr(bot_app,'deliver_studio_result',deliver)
    monkeypatch.setattr(bot_app,'publish_studio_result',publish)
    monkeypatch.setattr(bot_app.youtube,'auto_enabled',lambda:enabled)
    u=SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock()))
    c=SimpleNamespace(application=SimpleNamespace(bot_data={}))
    asyncio.run(bot_app.run_studio_job(u,c,'Topic'))
    assert events==(['production','telegram','youtube'] if enabled else ['production','telegram'])


def test_worker_cancellation_reads_remain_safe_during_database_writes(bot_app):
    from concurrent.futures import ThreadPoolExecutor
    bot_app.set_setting('frozen','0')
    def worker(index):
        for step in range(100):
            bot_app.set_setting(f'worker_{index}',step)
            bot_app.log_action('CONCURRENCY_TEST',f'{index}:{step}')
            assert bot_app.get_setting(f'worker_{index}')==str(step)
            assert bot_app.get_setting('frozen')=='0'
            assert bot_app.db_rows('SELECT COUNT(*) FROM memory')[0][0]==6
    with ThreadPoolExecutor(max_workers=6) as workers:
        list(workers.map(worker,range(6)))
    assert bot_app.db_rows("SELECT COUNT(*) FROM ledger WHERE kind='CONCURRENCY_TEST'")[0][0]==600
    bot_app.set_setting('frozen','1')
    with ThreadPoolExecutor(max_workers=2) as workers:
        assert list(workers.map(lambda _:bot_app.get_setting('frozen'),range(10)))==['1']*10


def test_model_request_has_total_deadline(bot_app,monkeypatch):
    cancelled=[]
    async def provider(**kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)
    fake=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=provider)))
    monkeypatch.setattr(bot_app,'brain',SimpleNamespace(with_options=lambda **kwargs:fake))
    monkeypatch.setattr(bot_app,'STUDIO_MODEL_DEADLINE',0.02)
    assert asyncio.run(bot_app.studio_ask('Return JSON'))==''
    assert cancelled==[True]


def test_studio_model_routes_cannot_fall_back_to_paid_models(bot_app,monkeypatch,tmp_path):
    calls=[]
    async def provider(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"approved":true,"issues":[]}'),finish_reason='stop')])
    fake=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=provider)))
    monkeypatch.setattr(bot_app,'brain',SimpleNamespace(with_options=lambda **kwargs:fake))
    for attempt in range(3):
        assert asyncio.run(bot_app.studio_ask('Return JSON',attempt))
    picture=tmp_path/'fixture.jpg';picture.write_bytes(b'image fixture')
    for attempt in range(2):
        assert asyncio.run(bot_app.studio_ask('Inspect JSON',attempt,images=[picture]))
    assert all(c['model'].endswith(':free') for c in calls)
    assert all(c['extra_body']['reasoning']['exclude'] is True for c in calls)
    assert calls[0]['extra_body']['reasoning']['max_tokens'] < calls[0]['max_tokens']
    assert 'response_format' not in calls[0]
    assert calls[1]['extra_body']['reasoning']['effort']=='high'
    assert all(c['extra_body']['reasoning']['enabled'] is False for c in calls[3:])
    assert all(c['model'] not in [v['model'] for v in calls[3:]] for c in calls[:3])


def test_daily_quota_has_clear_error_without_logging_provider_body(bot_app,monkeypatch,caplog):
    error=type('RateLimitError',(Exception,),{})('Quota exceeded')
    error.body={'message':'Rate limit exceeded: free-models-per-day','private':'NEVER_LOG_PROVIDER_BODY'}
    async def provider(**kwargs):raise error
    fake=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=provider)))
    monkeypatch.setattr(bot_app,'brain',SimpleNamespace(with_options=lambda **kwargs:fake))
    with pytest.raises(bot_app.studio.StudioError,match='daily quota'):
        asyncio.run(bot_app.studio_ask('Return JSON'))
    assert 'NEVER_LOG_PROVIDER_BODY' not in caplog.text


def test_transient_free_rate_limit_cools_down_before_next_request(bot_app,monkeypatch):
    now=[100.0];calls=[];waits=[]
    monkeypatch.setattr(bot_app.time,'monotonic',lambda:now[0])
    async def sleep(seconds):
        waits.append(seconds); now[0]+=seconds
    monkeypatch.setattr(bot_app.asyncio,'sleep',sleep)
    error=type('RateLimitError',(Exception,),{})('Temporary limit')
    error.body={'message':'temporarily rate limited'}
    async def provider(**kwargs):
        calls.append(now[0])
        if len(calls)==1: raise error
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{}'),finish_reason='stop')])
    fake=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=provider)))
    monkeypatch.setattr(bot_app,'brain',SimpleNamespace(with_options=lambda **kwargs:fake))
    async def run():
        assert await bot_app.studio_ask('JSON') == ''
        assert await bot_app.studio_ask('JSON',1) == '{}'
    asyncio.run(run())
    assert waits == [65.0]
    assert calls == [100.0,165.0]


@pytest.mark.parametrize('video_fails',[False,True])
def test_link_timeout_preserves_video_and_attempts_inline_delivery(bot_app,video_fails):
    reply=AsyncMock(side_effect=TimeoutError())
    send=AsyncMock(side_effect=TimeoutError() if video_fails else None)
    u=SimpleNamespace(message=SimpleNamespace(reply_text=reply),effective_chat=SimpleNamespace(id=1))
    c=SimpleNamespace(bot=SimpleNamespace(send_video=send))
    result=asyncio.run(bot_app.deliver_studio_result(u,c,'https://example.test/output','Test',
                     {'duration_seconds':40,'bytes':1234}))
    assert reply.await_count==1
    assert send.await_count==1
    assert 'FIRST_STAGE_package.zip' in send.call_args.kwargs['caption']
    assert ('unconfirmed' in result) if video_fails else ('Telegram video delivered' in result)
    assert 'regenerate' in result if video_fails else True




def test_rejected_fact_outline_shows_actual_sentences_in_telegram(bot_app,monkeypatch):
    error=bot_app.studio.StudioError('c14 is too long')
    error.diagnostic={'draft':{'title':'Rejected title','claims':[{'id':'c14','text':'The actual rejected sentence.'}],
                              'scenes':[{'heading':'Heading','claim_ids':['c14']}]},'issue':'c14 is too long'}
    async def produce(*args):raise error
    monkeypatch.setattr(bot_app.studio,'produce',produce)
    u=SimpleNamespace(effective_chat=SimpleNamespace(id=123),message=SimpleNamespace(reply_text=AsyncMock()))
    c=SimpleNamespace(application=SimpleNamespace(bot_data={}),bot=SimpleNamespace(send_document=AsyncMock()))
    asyncio.run(bot_app.run_studio_job(u,c,'Topic'))
    assert any('c14: The actual rejected sentence.' in v.args[0] for v in u.message.reply_text.call_args_list)
    c.bot.send_document.assert_awaited_once()
