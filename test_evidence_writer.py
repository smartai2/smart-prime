"""Checks for production's atomic evidence and correction path (no paid/API calls)."""
import asyncio
import copy
import json
import os
import time

import pytest
import studio
import evidence_writer as writer


@pytest.fixture
def evidence_case():
    lines = [
        'The lower stage supplies thrust during the initial ascent.',
        'The upper vehicle sits above that lower stage.',
        'Together the two stages form the launch vehicle.',
        'The first stage lifts the combined vehicle during launch.',
        'Its engines produce the thrust for this initial climb.',
        'The upper stage carries its own separate propulsion system.',
        'The upper engines ignite before the booster completely shuts down.',
        'This ignition sequence is known as hot staging.',
        'The stages separate while upper stage engines are burning.',
        'The interstage includes openings for the upper engine exhaust.',
        'Those openings allow exhaust to leave the interstage area.',
        'The upper stage continues its powered ascent after separation.',
        'The booster separates from the departing upper stage.',
        'The two separated stages then follow their respective trajectories.',
        'The lower stage no longer carries the upper stage.',
    ]
    sources=[{'id':1,'text':' '.join(lines)}]
    outline={'title':'How two stages work','claims':[{'id':f'c{i+1}','text':v,'evidence_ids':[f'1:{i+1}']} for i,v in enumerate(lines)],
             'scenes':[{'heading':h,'visual_query':'launch vehicle','claim_ids':[f'c{j+1}' for j in range(i*3,i*3+3)]}
                       for i,h in enumerate(['The stack','Initial ascent','Hot staging','Upper ascent','Separated stages'])]}
    return outline,sources


def compile_case(case):
    outline,sources=case
    return writer.compile_outline(outline,writer.catalogue_for('How it works',sources),sources,'How it works')


def review(plan, rejected=None):
    checks=[{'id':i['id'],'supported':True,'reason':'Attached quotation states this fact in the given context.'} for i in writer.audit_items(plan)]
    for check in checks:
        if rejected and check['id'] in rejected:
            check.update(supported=False,reason='The qualification is missing.',replacement=rejected[check['id']])
    return {'checks':checks}


def approved(case):
    plan=compile_case(case)
    plan['claim_review']=review(plan)['checks']
    plan['claim_review_digest']=writer.review_digest(writer.audit_items(plan))
    plan['editorial_check']='Source quotes matched; second model pass approved.'
    return plan


def test_compiles_each_sentence_with_its_own_exact_evidence(evidence_case):
    plan=compile_case(evidence_case)
    assert 80<=plan['word_count']<=170
    assert len(plan['claim_evidence'])==15
    for c in plan['claim_evidence']:
        assert c['evidence'][0]['quote']==c['text']
    assert [c['text'] for c in plan['claim_evidence']]==[p for s in plan['scenes'] for p in s['narration']]


@pytest.mark.parametrize('defect',['unknown_evidence','duplicate_claim','missing_claim','repeat_claim','nonobject_claim','nonobject_scene','two_sentences'])
def test_invalid_claim_structure_never_compiles(evidence_case,defect):
    outline,_=evidence_case
    if defect=='unknown_evidence':outline['claims'][0]['evidence_ids']=['2:99']
    if defect=='duplicate_claim':outline['claims'][1]['id']='c1'
    if defect=='missing_claim':outline['scenes'][0]['claim_ids'].pop()
    if defect=='repeat_claim':outline['scenes'][0]['claim_ids'][1]='c1'
    if defect=='nonobject_claim':outline['claims'][0]=None
    if defect=='nonobject_scene':outline['scenes'][0]=None
    if defect=='two_sentences':outline['claims'][0]['text']='It launches. It separates.'
    with pytest.raises(ValueError):compile_case(evidence_case)


def test_planned_sentence_cannot_hide_behind_another_qualified_sentence(evidence_case):
    outline,sources=evidence_case
    quote='The vehicle is designed to carry cargo after development.'
    sources[0]['text']+=' '+quote
    outline['claims'][0].update(text='The vehicle carries cargo after development.',evidence_ids=['1:16'])
    outline['claims'][1].update(text='The vehicle is designed to carry cargo.',evidence_ids=['1:16'])
    with pytest.raises(ValueError,match='c1: preserve the planned'):compile_case(evidence_case)
    outline['claims'][0]['text']='The vehicle is designed to carry cargo after development.'
    compile_case(evidence_case)


@pytest.mark.parametrize('defect',['missing','extra','duplicate','string_bool','no_reason','not_object'])
def test_review_requires_every_sentence_and_headline(evidence_case,defect):
    plan=compile_case(evidence_case);answer=review(plan)
    if defect=='missing':answer['checks'].pop()
    if defect=='extra':answer['checks'].append({'id':'unknown','supported':True,'reason':'yes'})
    if defect=='duplicate':answer['checks'][1]=answer['checks'][0]
    if defect=='string_bool':answer['checks'][0]['supported']='true'
    if defect=='no_reason':answer['checks'][0]['reason']=''
    if defect=='not_object':answer=[]
    with pytest.raises(ValueError):writer.validate_audit(answer,writer.audit_items(plan))


def test_corrections_preserve_accepted_text_evidence_and_order(evidence_case):
    outline,_=evidence_case;plan=compile_case(evidence_case)
    replacement='The lower stage provides thrust during initial ascent.'
    checks=review(plan,{'c1':replacement})['checks']
    checks[0]['replacement']='An unsolicited title change'
    checks[-1]['replacement']='An unsolicited sentence change.'
    checks[-1]['evidence_ids']=['9:99']
    revised=writer.apply_corrections(outline,checks)
    expected=copy.deepcopy(outline);expected['claims'][0]['text']=replacement
    assert revised==expected
    assert outline['claims'][0]['text']!=replacement


def test_rejected_text_cannot_be_resubmitted_unchanged(evidence_case):
    outline,_=evidence_case
    with pytest.raises(ValueError,match='unchanged'):
        writer.apply_corrections(outline,review(compile_case(evidence_case),{'c1':outline['claims'][0]['text']})['checks'])


def test_production_writer_reaudits_only_corrected_script_without_rewriting(evidence_case):
    outline,sources=evidence_case;plan=compile_case(evidence_case)
    correction=review(plan,{'c1':'The lower stage provides thrust during initial ascent.'})
    revised=writer.apply_corrections(outline,correction['checks'])
    final=compile_case((revised,sources))
    replies=iter([outline,correction,review(final)])
    calls=[]
    async def ask(prompt,route):
        calls.append((prompt,route));return json.dumps(next(replies))
    result=asyncio.run(studio.write_script('How it works',sources,ask))
    assert len(calls)==3 and [r for _,r in calls]==[0,0,0]
    assert result['fact_outline']==revised
    assert all('Check EVERY supplied item' in p for p,_ in calls[1:])
    assert revised['claims'][0]['text'] in calls[-1][0]
    writer.validate_approved(result,sources,'How it works')


def test_malformed_review_is_bounded_and_never_counts_as_approval(evidence_case):
    outline,sources=evidence_case;calls=[]
    async def ask(*args):
        calls.append(args)
        return json.dumps(outline) if len(calls)==1 else '{"approved":true}'
    with pytest.raises(studio.StudioError,match='incomplete review'):
        asyncio.run(studio.write_script('How it works',sources,ask))
    assert len(calls)==3


def test_factual_rejection_without_supported_correction_stops(evidence_case):
    outline,sources=evidence_case;answer=review(compile_case(evidence_case))
    answer['checks'][-1].update(supported=False,reason='The evidence does not support this claim.')
    replies=iter([outline,answer]);calls=[]
    async def ask(*args):calls.append(args);return json.dumps(next(replies))
    with pytest.raises(studio.StudioError,match='targeted factual correction') as err:
        asyncio.run(studio.write_script('How it works',sources,ask))
    assert len(calls)==2
    assert err.value.diagnostic['claim_review'][-1]['supported'] is False


def test_repeated_rejection_stops_after_two_actual_corrections(evidence_case):
    outline,sources=evidence_case;calls=[]
    versions=['The lower stage supplies thrust for initial ascent.','Initial ascent uses thrust supplied by the lower stage.']
    state={'outline':outline}
    async def ask(prompt,route):
        calls.append((prompt,route))
        if len(calls)==1:return json.dumps(outline)
        plan=compile_case((state['outline'],sources))
        replacement=versions[(len(calls)-2)%2]
        answer=review(plan,{'c1':replacement})
        state['outline']=writer.apply_corrections(state['outline'],answer['checks'])
        return json.dumps(answer)
    with pytest.raises(studio.StudioError,match='bounded corrections'):
        asyncio.run(studio.write_script('How it works',sources,ask))
    assert len(calls)==4 and all(r==0 for _,r in calls)


def test_quota_exhaustion_stops_without_a_second_call(evidence_case):
    calls=[]
    async def ask(*args):
        calls.append(args);raise studio.StudioError('The free AI daily quota is exhausted.')
    with pytest.raises(studio.StudioError,match='daily quota'):
        asyncio.run(studio.write_script('How it works',evidence_case[1],ask))
    assert len(calls)==1


@pytest.mark.parametrize('defect',['title','sentence','claim_quote','outline','missing_review','false_review','digest','version','expired'])
def test_approved_cache_cannot_reuse_stale_text_or_evidence(tmp_path,monkeypatch,evidence_case,defect):
    monkeypatch.setenv('STUDIO_CACHE',str(tmp_path))
    _,sources=evidence_case;plan=approved(evidence_case)
    studio.cache_script('How it works',sources,plan)
    assert studio.cached_script('How it works',sources)==plan
    assert studio.cached_script('Another topic',sources) is None
    assert studio.cached_script('How it works',[{'id':1,'text':'Changed evidence.'}]) is None
    path=studio.script_cache_path('How it works',sources)
    saved=json.loads(path.read_text());p=saved['plan']
    if defect=='title':p['title']='Something unchecked'
    if defect=='sentence':p['scenes'][0]['narration'][0]='Something unchecked occurred during initial ascent.'
    if defect=='claim_quote':p['claim_evidence'][0]['evidence'][0]['quote']='Invented source quote.'
    if defect=='outline':p['fact_outline']['claims'][0]['evidence_ids']=['1:2']
    if defect=='missing_review':p['claim_review'].pop()
    if defect=='false_review':p['claim_review'][0]['supported']=False
    if defect=='digest':p['claim_review_digest']='stale'
    if defect=='version':saved['version']='4.3.1'
    path.write_text(json.dumps(saved))
    if defect=='expired':os.utime(path,(time.time()-21601,)*2)
    assert studio.cached_script('How it works',sources) is None


def test_failed_sentence_review_stops_pipeline_before_media(tmp_path,monkeypatch,evidence_case):
    outline,sources=evidence_case;phases=[]
    def isolated(phase,*args):
        phases.append(phase)
        assert phase=='research'
        return sources
    monkeypatch.setattr(studio,'isolated_phase',isolated)
    monkeypatch.setenv('STUDIO_CACHE',str(tmp_path/'cache'))
    responses=iter([json.dumps(outline),'{"approved":true}','{}'])
    async def ask(*args):return next(responses)
    with pytest.raises(studio.StudioError,match='incomplete review'):
        asyncio.run(studio.produce('How it works',None,ask,tmp_path,lambda s:None))
    assert phases==['research']
    assert not studio.script_cache_path('How it works',sources).exists()


def test_length_repair_changes_only_flagged_text_then_requires_full_review(evidence_case):
    outline,sources=evidence_case
    original=outline['claims'][13]['text']
    outline['claims'][13]['text']='The two separated stages then follow their respective trajectories after they have separated from one another.'
    outline['scenes'][0]['heading']='A very long heading describing the vehicle visible during launch'
    items=writer.overlong_items(outline)
    repair={'replacements':[{'id':'c14','replacement':original}, {'id':'h1','replacement':'The visible vehicle'}]}
    revised=writer.shorten_items(outline,repair,items)
    assert revised['claims'][13]['evidence_ids']==outline['claims'][13]['evidence_ids']
    assert revised['claims'][:13]==outline['claims'][:13]
    assert revised['scenes'][1:]==outline['scenes'][1:]
    responses=iter([outline,repair,review(compile_case((revised,sources)))])
    prompts=[]
    async def ask(prompt,route):prompts.append(prompt);return json.dumps(next(responses))
    result=asyncio.run(studio.write_script('How it works',sources,ask))
    assert result['fact_outline']==revised
    assert len(prompts)==3
    assert 'Shorten ONLY' in prompts[1] and 'Check EVERY' in prompts[2]


def test_length_repair_cannot_edit_other_claims(evidence_case):
    outline,_=evidence_case
    outline['claims'][0]['text']='An overlong complete sentence with too many extra words to be used as narration in this video.'
    items=writer.overlong_items(outline)
    with pytest.raises(ValueError,match='only the overlong IDs'):
        writer.shorten_items(outline,{'replacements':[{'id':'c2','replacement':'Something else is changed.'}]},items)


def test_twostage_catalogue_excludes_unrelated_novelty_and_plume_research():
    useful=['The booster supplies thrust for initial ascent.',
            'The upper stage has its own rocket engines.',
            'Upper stage ignition begins before stage separation.']
    irrelevant=['Jason Howison studies hot staging.', 'Plume impingement hits the booster shield.',
                'Brian Richardson said staging has never been done before at this size.']
    catalog=writer.catalogue_for('How Starship two stages work',[{'id':1,'text':' '.join(useful+irrelevant)}])
    assert {v['quote'] for v in catalog.values()}==set(useful)


def test_twelve_sentence_outline_does_not_need_filler(evidence_case):
    outline,sources=evidence_case
    outline['claims']=outline['claims'][:12];outline['scenes']=outline['scenes'][:4]
    plan=compile_case(evidence_case)
    assert len(plan['claim_evidence'])==12 and plan['word_count']>=80


def test_stage_evidence_keeps_orbital_launch_pad_and_completed_ascent_burn():
    wanted=['The booster powered the stacked vehicle from the orbital launch pad.',
            'The spacecraft reached an orbit and completed its ascent burn.',
            'The upper engines ignite before stage separation.']
    unwanted=['The booster research concerns propellant transfer in orbit.',
              'The upper stage used thrusters to control orientation in orbit.']
    catalog=writer.catalogue_for('How Starship stages work',[{'id':1,'text':' '.join(wanted+unwanted)}])
    assert {v['quote'] for v in catalog.values()}==set(wanted)
