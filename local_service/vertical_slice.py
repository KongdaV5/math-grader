"""Template-bound crops, queued model runs and inspectable benchmark export."""
from datetime import date
import json
import logging
from pathlib import Path
import time
import uuid

from local_service.answer_normalizer import normalize_answer
from local_service.errors import (CropFailed, DomainError, InvalidAnswerRegion,
                                  NoConfidentTemplateMatch, PageNotFound, TemplateNotFound)
from local_service.model_providers import RecognitionRequest
from local_service.templates import validate_bbox

logger = logging.getLogger(__name__)


def _id():
    return str(uuid.uuid4())


def _now():
    from local_service.service import utc_now
    return utc_now()


def _dict(row):
    return dict(row) if row else None


class VerticalSlice:
    def __init__(self, service):
        self.service = service
        self.database = service.database
        self.paths = service.paths
        self.routes = json.loads((Path(__file__).parent / 'config' / 'recognition_candidates.json').read_text())['model_routes']

    def _page(self, connection, page_id):
        row = connection.execute('SELECT * FROM submission_pages WHERE id=?', (page_id,)).fetchone()
        if row is None:
            raise PageNotFound('Submission page not found')
        return row

    def process_page(self, page_id):
        with self.database.connection() as connection:
            row = self._page(connection,page_id)
            source = self.service._stored_page_path(row['source_ref'])
            if source is None or not source.is_file():
                raise PageNotFound('Stored page image not found')
            connection.execute("UPDATE submission_pages SET processing_status='PROCESSING',processing_started_at=?,processing_error=NULL WHERE id=?",(_now(),page_id))
        try:
            result = self.service.image_pipeline.process(source)
            status = 'WARNING' if result.warnings else 'READY'
            with self.database.connection() as connection:
                self._page(connection,page_id)
                connection.execute('''UPDATE submission_pages SET processed_image=?,processing_status=?,
                   processing_completed_at=?,page_detected=?,perspective_corrected=?,blur_score=?,exposure_score=?,
                   transform_metadata=?,processing_warning=?,processing_error=NULL WHERE id=?''',
                   (str(Path(result.processed_path).relative_to(self.paths.root)),status,_now(),
                    int(result.page_detected),int(result.perspective_corrected),result.blur_score,result.exposure_score,
                    json.dumps(result.transform),json.dumps(result.warnings),page_id))
            return {**result.to_dict(), 'processing_status':status}
        except Exception as error:
            with self.database.connection() as connection:
                connection.execute("UPDATE submission_pages SET processing_status='FAILED',processing_completed_at=?,processing_error=? WHERE id=?",
                                   (_now(),str(error)[:600],page_id))
            raise

    def bind_template(self,page_id,template_id):
        template = self.service.templates.get_page_template(template_id)
        with self.database.connection() as connection:
            page = self._page(connection,page_id)
            if page['processing_status'] not in ('READY','WARNING') or not page['processed_image']:
                raise CropFailed('Process this page before binding a template')
            binding_id = _id()
            snapshot = json.dumps(template,ensure_ascii=False)
            connection.execute('''INSERT INTO template_bindings
                (id,submission_page_id,page_template_id,template_version,snapshot_json,processed_image,created_at)
                VALUES(?,?,?,?,?,?,?)''',(binding_id,page_id,template_id,template['version'],snapshot,page['processed_image'],_now()))
            connection.execute('UPDATE submission_pages SET template_binding_id=? WHERE id=?',(binding_id,page_id))
        return self.get_binding(binding_id)

    def get_binding(self,binding_id):
        with self.database.connection() as connection:
            row=connection.execute('SELECT * FROM template_bindings WHERE id=?',(binding_id,)).fetchone()
            if not row: raise TemplateNotFound('Binding not found')
            item=dict(row);item['snapshot']=json.loads(item.pop('snapshot_json'))
            return item

    def match_templates(self,page_id,threshold=.35):
        import cv2
        with self.database.connection() as connection:
            page=self._page(connection,page_id)
            if not page['processed_image']: raise PageNotFound('Page has no processed image')
            page_path=self.paths.root/page['processed_image']
            rows=connection.execute('SELECT id,page_number,name,version,reference_image FROM page_templates WHERE active=1 AND reference_image IS NOT NULL').fetchall()
        image=cv2.imread(str(page_path),cv2.IMREAD_GRAYSCALE)
        if image is None: raise PageNotFound('Cannot decode processed page')
        orb=cv2.ORB_create(nfeatures=800)
        points,descriptors=orb.detectAndCompute(image,None)
        candidates=[]
        for row in rows:
            path=self.service._stored_page_path(row['reference_image'])
            ref=cv2.imread(str(path),cv2.IMREAD_GRAYSCALE) if path else None
            if ref is None or descriptors is None: continue
            ref_points,ref_descriptors=orb.detectAndCompute(ref,None)
            if ref_descriptors is None: continue
            pairs=cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(ref_descriptors,descriptors,k=2)
            good=[pair[0] for pair in pairs if len(pair)==2 and pair[0].distance<.75*pair[1].distance]
            if len(good)<8: continue
            import numpy as np
            source=np.float32([ref_points[m.queryIdx].pt for m in good]).reshape(-1,1,2)
            target=np.float32([points[m.trainIdx].pt for m in good]).reshape(-1,1,2)
            _,mask=cv2.findHomography(source,target,cv2.RANSAC,5.0)
            inliers=int(mask.sum()) if mask is not None else 0
            aspect=min(image.shape[1]/image.shape[0],ref.shape[1]/ref.shape[0])/max(image.shape[1]/image.shape[0],ref.shape[1]/ref.shape[0])
            score=min(1.0,inliers/max(1,min(len(points),len(ref_points)))*1.6)*.85+aspect*.15
            candidates.append({'template_id':row['id'],'page_number':row['page_number'],'name':row['name'],
                               'version':row['version'],'score':round(score,4)})
        candidates.sort(key=lambda x:x['score'],reverse=True)
        if not candidates or candidates[0]['score']<threshold:
            raise NoConfidentTemplateMatch('No template matched with enough confidence')
        return candidates

    def create_crops(self,page_id):
        from PIL import Image
        with self.database.connection() as connection:
            page=self._page(connection,page_id)
            if not page['template_binding_id']: raise TemplateNotFound('Bind a template first')
            binding=self.get_binding(page['template_binding_id'])
        source=self.paths.root/binding['processed_image']
        if not source.is_file(): raise CropFailed('Processed image for binding is missing')
        template=binding['snapshot']
        created=[]
        with Image.open(source) as image:
            width,height=image.size
            for question in template['questions']:
                for region in question['regions']:
                    validate_bbox(region['x'],region['y'],region['width'],region['height'])
                    x0=max(0,min(width-1,round(region['x']*width)))
                    y0=max(0,min(height-1,round(region['y']*height)))
                    x1=max(x0+1,min(width,round((region['x']+region['width'])*width)))
                    y1=max(y0+1,min(height,round((region['y']+region['height'])*height)))
                    if x1<=x0 or y1<=y0: raise CropFailed('Crop has no pixels')
                    crop_id=_id();path=self.paths.crops/(crop_id+'.png')
                    image.crop((x0,y0,x1,y1)).save(path)
                    entry={'id':crop_id,'submission_page_id':page_id,'binding_id':binding['id'],
                           'page_template_id':template['id'],'template_version':binding['template_version'],
                           'question_id':question['id'],'answer_region_id':region['id'],
                           'question_no':question['question_no'],'answer_type':question['answer_type'],
                           'region_index':region['region_index'],'crop_path':str(path.relative_to(self.paths.root)),
                           'normalized_bbox':json.dumps({k:region[k] for k in ('x','y','width','height')}),
                           'pixel_bbox':json.dumps([x0,y0,x1,y1]),'width':x1-x0,'height':y1-y0,'created_at':_now()}
                    with self.database.connection() as connection:
                        connection.execute('''INSERT INTO answer_crops(id,submission_page_id,binding_id,page_template_id,template_version,
                         question_id,answer_region_id,question_no,answer_type,region_index,crop_path,normalized_bbox,pixel_bbox,width,height,created_at)
                         VALUES(:id,:submission_page_id,:binding_id,:page_template_id,:template_version,:question_id,
                         :answer_region_id,:question_no,:answer_type,:region_index,:crop_path,:normalized_bbox,:pixel_bbox,:width,:height,:created_at)''',entry)
                    created.append(entry)
        return created

    def page_detail(self,page_id):
        with self.database.connection() as connection:
            page=dict(self._page(connection,page_id))
            binding=self.get_binding(page['template_binding_id']) if page['template_binding_id'] else None
            crops=[dict(row) for row in connection.execute('SELECT * FROM answer_crops WHERE submission_page_id=? ORDER BY created_at,question_no,region_index',(page_id,))]
            runs=[dict(row) for row in connection.execute('SELECT * FROM recognition_results WHERE page_id=? AND crop_id IS NOT NULL ORDER BY created_at,id',(page_id,))]
        for run in runs: run['metadata']=json.loads(run['metadata_json'])
        return {'page':page,'binding':binding,'crops':crops,'runs':runs}

    def queue_recognition(self,crop_id,model_id=None,allow_fallback=False):
        with self.database.connection() as connection:
            crop=connection.execute('SELECT * FROM answer_crops WHERE id=?',(crop_id,)).fetchone()
            if crop is None: raise CropFailed('Crop not found')
            route=self.routes.get(crop['answer_type'])
            if model_id is None:
                if route is None: raise ValueError('No candidate route for answer type')
                model_id=route['primary'];allow_fallback=True
            model=self.service.model_catalog.get(model_id)
            if crop['answer_type'] not in model['capabilities'] and 'vision' not in model['capabilities']:
                raise ValueError('Model does not support this answer type')
            run_id=_id();now=_now()
            revision=None
            if self.service.model_manager.get_model_status(model_id)['state']=='INSTALLED':
                manifest=self.service.model_manager.verify_model(model_id)
                resolved=manifest['resolved_revision']
                revision=(next(iter(resolved.values())) if len(resolved)==1 else
                          json.dumps(resolved,sort_keys=True,separators=(',',':')))
            metadata={'candidate_route':crop['answer_type'],'allow_fallback':bool(allow_fallback)}
            connection.execute('''INSERT INTO recognition_results(id,submission_id,page_id,crop_id,page_template_id,template_version,
             question_id,answer_region_id,region_index,crop_path,provider,model,model_revision,latency_ms,metadata_json,
             created_at,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?, 'PENDING')''',
             (run_id,connection.execute('SELECT submission_id FROM submission_pages WHERE id=?',(crop['submission_page_id'],)).fetchone()[0],
              crop['submission_page_id'],crop_id,crop['page_template_id'],crop['template_version'],crop['question_id'],
              crop['answer_region_id'],crop['region_index'],crop['crop_path'],model['provider_type'],model_id,revision,json.dumps(metadata),now))
            connection.execute("INSERT INTO jobs(id,status,created_at,kind,page_id,run_id) VALUES(?,'QUEUED',?,'RECOGNITION',?,?)",
                               (_id(),now,crop['submission_page_id'],run_id))
        return {'id':run_id,'status':'PENDING','model':model_id}

    def execute_run(self,run_id):
        from local_service.recognition import RecognitionResult
        with self.database.connection() as connection:
            run=connection.execute('SELECT * FROM recognition_results WHERE id=?',(run_id,)).fetchone()
            if not run: raise LookupError('Recognition run not found')
            crop=connection.execute('SELECT * FROM answer_crops WHERE id=?',(run['crop_id'],)).fetchone()
            if not crop: raise CropFailed('Crop not found')
            connection.execute("UPDATE recognition_results SET status='RUNNING' WHERE id=?",(run_id,))
        started=time.perf_counter();metadata=json.loads(run['metadata_json']);raw=None
        try:
            image=self.paths.root/crop['crop_path']
            prompt=''
            if self.service.model_catalog.get(run['model'])['provider_type']=='mlx_vlm':
                from local_service.vision_strategy import VisionRecognitionStrategy
                prompt=VisionRecognitionStrategy.prompt(crop['answer_type'])
            request=RecognitionRequest(image=str(image),answer_type=crop['answer_type'],
                                       capability=crop['answer_type'],prompt=prompt,
                                       constraints={'max_tokens':64})
            result=self.service.gateway.model_registry.get(run['model']).execute(request)
            raw=result.text
            metadata.update(result.metadata)
            if prompt:
                normalized=VisionRecognitionStrategy.parse(crop['answer_type'],raw)
            else:
                normalized=normalize_answer(raw)
            status='SUCCESS';error_code=None;error=None
            metadata['normalization_rules']=normalized['rules_applied']
            candidate=normalized['normalized'];confidence=result.confidence
        except Exception as exc:
            status=exc.code if isinstance(exc,DomainError) and exc.code in ('MODEL_NOT_INSTALLED','PROVIDER_UNAVAILABLE') else 'FAILED'
            error_code=exc.code if isinstance(exc,DomainError) else 'RECOGNITION_FAILED'
            error=str(exc)[:600];candidate=None;confidence=None
            logger.warning('run_id=%s provider=%s model=%s revision=%s status=%s error=%s',
                           run_id,run['provider'],run['model'],run['model_revision'],status,error_code)
        latency=int((time.perf_counter()-started)*1000)
        with self.database.connection() as connection:
            connection.execute('''UPDATE recognition_results SET text=?,normalized_candidate=?,confidence=?,latency_ms=?,
              metadata_json=?,error=?,error_code=?,status=?,completed_at=? WHERE id=?''',
              (raw,candidate,confidence,latency,json.dumps(metadata,ensure_ascii=False),error,error_code,status,_now(),run_id))
        logger.info('run_id=%s provider=%s model=%s revision=%s latency_ms=%s status=%s error=%s',
                    run_id,run['provider'],run['model'],run['model_revision'],latency,status,error_code)
        if status!='SUCCESS' and metadata.get('allow_fallback'):
            route=self.routes.get(crop['answer_type'],{})
            fallback=route.get('fallback')
            if fallback and fallback!=run['model']:
                self.queue_recognition(crop['id'],fallback,allow_fallback=False)
        return {'id':run_id,'status':status,'text':raw,'error_code':error_code,'latency_ms':latency}

    def export_predictions(self,page_id):
        detail=self.page_detail(page_id)
        return [{'schema_version':'0.1','run_id':run['id'],'sample_id':run['crop_id'],
                 'model_name':run['model'],'model_version':run['model_revision'] or 'unresolved',
                 'raw_prediction':run['text'],'normalized_prediction':run['normalized_candidate'] if run['status']=='SUCCESS' else None,
                 'model_confidence':run['confidence'],'decision_status':'REVIEW_REQUIRED',
                 'decision_confidence':None,'latency_ms':run['latency_ms'],
                 'error':{'code':run['error_code'] or 'RECOGNITION_FAILED','message':run['error'] or run['status']}
                   if run['status']!='SUCCESS' else None} for run in detail['runs'] if run['status'] not in ('PENDING','RUNNING')]

    def image_bytes(self,kind,item_id):
        with self.database.connection() as connection:
            if kind=='reference':
                row=connection.execute('SELECT reference_image AS path FROM page_templates WHERE id=?',(item_id,)).fetchone()
            elif kind=='processed':
                row=connection.execute('SELECT processed_image AS path FROM submission_pages WHERE id=?',(item_id,)).fetchone()
            elif kind=='crop':
                row=connection.execute('SELECT crop_path AS path FROM answer_crops WHERE id=?',(item_id,)).fetchone()
            elif kind=='original':
                row=connection.execute('SELECT source_ref AS path,mime_type FROM submission_pages WHERE id=?',(item_id,)).fetchone()
            else:
                raise PageNotFound('Unknown image type')
        if row is None or not row['path']: raise PageNotFound('Image not found')
        path=self.service._stored_page_path(row['path']) if kind in ('reference','original') else self.paths.root/row['path']
        if kind=='original':
            allowed = self.paths.legacy_pages if row['path'].startswith('pages/') else self.paths.originals
        else:
            allowed=self.paths.originals if kind=='reference' else self.paths.processed if kind=='processed' else self.paths.crops
        if path is None or not path.resolve().is_relative_to(allowed.resolve()) or not path.is_file():
            raise PageNotFound('Managed image not found')
        mime=(row['mime_type'] if kind=='original' and row['mime_type'] else
              'image/png' if path.suffix.lower()=='.png' else
              'image/jpeg' if path.suffix.lower() in ('.jpg','.jpeg') else
              'image/webp' if path.suffix.lower()=='.webp' else 'application/octet-stream')
        return mime,path.read_bytes()

    def import_lab_image(self,filename,content):
        service=self.service
        # Keep repeated lab imports together so they remain reachable after reopening the UI.
        with self.database.connection() as connection:
            row=connection.execute('''SELECT c.id AS class_id FROM classes c
                JOIN students s ON s.class_id=c.id WHERE c.name=? AND (s.student_no=? OR s.student_no LIKE ?)
                ORDER BY c.created_at,c.id LIMIT 1''',('识别实验室','LAB','LAB-%')).fetchone()
        if row:
            class_id=row['class_id']
        else:
            klass=service.create_class('识别实验室')
            class_id=klass['id']
        student_id=service.create_student(class_id,'LAB-'+uuid.uuid4().hex[:12],'合成样例')['id']
        day=date.today().isoformat();name='实验 '+day
        assignment=next((item for item in service.list_assignments(class_id)
                         if item['name']==name and item['date']==day),None)
        if assignment is None:
            assignment=service.create_assignment(class_id,name,day)
        submission=service.create_submission(assignment['id'],student_id)
        service.start_submission(submission['id'])
        return service.add_uploaded_page(submission['id'],filename,content)
