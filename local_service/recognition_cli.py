"""Run the template/crop/recognition development path without the Desktop UI."""
import argparse
import json
from pathlib import Path

from local_service.runtime_paths import RuntimePaths, default_root
from local_service.service import MathGraderService, utc_now


def main(argv=None):
    parser=argparse.ArgumentParser(description='Local template-bound recognition smoke')
    parser.add_argument('--image',required=True,type=Path)
    parser.add_argument('--template',required=True,help='PageTemplate ID')
    parser.add_argument('--model',default='pp-ocrv6-small')
    parser.add_argument('--data-dir',type=Path,default=default_root())
    parser.add_argument('--json',action='store_true',help='Print one JSON result object')
    args=parser.parse_args(argv)
    source=args.image.expanduser().resolve(strict=True)
    paths=RuntimePaths(args.data_dir).ensure()
    service=MathGraderService(paths.database,data_dir=paths.root)
    service.templates.get_page_template(args.template)
    page=service.slice.import_lab_image(source.name,source.read_bytes())
    service.slice.process_page(page['id'])
    with service.database.connection() as connection:
        connection.execute("UPDATE jobs SET status='COMPLETED',completed_at=? WHERE kind='IMAGE' AND page_id=? AND status='QUEUED'",
                           (utc_now(),page['id']))
    binding=service.slice.bind_template(page['id'],args.template)
    crops=service.slice.create_crops(page['id'])
    results=[]
    for crop in crops:
        run=service.slice.queue_recognition(crop['id'],args.model)
        outcome=service.slice.execute_run(run['id'])
        with service.database.connection() as connection:
            connection.execute("UPDATE jobs SET status='COMPLETED',completed_at=? WHERE kind='RECOGNITION' AND run_id=?",
                               (utc_now(),run['id']))
        results.append({'question_no':crop['question_no'],'region_index':crop['region_index'],**outcome})
    details=service.slice.page_detail(page['id'])
    output={'processed_page':details['page']['processed_image'],'processing_status':details['page']['processing_status'],
            'template_id':args.template,'template_version':binding['template_version'],
            'crop_count':len(crops),'provider':service.model_catalog.get(args.model)['provider_type'],
            'model':args.model,'results':results}
    if args.json:
        print(json.dumps(output,ensure_ascii=False,indent=2))
    else:
        print('Processed page:',output['processed_page'])
        print('Template:',args.template,'version',binding['template_version'],'crops',len(crops))
        for result in results:
            print('Q{} region {}: {} {} {} ms {}'.format(result['question_no'],result['region_index'],
                result['status'],result['text'],result['latency_ms'],result['error_code'] or ''))
    return 0 if all(row['status']=='SUCCESS' for row in results) else 2


if __name__=='__main__':
    raise SystemExit(main())
