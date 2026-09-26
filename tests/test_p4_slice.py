"""P4 slice invariants without downloading real model weights during pytest."""
import base64
import json
from pathlib import Path
import threading
import time

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw
from jsonschema import Draft202012Validator

from local_service.answer_normalizer import normalize_answer
from local_service.errors import InvalidAnswerRegion, InvalidRecognitionOutput, NoConfidentTemplateMatch
from local_service.image_pipeline import ImageProcessResult
from local_service.model_providers import PaddleFormulaProvider, MLXVLMProvider, RecognitionRequest
from local_service.ocr_runtime import ctc_decode, det_postprocess, det_preprocess, rec_preprocess, extract_text_crop
from local_service.service import MathGraderService
from local_service.templates import ANSWER_TYPES
from local_service.worker import JobWorker
from scripts.generate_synthetic_worksheet import generate


def service_at(path):
    return MathGraderService(path/'data/math-grader.sqlite3',data_dir=path)


def prepared(tmp_path):
    service=service_at(tmp_path)
    files=tmp_path/'fixtures';regions=generate(files)
    group=service.templates.create_template_group('Fixture','4','fall','Book')
    template=service.templates.create_page_template(group['id'],1,'Page 1')
    reference=(files/'reference.png').read_bytes()
    service.import_template_reference(template['id'],{'filename':'reference.png',
        'image_base64':base64.b64encode(reference).decode()})
    questions=[]
    for number,(x,y,w,h,answer) in enumerate(regions,1):
        question=service.templates.create_question(template['id'],str(number),
             'choice' if number==3 else 'comparison_symbol' if number==4 else 'integer',answer)
        service.templates.create_answer_region(question['id'],1,x,y,w,h)
        questions.append(question)
    page=service.slice.import_lab_image('fixture.png',(files/'submission.png').read_bytes())
    return service,template,page,questions


def test_synthetic_formula_fixtures_and_lab_import_reuse(tmp_path):
    service=service_at(tmp_path)
    files=tmp_path/'fixtures';generate(files)
    for name in ('fraction.png','vertical.png','expression.png','formula_page.png'):
        with Image.open(files/name) as image:
            assert image.width>0 and image.height>0
    first=service.slice.import_lab_image('first.png',(files/'submission.png').read_bytes())
    second=service.slice.import_lab_image('second.png',(files/'formula_page.png').read_bytes())
    assert first['id']!=second['id']
    classes=[row for row in service.list_classes() if row['name']=='识别实验室']
    assert len(classes)==1
    assignments=service.list_assignments(classes[0]['id'])
    assert len(assignments)==1
    assert len(service.list_submissions(assignments[0]['id']))==2


def test_async_image_job_allows_second_upload_during_processing(tmp_path):
    service=service_at(tmp_path)
    klass=service.create_class('C');student=service.create_student(klass['id'],'1','A')
    assignment=service.create_assignment(klass['id'],'Worksheet','2026-09-26')
    submission=service.create_submission(assignment['id'],student['id'])
    service.start_submission(submission['id'])
    image=Image.new('RGB',(20,20),'white');source=tmp_path/'source.png';image.save(source);data=source.read_bytes()
    first=service.add_uploaded_page(submission['id'],'first.png',data)
    entered=threading.Event();release=threading.Event()
    original=service.image_pipeline.process
    def slow(path):
        entered.set();assert release.wait(5)
        return original(path)
    service.image_pipeline.process=slow
    worker=JobWorker(service,.01);worker.start()
    try:
        assert entered.wait(2)
        before=time.perf_counter();second=service.add_uploaded_page(submission['id'],'second.png',data)
        assert time.perf_counter()-before < .5
        assert second['page_index']==2
        assert service.slice.page_detail(second['id'])['page']['processing_status']=='PENDING'
    finally:
        release.set();worker.stop()
    assert service.slice.page_detail(first['id'])['page']['processing_status'] in ('READY','WARNING')


def test_image_status_warning_and_failure(tmp_path):
    service=service_at(tmp_path)
    klass=service.create_class('C');student=service.create_student(klass['id'],'1','A')
    assignment=service.create_assignment(klass['id'],'Worksheet','2026-09-26')
    submission=service.create_submission(assignment['id'],student['id']);service.start_submission(submission['id'])
    image=Image.new('RGB',(60,60),'white');source=tmp_path/'page.png';image.save(source)
    good=service.add_uploaded_page(submission['id'],'white.png',source.read_bytes())
    assert service.process_next_job()
    detail=service.slice.page_detail(good['id'])['page']
    assert detail['processing_status']=='WARNING' and detail['processed_image']
    assert detail['processing_completed_at'] and detail['processing_warning']
    damaged=service.add_uploaded_page(submission['id'],'bad.png',b'\x89PNG\r\n\x1a\nnot-a-real-image')
    assert service.process_next_job()
    detail=service.slice.page_detail(damaged['id'])['page']
    assert detail['processing_status']=='FAILED' and detail['processing_error']


def test_template_crud_version_snapshot_and_multiple_regions(tmp_path):
    service,template,page,questions=prepared(tmp_path)
    q=questions[0]
    second=service.templates.create_answer_region(q['id'],2,.79,.16,.1,.1)
    assert len(service.templates.get_question(q['id'])['regions'])==2
    service.slice.process_page(page['id'])
    binding=service.slice.bind_template(page['id'],template['id'])
    old=binding['template_version']
    service.templates.update_region(second['id'],{'x':.8})
    service.templates.update_question(q['id'],{'score':2,'answer_type':'decimal','metadata':{'note':'edit'}})
    assert service.templates.get_page_template(template['id'])['version']>old
    assert binding['snapshot']['questions'][0]['answer_type']=='integer'
    crops=service.slice.create_crops(page['id'])
    assert len(crops)==5 and crops[0]['template_version']==old
    assert {item['region_index'] for item in crops if item['question_id']==q['id']}=={1,2}
    service.templates.delete_region(second['id'])
    assert len(service.templates.get_question(q['id'])['regions'])==1
    assert len(service.slice.get_binding(binding['id'])['snapshot']['questions'][0]['regions'])==2
    reopened=service_at(tmp_path)
    assert len(reopened.templates.get_page_template(template['id'])['questions'])==4
    assert reopened.slice.get_binding(binding['id'])['template_version']==old


def test_invalid_bbox_and_controlled_answer_type(tmp_path):
    service,template,_,questions=prepared(tmp_path)
    for box in [(-.1,0,.2,.2),(0,0,0,.2),(.9,.9,.2,.2),(0,1,.1,.1)]:
        with pytest.raises(InvalidAnswerRegion):service.templates.create_answer_region(questions[0]['id'],10,*box)
    with pytest.raises(ValueError,match='answer_type'):
        service.templates.update_question(questions[0]['id'],{'answer_type':'arbitrary'})
    assert len(ANSWER_TYPES)==10


def test_crop_pixels_and_matcher_safety(tmp_path):
    service,template,page,_=prepared(tmp_path)
    service.slice.process_page(page['id'])
    candidates=service.slice.match_templates(page['id'])
    assert candidates[0]['template_id']==template['id']
    service.slice.bind_template(page['id'],template['id'])
    crops=service.slice.create_crops(page['id'])
    processed=service.paths.root/service.slice.page_detail(page['id'])['page']['processed_image']
    with Image.open(processed) as whole:
        for crop in crops:
            with Image.open(service.paths.root/crop['crop_path']) as item:
                assert item.size==(crop['width'],crop['height'])
                assert list(item.getdata())==list(whole.crop(json.loads(crop['pixel_bbox'])).getdata())
    # A blank page must be rejected rather than bound to an arbitrary template.
    blank=Image.new('RGB',(1000,1400),'white');path=tmp_path/'blank.png';blank.save(path)
    other=service.slice.import_lab_image('blank.png',path.read_bytes());service.slice.process_page(other['id'])
    with pytest.raises(NoConfidentTemplateMatch):service.slice.match_templates(other['id'])
    assert service.slice.page_detail(other['id'])['binding'] is None


def test_normalizer_trace_and_idempotence():
    examples={'１２０':'120','  2  ×  3  ':'2*3','2 X 3':'2*3','2 x 3':'2*3','2 ÷ 4':'2 / 4','':'','A\t B':'A B'}
    for raw,expected in examples.items():
        result=normalize_answer(raw)
        assert result['normalized']==expected
        assert normalize_answer(expected)['normalized']==expected
    assert normalize_answer('１２０')['rules_applied']
    assert normalize_answer('\x00A')['normalized']=='A'


def test_ocr_preprocess_postprocess_decoder_no_text():
    det_config={'PreProcess':{'transform_ops':[{'DetResizeForTest':None}]},
                'PostProcess':{'thresh':.2,'box_thresh':.45,'unclip_ratio':1.4,'max_candidates':3000}}
    image=np.ones((80,160,3),dtype='uint8')*255
    tensor,size=det_preprocess(image,det_config)
    assert tensor.shape[0:2]==(1,3) and size==(160,80) and tensor.dtype==np.float32
    probability=np.zeros((1,1,80,160),dtype=np.float32)
    assert det_postprocess(probability,(160,80),det_config)==[]
    probability[0,0,20:50,30:95]=.9
    boxes=det_postprocess(probability,(160,80),det_config)
    assert len(boxes)==1 and boxes[0]['score']>.45
    crop=extract_text_crop(image,boxes[0]['polygon'])
    rec_config={'PreProcess':{'transform_ops':[{'RecResizeImg':{'image_shape':[3,48,320]}}]}}
    assert rec_preprocess(crop,rec_config).shape==(1,3,48,320)
    chars=['','1','2','<',' ']
    logits=np.zeros((1,7,len(chars)),dtype='float32')
    for step,index in enumerate([0,1,1,0,2,3,3]):logits[0,step,index]=.9
    assert ctc_decode(logits,chars)==('12<',.9)
    assert ctc_decode(np.zeros((1,4,len(chars)),dtype='float32'),chars)==('',None)
    with pytest.raises(InvalidRecognitionOutput):ctc_decode(np.zeros((1,2,2)),chars)


def test_formula_output_parser_and_vlm_prompt_passthrough(tmp_path):
    assert PaddleFormulaProvider.parse_output({'res':{'rec_formula':'\\frac{1}{2}'}})=='\\frac{1}{2}'
    with pytest.raises(InvalidRecognitionOutput):PaddleFormulaProvider.parse_output({'res':{}})
    calls=[]
    class FakeProvider(MLXVLMProvider):
        def _load(self,path):return ('model','processor')
        def _infer(self,request):
            calls.append((request.image,request.prompt,request.constraints))
            return {'text':'120'}
    class Manager:
        catalog=type('Catalog',(),{'get':lambda self,_:{'runtime':'mlx-vlm'}})()
        def get_model_status(self,_):return {'state':'INSTALLED','path':str(tmp_path)}
    p=FakeProvider('fake',Manager());p.dependency='json'
    r=p.execute(RecognitionRequest('/tmp/crop.png','integer','vision',prompt='Read exactly',constraints={'max_tokens':10}))
    assert r.text=='120' and calls==[('/tmp/crop.png','Read exactly',{'max_tokens':10})]
    assert p.health()['state']=='READY';p.unload();assert p.health()['state']=='LOADABLE'


def test_recognition_history_error_and_benchmark_adapter(tmp_path):
    service,template,page,_=prepared(tmp_path)
    service.slice.process_page(page['id']);service.slice.bind_template(page['id'],template['id'])
    crop=service.slice.create_crops(page['id'])[0]
    first=service.slice.queue_recognition(crop['id'],'pp-ocrv6-small')
    assert service.process_next_job() # queued IMAGE may be handled first
    while service.slice.page_detail(page['id'])['runs'][0]['status']=='PENDING':assert service.process_next_job()
    second=service.slice.queue_recognition(crop['id'],'pp-ocrv6-small')
    while any(r['id']==second['id'] and r['status']=='PENDING' for r in service.slice.page_detail(page['id'])['runs']):assert service.process_next_job()
    runs=[r for r in service.slice.page_detail(page['id'])['runs'] if r['crop_id']==crop['id']]
    assert len(runs)==2 and all(r['status']=='MODEL_NOT_INSTALLED' for r in runs)
    records=service.slice.export_predictions(page['id'])
    schema=json.loads((Path(__file__).resolve().parents[1]/'benchmark/schemas/prediction.schema.json').read_text())
    for record in records:Draft202012Validator(schema).validate(record)
    assert all(record['decision_status']=='REVIEW_REQUIRED' for record in records)
    assert all(record['error']['code']=='MODEL_NOT_INSTALLED' for record in records)


def test_multi_artifact_run_records_both_model_revisions(tmp_path):
    service,template,page,_=prepared(tmp_path)
    service.slice.process_page(page['id']);service.slice.bind_template(page['id'],template['id'])
    crop=service.slice.create_crops(page['id'])[0]
    service.model_manager.get_model_status=lambda _:{'state':'INSTALLED'}
    service.model_manager.verify_model=lambda _:{'resolved_revision':{'det':'det-sha','rec':'rec-sha'}}
    run=service.slice.queue_recognition(crop['id'],'pp-ocrv6-small')
    saved=next(item for item in service.slice.page_detail(page['id'])['runs'] if item['id']==run['id'])
    assert json.loads(saved['model_revision'])=={'det':'det-sha','rec':'rec-sha'}


def test_model_error_persists_across_restart(tmp_path):
    from local_service.model_catalog import ModelCatalog
    from local_service.model_manager import ModelManager
    from local_service.runtime_paths import RuntimePaths
    path=tmp_path/'catalog.json';model=ModelCatalog().get('pp-ocrv6-small')
    path.write_text(json.dumps({'catalog_schema_version':1,'models':[model]}))
    class Failing:
        def list_files(self,*_):raise OSError('network unreachable')
    runtime=RuntimePaths(tmp_path/'runtime')
    first=ModelManager(ModelCatalog(path),runtime,downloader=Failing())
    assert first.install_model(model['id'],background=False)['state']=='ERROR'
    second=ModelManager(ModelCatalog(path),runtime,downloader=Failing())
    assert second.get_model_status(model['id'])['error']['message']=='network unreachable'
