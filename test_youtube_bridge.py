import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from youtube_bridge import CALLBACK, YouTubeBridge, YouTubeError


@pytest.fixture
def bridge():
    settings = {}
    obj = YouTubeBridge(settings.get, settings.__setitem__, env={})
    obj.settings = settings
    return obj


def passing_report():
    return {'technical_checks':'passed',
            'editorial_check':'Source quotes matched; second model pass approved. Human review still recommended.',
            'rendered_picture_review':'Passed separate review of two actual output frames per shot.'}


def test_oauth_state_is_expiring_single_use_and_pkce_bound(bridge, monkeypatch):
    from google_auth_oauthlib.flow import Flow
    creds = SimpleNamespace(refresh_token='PRIVATE_REFRESH',to_json=lambda:'PRIVATE_TOKEN_JSON')
    flow = SimpleNamespace(authorization_url=Mock(return_value=('https://accounts.google.com/authorize','state')),
                           fetch_token=Mock(),credentials=creds)
    factory=Mock(return_value=flow)
    monkeypatch.setattr(Flow,'from_client_config',factory)
    bridge.env.update(YT_CLIENT_ID='client',YT_CLIENT_SECRET='PRIVATE_CLIENT')
    monkeypatch.setattr(bridge,'channel',lambda creds:{'id':'correct','title':'FIRST STAGE'})
    bridge.start()
    assert factory.call_args.kwargs['autogenerate_code_verifier'] is True
    assert flow.redirect_uri == CALLBACK
    state=next(iter(bridge.pending))
    assert len(state)>=40
    with pytest.raises(YouTubeError):bridge.finish('wrong-state','secret-code')
    flow.fetch_token.assert_not_called()
    assert bridge.finish(state,'secret-code')['id']=='correct'
    flow.fetch_token.assert_called_once_with(code='secret-code',timeout=30)
    with pytest.raises(YouTubeError):bridge.finish(state,'secret-code')
    bridge.start();state=next(iter(bridge.pending))
    monkeypatch.setattr(bridge,'clock',lambda:10**12)
    with pytest.raises(YouTubeError):bridge.finish(state,'secret-code')
    assert flow.fetch_token.call_count==1


def test_channel_guard_rejects_wrong_channel_and_missing_upload_scope(bridge,monkeypatch):
    creds=SimpleNamespace(has_scopes=lambda scopes:True)
    client=Mock()
    client.channels.return_value.list.return_value.execute.return_value={'items':[
        {'id':'other','snippet':{'title':'Personal','customUrl':'@other'}}]}
    monkeypatch.setattr(bridge,'client',lambda creds:client)
    with pytest.raises(YouTubeError,match='not FIRST STAGE'):bridge.channel(creds)
    client.channels.return_value.list.return_value.execute.return_value={'items':[
        {'id':'correct','snippet':{'title':'FIRST STAGE','customUrl':'@FirstStageOfficial'}}]}
    assert bridge.channel(creds)['id']=='correct'
    bridge.settings['yt_channel_id']='pinned-different-channel'
    with pytest.raises(YouTubeError,match='not FIRST STAGE'):bridge.channel(creds)
    creds.has_scopes=lambda scopes:False
    with pytest.raises(YouTubeError,match='permission'):bridge.channel(creds)


def test_rejected_and_old_outputs_never_reach_youtube(bridge,tmp_path,monkeypatch):
    client=Mock();monkeypatch.setattr(bridge,'client',client)
    for report in ({}, {'technical_checks':'passed'}, {**passing_report(),'rendered_picture_review':''}):
        with pytest.raises(YouTubeError,match='Only a completed Studio'):bridge.upload(tmp_path,'Test',report)
    client.assert_not_called()


def upload_fixture(bridge,tmp_path,monkeypatch):
    (tmp_path/'FIRST_STAGE.mp4').write_bytes(b'VIDEO_FIXTURE')
    (tmp_path/'FIRST_STAGE_description.txt').write_text('Sources and full licensed footage credits.')
    monkeypatch.setattr(bridge,'credentials',lambda:'opaque-credentials')
    monkeypatch.setattr(bridge,'channel',lambda creds:{'id':'correct'})
    client=Mock();monkeypatch.setattr(bridge,'client',lambda creds:client)
    request=client.videos.return_value.insert.return_value
    request.next_chunk.return_value=(None,{'id':'video-id','status':{'privacyStatus':'public','uploadStatus':'uploaded'}})
    return client,request


def test_public_upload_preserves_credits_and_prevents_duplicates(bridge,tmp_path,monkeypatch):
    client,request=upload_fixture(bridge,tmp_path,monkeypatch)
    result=bridge.upload(tmp_path,'Evidence-backed title',passing_report())
    assert result['id']=='video-id' and result['privacy']=='public'
    body=client.videos.return_value.insert.call_args.kwargs['body']
    assert body['snippet']['description']=='Sources and full licensed footage credits.'
    assert body['status']['privacyStatus']=='public'
    assert body['status']['containsSyntheticMedia'] is True
    assert bridge.upload(tmp_path,'Evidence-backed title',passing_report())==result
    assert client.videos.return_value.insert.call_count==1
    request.next_chunk.assert_called_once_with(num_retries=0)


def test_uncertain_acknowledgement_is_not_retried_and_secrets_are_hidden(bridge,tmp_path,monkeypatch):
    client,request=upload_fixture(bridge,tmp_path,monkeypatch)
    request.next_chunk.side_effect=RuntimeError('PRIVATE_PROVIDER_TOKEN')
    with pytest.raises(YouTubeError,match='did not confirm') as error:bridge.upload(tmp_path,'Title',passing_report())
    assert 'PRIVATE' not in str(error.value)
    with pytest.raises(YouTubeError,match='uncertain outcome'):bridge.upload(tmp_path,'Title',passing_report())
    assert request.next_chunk.call_count==1


def test_freeze_and_credit_length_stop_before_upload(bridge,tmp_path,monkeypatch):
    client,request=upload_fixture(bridge,tmp_path,monkeypatch)
    with pytest.raises(YouTubeError,match='stopped before'):bridge.upload(tmp_path,'Title',passing_report(),lambda:True)
    request.next_chunk.assert_not_called()
    (tmp_path/'FIRST_STAGE_description.txt').write_text('x'*5001)
    with pytest.raises(YouTubeError,match='not truncated'):bridge.upload(tmp_path,'Title',passing_report())
    assert not bridge.settings


def test_persistence_status_checks_matching_refresh_token_and_reports_truthfully(bridge,monkeypatch):
    monkeypatch.setattr(bridge,'channel',lambda:{'id':'correct'})
    bridge.settings['yt_token']=json.dumps({'refresh_token':'current'})
    assert bridge.status()['persistent'] is False
    bridge.env['YT_TOKEN']=json.dumps({'refresh_token':'old'})
    assert bridge.status()['persistent'] is False
    bridge.env['YT_TOKEN']=json.dumps({'refresh_token':'current'})
    assert bridge.status()['persistent'] is True
    assert bridge.auto_enabled() is False
    bridge.env['YT_AUTO_PUBLISH']='1'
    assert bridge.auto_enabled() is True
    bridge.settings['yt_auto_publish']='0'
    assert bridge.auto_enabled() is False
