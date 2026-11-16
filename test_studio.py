import asyncio
import json
import sys
import threading
import time
from pathlib import Path

import pytest
import studio


def sample_plan():
    phrase = "This source explains how the launch system works."
    return {"title":"How the system works", "scenes":[
        {"heading":"The explanation", "visual_query":"Starship launch", "narration":[phrase,phrase,phrase],
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


def test_script_rejects_unfinished_clauses_and_overlong_narration():
    for phrase in ['The ship is designed to', 'This is an overly long sentence with eleven distinct separate words.']:
        plan=sample_plan()
        plan['scenes'][0]['narration'][0]=phrase
        with pytest.raises(ValueError):
            studio.validate_script(plan,[{'id':1,'text':'This is the exact source evidence for the explanation.'}])


def test_planned_capability_cannot_silently_become_operational():
    plan=sample_plan()
    quote='The spacecraft is intended to carry crew and cargo.'
    plan['scenes'][0]['evidence'][0]['quote']=quote
    with pytest.raises(ValueError,match='planned capability'):
        studio.validate_script(plan,[{'id':1,'text':quote+' This is the exact source evidence for the explanation.'}])


def test_visual_gate_rejects_repetition_illustrations_and_slideshow():
    assets=[studio.Media('Launch','','','','','','video'),studio.Media('Photo','','','','','','image')]
    candidates=[{'id':i,'media_index':0 if i<6 else 1} for i in range(8)]
    phrases=[{'narration':'A short complete sentence.'} for _ in range(10)]
    def validate(ids,allowed=range(8)):
        return studio.validate_shot_sequence({'approved':True,'shots':[{'id':i,'reason':'Visible rocket'} for i in ids]},phrases,candidates,assets,allowed)
    assert len(validate([0,1,2,6,3,4,5,7,0,1]))==10
    for ids,allowed in [([0,0,1,2,3,4,5,6,7,0],range(8)),
                        ([6,7,6,7,6,7,6,7,0,1],range(8)),
                        ([0,1,2,6,3,4,5,7,0,1],range(7))]:
        with pytest.raises(ValueError):validate(ids,allowed)


def test_malformed_review_is_retried_without_skipping_editorial_check():
    answers=iter([json.dumps(sample_plan()),'The response was interrupted.',
                  'Review result: {"approved":true,"issues":[]}'])
    async def ask(*args):return next(answers)
    plan=asyncio.run(studio.write_script('How it works',[{'id':1,'text':'This is the exact source evidence for the explanation.'}],ask))
    assert 'approved' in plan['editorial_check']


def test_missing_video_frame_does_not_abort_other_usable_shots(tmp_path,monkeypatch):
    from PIL import Image,ImageDraw
    image=Image.new('RGB',(800,800),'white')
    ImageDraw.Draw(image).rectangle((0,0,400,800),fill='black')
    image.save(tmp_path/'still.jpg')
    def extract(*args,**kwargs):
        offset=float(args[args.index('-ss')+1])
        if offset!=1:
            image.save(args[-1])
    monkeypatch.setattr(studio,'ffmpeg',extract)
    assets=[studio.Media('Launch','','','NASA','CC0','','video',path='clip.webm',duration=10),
            studio.Media('Rocket','','','NASA','CC0','','image',path='still.jpg')]
    sheet,shots=studio.contact_sheet(assets,tmp_path)
    assert sheet.is_file()
    assert len(shots)==3
    assert shots[-1]['kind']=='image'


def test_full_range_jpeg_renders_as_compatible_limited_range_video(tmp_path):
    import math,wave
    from array import array
    from PIL import Image,ImageDraw
    photo=Image.new('RGB',(800,1000),'#173F77')
    ImageDraw.Draw(photo).rectangle((150,200,650,800),fill='#ECE7DD')
    photo.save(tmp_path/'photo.jpg')
    voice=tmp_path/'tone.wav'
    duration=25.2;rate=16000
    with wave.open(str(voice),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate)
        w.writeframes(array('h',(int(3500*math.sin(2*math.pi*440*n/rate)) for n in range(int(duration*rate)))).tobytes())
    plan={'scenes':[{'heading':'COLOR FORMAT CHECK','visual_query':'Rocket','narration':['A test of the delivered video format.']} ]}
    assets=[studio.Media('Rocket','','','Test fixture','CC0','','image',path='photo.jpg')]
    result,report=studio.render_edit(plan,assets,[{'duration':duration,'output':str(voice)}],tmp_path)
    assert report['technical_checks']=='passed'
    assert studio.probe(result/'FIRST_STAGE.mp4')['yuv420p'] is True


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


@pytest.mark.skipif(not sys.platform.startswith('linux'),reason='Linux memory accounting')
def test_memory_budget_stops_an_oversized_worker():
    import os
    budget=studio.resident_mib(os.getpid())+45
    start=time.monotonic()
    with pytest.raises(studio.StudioError,match='memory budget'):
        studio.command([sys.executable,'-c','import time; payload=bytearray(90*1024*1024); time.sleep(10)'],memory_budget_mb=budget)
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
        '8':page(8,'CC0','SpaceX Starship models.webm'),
        '9':page(9,'CC0','Starship could deploy retractable air-breaks.webm')}}})
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
