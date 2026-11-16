import asyncio
import json
import sys
import threading
import time
from pathlib import Path

import pytest
import studio


def sample_plan():
    phrase = "This is a source supported explanation of how the launch system works."
    return {"title":"How the system works", "scenes":[
        {"heading":"The explanation", "visual_query":"Starship launch", "narration":[phrase,phrase],
         "evidence":[{"source_id":1,"quote":"This is the exact source evidence for the explanation."}]} for _ in range(4)]}


def test_script_evidence_quotes_must_exist():
    sources=[{"id":1,"text":"This is the exact source evidence for the explanation."}]
    plan=sample_plan()
    assert studio.validate_script(plan,sources)["word_count"]==96
    plan['scenes'][0]['evidence'][0]['quote']='A fabricated quote that never occurred.'
    with pytest.raises(ValueError,match='does not occur'):
        studio.validate_script(plan,sources)


def test_review_wrapping_is_tolerated_but_conflicting_answers_are_not():
    review='Here is the review:\n```json\n{"approved":true,"issues":[]}\n```'
    assert studio.json_object(review)=={'approved':True,'issues':[]}
    for ambiguous in ('[{"approved":true}]','{"approved":false} {"approved":true}'):
        with pytest.raises(ValueError):
            studio.json_object(ambiguous)


def test_malformed_review_is_retried_without_skipping_editorial_check():
    answers=iter([json.dumps(sample_plan()),'The response was interrupted.',
                  'Review result: {"approved":true,"issues":[]}'])
    async def ask(*args):return next(answers)
    plan=asyncio.run(studio.write_script('How it works',[{'id':1,'text':'This is the exact source evidence for the explanation.'}],ask))
    assert 'approved' in plan['editorial_check']


@pytest.mark.parametrize('url',[
    'http://www.nasa.gov/a','https://nasa.gov.attacker.example/a',
    'https://nasa.gov@127.0.0.1/a','https://127.0.0.1/a',
    'file:///etc/passwd','https://nasa.gov:8080/a'])
def test_source_host_boundary(url):
    assert not studio.host_allowed(url,studio.PRIMARY)


def test_download_redirect_rechecks_host():
    with pytest.raises(studio.StudioError):
        studio.SafeRedirect(studio.PRIMARY).redirect_request(None,None,302,'',{},'https://localhost/secret')


def test_cancellation_terminates_child():
    stop=threading.Event()
    timer=threading.Timer(.25,stop.set)
    timer.start()
    start=time.monotonic()
    with pytest.raises(studio.Cancelled):
        studio.command([sys.executable,'-c','import time; time.sleep(60)'],stopped=stop.is_set)
    timer.join()
    assert time.monotonic()-start<3


def test_licensing_and_simulation_filter(monkeypatch):
    def page(i,licence,title='SpaceX Starship launch.webm'):
        return {'title':'File:'+title,'index':i,'videoinfo':[{'url':'https://upload.wikimedia.org/test.webm',
            'descriptionurl':'https://commons.wikimedia.org/wiki/File:'+title,'width':1280,'height':720,'size':1000,
            'extmetadata':{'LicenseShortName':{'value':licence},'Artist':{'value':'Camera operator'},
                           'LicenseUrl':{'value':'https://creativecommons.org/licenses/by/4.0/'},
                           'ImageDescription':{'value':title}}}]}
    monkeypatch.setattr(studio,'api_json',lambda *a:{'query':{'pages':{
        '1':page(1,'CC0'),'2':page(2,'CC BY-NC 4.0'),'3':page(3,'CC BY-SA 4.0'),
        '4':page(4,'CC0','SpaceX Starship animation.webm'),'5':page(5,'CC BY 4.0'),
        '6':page(6,'CC BY 4.0','Mickey Thomas and Starship band.webm'),
        '7':page(7,'CC0',"Artist Concepts of SpaceX Starship.webm"),
        '8':page(8,'CC0','SpaceX Starship models.webm')}}})
    found=studio.commons_media('Starship','video')
    assert len(found)==2
    assert {m.license for m in found}=={'CC0','CC BY 4.0'}


def test_thumbnail_text_handles_punctuation(tmp_path):
    m=studio.Media('Launch','','','An actual creator','CC0','','video',date='2024-10-13')
    studio.overlay_image(tmp_path/'overlay.png',"What's different?",'No shell commands: $HOME; quotes & punctuation.',m,1,8)
    from PIL import Image
    with Image.open(tmp_path/'overlay.png') as im:
        assert im.size==(1080,1920)
        assert im.getpixel((500,800))[3]==0


def test_freshness_does_not_fall_back_to_encyclopedia(monkeypatch):
    monkeypatch.setattr(studio,'download',lambda *a,**k:b'<article>Starship undated background '*100)
    monkeypatch.setattr(studio,'api_json',lambda *a:pytest.fail('Current news cannot use background fallback'))
    with pytest.raises(studio.StudioError,match='dated primary'):
        studio.research('Starship latest today',lambda q,n:[])


def test_srt_rounding():
    assert studio.srt_time(59.9998)=='00:01:00,000'


def test_quality_gate_rejects_wrong_resolution(tmp_path,monkeypatch):
    monkeypatch.setattr(studio,'probe',lambda p:{'width':640,'height':360,'h264':True,'yuv420p':True,'aac':True,'audio':1})
    with pytest.raises(studio.StudioError,match='format'):
        studio.quality_check(tmp_path/'bad.mp4',[],30)
