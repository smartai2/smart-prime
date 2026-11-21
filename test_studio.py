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
    for phrase in ['The ship is designed to', 'This is an overly long sentence which contains far too many distinct separate words.']:
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


def test_evidence_ids_attach_original_text_and_reject_invented_ids():
    source={'id':1,'text':'The spacecraft is intended to carry crew and cargo. Both stages are still under development.'}
    catalog=studio.evidence_catalog([source])
    plan={'scenes':[{'evidence_ids':['1:1']}]}
    assert studio.resolve_evidence(plan,catalog)['scenes'][0]['evidence'][0]['quote']=='The spacecraft is intended to carry crew and cargo.'
    with pytest.raises(ValueError,match='exact evidence IDs'):
        studio.resolve_evidence({'scenes':[{'evidence_ids':['9:9']}]},catalog)


def test_writer_repairs_actual_rejected_draft():
    plan=sample_plan()
    bad=sample_plan()
    bad['scenes'][0]['narration'][0]='This is an overly long sentence which contains far too many distinct separate words.'
    calls=[]
    answers=iter([json.dumps(bad),json.dumps({'replacements':[plan['scenes'][0]['narration'][0]]}),' {"approved":true,"issues":[]} '])
    async def ask(prompt,*args):calls.append(prompt);return next(answers)
    asyncio.run(studio.write_script('How it works',[{'id':1,'text':'This is the exact source evidence for the explanation.'}],ask))
    assert 'Sentences to shorten' in calls[1]
    assert bad['scenes'][0]['narration'][0] in calls[1]
    assert 'evidence_catalogue' not in calls[1]
    assert 'Fact-check this narration' in calls[2]


def test_sentence_repair_cannot_remove_planned_capability_qualification():
    source='This is the exact source evidence for the explanation. The spacecraft is intended to carry crew and cargo.'
    bad=sample_plan()
    bad['scenes'][0]['narration'][0]='The spacecraft is designed to act as a standalone vehicle for crew and cargo.'
    bad['scenes'][0]['evidence']=[{'source_id':1,'quote':'The spacecraft is intended to carry crew and cargo.'}]
    calls=[]
    async def ask(prompt,*args):
        calls.append(prompt)
        if 'Sentences to shorten' in prompt:
            return json.dumps({'replacements':['The spacecraft carries crew and cargo.']})
        return json.dumps(bad)
    with pytest.raises(studio.StudioError,match='evidence check'):
        asyncio.run(studio.write_script('How it works',[{'id':1,'text':source}],ask))
    assert not any('Fact-check this narration' in prompt for prompt in calls)


def test_sentence_repair_preserves_room_for_factual_revision():
    bad = sample_plan()
    bad['scenes'][0]['narration'][0] = 'This is an overly long sentence which contains far too many distinct separate words.'
    short = sample_plan()['scenes'][0]['narration'][0]
    responses = iter([json.dumps(bad), json.dumps({'replacements':[[short,short]]}),
                      json.dumps({'approved':False,'issues':['Correct the factual description.']}),
                      json.dumps(sample_plan()), json.dumps({'approved':True,'issues':[]})])
    calls = []
    async def ask(prompt,*args):
        calls.append(prompt)
        return next(responses)
    plan = asyncio.run(studio.write_script('How it works',
        [{'id':1,'text':'This is the exact source evidence for the explanation.'}],ask))
    assert plan['word_count'] == 96
    assert 'Sentences to shorten' in calls[1]
    assert 'Fact-check this narration' in calls[2]
    assert 'Correct the factual description.' in calls[3]


def test_approved_script_cache_rechecks_evidence_version_and_expiry(tmp_path,monkeypatch):
    import os
    monkeypatch.setenv('STUDIO_CACHE',str(tmp_path))
    sources = [{'id':1,'text':'This is the exact source evidence for the explanation.'}]
    plan = sample_plan()
    plan['editorial_check'] = 'Second model approved.'
    studio.cache_script('How it works',sources,plan)
    assert studio.cached_script('How it works',sources) == plan
    assert studio.cached_script('Another topic',sources) is None
    assert studio.cached_script('How it works',[{'id':1,'text':'Changed evidence.'}]) is None
    path = studio.script_cache_path('How it works',sources)
    past = time.time()-6*3600-1
    os.utime(path,(past,past))
    assert studio.cached_script('How it works',sources) is None
    studio.cache_script('How it works',sources,plan)
    saved = json.loads(path.read_text()); saved['version']='old'
    path.write_text(json.dumps(saved))
    assert studio.cached_script('How it works',sources) is None
    studio.cache_script('How it works',sources,plan)
    saved = json.loads(path.read_text())
    saved['plan']['scenes'][0]['evidence'][0]['quote']='A fabricated quotation never present in evidence.'
    path.write_text(json.dumps(saved))
    assert studio.cached_script('How it works',sources) is None


def test_stage_explainer_rejects_fact_list_and_unqualified_heading():
    plan=sample_plan()
    with pytest.raises(ValueError,match='Answer how'):
        studio.validate_topic_focus(plan,'How Starship stages work')
    plan['scenes'][0]['heading']='A Fully Reusable Rocket'
    with pytest.raises(ValueError,match='Headlines'):
        studio.validate_topic_focus(plan,'Starship')
    plan['scenes'][0]['heading']='The staging sequence'
    plan['scenes'][0]['narration']=['Super Heavy powers launch.','The upper stage starts its engines before separation.']
    studio.validate_topic_focus(plan,'How Starship stages work')
    plan['scenes'][1]['narration']=['The 2024 test demonstrated this separation sequence.']
    studio.validate_topic_focus(plan,'How Starship stages work')
    plan['scenes'][1]['narration']=['As of 2026, it has launched fifteen times.']
    with pytest.raises(ValueError,match='flight counts'):
        studio.validate_topic_focus(plan,'How Starship stages work')


def test_real_source_does_not_authorize_empty_sky_shots():
    assets=[studio.Media('Launch','','','','','','video'),studio.Media('Concept','','','','','','image')]
    candidates=[{'id':0,'media_index':0},{'id':1,'media_index':0},{'id':2,'media_index':1}]
    answer={'media':[{'index':0,'type':'real'},{'index':1,'type':'illustration'}],
            'shots':[{'id':0,'usable':True,'subject_visible':True},
                     {'id':1,'usable':True,'subject_visible':False},
                     {'id':2,'usable':True,'subject_visible':True}]}
    assert studio.screened_shots(answer,assets,candidates)==[0]
    answer['shots'].pop()
    with pytest.raises(ValueError,match='every numbered shot'):
        studio.screened_shots(answer,assets,candidates)


def test_editor_options_are_arranged_without_rejected_or_repeated_shots():
    assets=[studio.Media('Launch','','','','','','video'),studio.Media('Pad','','','','','','image')]
    candidates=[{'id':i,'media_index':0 if i<3 else 1} for i in range(5)]
    phrases=[{'narration':'A clear complete explanation.'} for _ in range(12)]
    answer={'approved':True,'choices':[{'ids':[0,1,2,3,4],'reason':'Approved relevant alternatives.'} for _ in phrases]}
    shots=studio.arrange_shot_options(answer,phrases,candidates,assets,range(5))
    assert len(shots)==len(phrases)
    ids=[s['id'] for s in shots]
    assert len(set(ids))>=4
    assert all(a!=b for a,b in zip(ids,ids[1:]))
    assert sum(i<3 for i in ids)>=8
    answer['choices'][1]['ids']=[99]
    with pytest.raises(ValueError,match='no approved alternatives'):
        studio.arrange_shot_options(answer,phrases,candidates,assets,range(5))

    answer['choices']=[{'ids':['0',0,99,'1',2,3,4],'reason':'Relevant choices with duplicate and rejected alternatives.'} for _ in phrases]
    shots=studio.arrange_shot_options(answer,phrases,candidates,assets,range(5))
    assert all(s['id'] in range(5) for s in shots)


def test_impossible_visual_options_stop_instead_of_inventing_matches():
    assets=[studio.Media('Launch','','','','','','video')]
    candidates=[{'id':i,'media_index':0} for i in range(4)]
    phrases=[{'narration':'A clear complete explanation.'} for _ in range(8)]
    answer={'approved':True,'choices':[{'ids':[0],'reason':'Only this shot matches.'} for _ in phrases]}
    with pytest.raises(ValueError,match='cannot satisfy'):
        studio.arrange_shot_options(answer,phrases,candidates,assets,range(4))


def test_complete_sentences_are_split_without_cutting_clauses():
    plan=sample_plan()
    plan['scenes'][0]['narration']=[' '.join(plan['scenes'][0]['narration'])]
    result=studio.validate_script(plan,[{'id':1,'text':'This is the exact source evidence for the explanation.'}])
    assert len(result['scenes'][0]['narration'])==3
    assert result['word_count']==96


def test_missing_video_frame_does_not_abort_other_usable_shots(tmp_path,monkeypatch):
    from PIL import Image,ImageDraw
    image=Image.new('RGB',(800,800),'white')
    ImageDraw.Draw(image).rectangle((0,0,400,800),fill='black')
    image.save(tmp_path/'still.jpg')
    def extract(*args,**kwargs):
        offset=float(args[args.index('-ss')+1])
        if offset!=2:
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


@pytest.mark.skipif(sys.platform!='linux',reason='Linux process groups')
def test_cancellation_also_stops_nested_phase_children(tmp_path):
    marker=tmp_path/'unexpected.txt'
    child=f"import time; from pathlib import Path; time.sleep(1); Path({str(marker)!r}).write_text('still running')"
    parent='import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",'+repr(child)+']); time.sleep(60)'
    stop=threading.Event();timer=threading.Timer(.25,stop.set);timer.start()
    with pytest.raises(studio.Cancelled):
        studio.command([sys.executable,'-c',parent],stopped=stop.is_set)
    timer.join();time.sleep(1)
    assert not marker.exists()


def test_isolated_phase_returns_safe_failure_without_starting_a_bot(tmp_path):
    with pytest.raises(studio.StudioError,match='Unknown production phase'):
        studio.isolated_phase('unknown','A topic',{},tmp_path)


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
            'descriptionurl':'https://commons.wikimedia.org/wiki/File:'+str(i)+title,'width':1280,'height':720,'size':1000,
            'extmetadata':{'LicenseShortName':{'value':licence},'Artist':{'value':'Camera operator'},
                           'LicenseUrl':{'value':'https://creativecommons.org/licenses/by/4.0/'},
                           'ImageDescription':{'value':title}}}]}
    monkeypatch.setattr(studio,'api_json',lambda *a:{'query':{'pages':{
        '1':page(1,'CC0'),'2':page(2,'CC BY-NC 4.0'),'3':page(3,'CC BY-SA 4.0'),
        '4':page(4,'CC0','SpaceX Starship animation.webm'),'5':page(5,'CC BY 4.0'),
        '6':page(6,'CC BY 4.0','Mickey Thomas and Starship band.webm'),
        '7':page(7,'CC0',"Artist Concepts of SpaceX Starship.webm"),
        '8':page(8,'CC0','SpaceX Starship models.webm'),
        '9':page(9,'CC0','Starship could deploy retractable air-breaks.webm'),
        '10':page(10,'CC0','Starship IFT2 NASA launch.webm')}}})
    found=studio.commons_media('Starship','video')
    assert len(found)==3
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


