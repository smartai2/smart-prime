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
