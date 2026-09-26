"""PP-OCRv6 ONNX inference using each installed bundle's inference.yml.

The DB contour and CTC steps follow PaddleOCR's Apache-2.0 pipeline semantics.
No page-wide fallback box is synthesized when detection returns no text.
"""
from pathlib import Path
import math
import time

import cv2
import numpy as np
import pyclipper
import yaml

from local_service.errors import InvalidRecognitionOutput, RecognitionFailed


def load_bundle(path):
    import onnxruntime as ort
    path = Path(path)
    configs = {part: yaml.safe_load((path / part / 'inference.yml').read_text(encoding='utf-8'))
               for part in ('det', 'rec')}
    sessions = {part: ort.InferenceSession(str(path / part / 'inference.onnx'), providers=['CPUExecutionProvider'])
                for part in ('det', 'rec')}
    dictionary = configs['rec']['PostProcess']['character_dict']
    classes = sessions['rec'].get_outputs()[0].shape[-1]
    # PaddleOCR exports CTC blank at zero and a trailing space character.
    charset = [''] + dictionary + [' ']
    if not isinstance(classes, int) or classes != len(charset):
        raise InvalidRecognitionOutput('Recognition dictionary does not match ONNX output')
    return {'config': configs, 'session': sessions, 'charset': charset}


def det_preprocess(image, config):
    h, w = image.shape[:2]
    if min(h, w) <= 0:
        raise RecognitionFailed('Empty OCR image')
    # PaddleOCR DetResizeForTest default: min side 736, max side 4000, stride 32.
    settings = next((item['DetResizeForTest'] or {} for item in config['PreProcess']['transform_ops']
                     if 'DetResizeForTest' in item), {})
    limit = settings.get('limit_side_len', 736)
    kind = settings.get('limit_type', 'min')
    max_side = settings.get('max_side_limit', 4000)
    scale = (max(1, limit / min(h, w)) if kind == 'min' else min(1, limit / max(h, w)))
    scale = min(scale, max_side / max(h, w))
    out_h = max(32, int(round(h * scale / 32) * 32))
    out_w = max(32, int(round(w * scale / 32) * 32))
    resized = cv2.resize(image, (out_w, out_h)).astype('float32') / 255.0
    normalized = (resized - np.array([.485, .456, .406], dtype='float32')) / np.array([.229, .224, .225], dtype='float32')
    return normalized.transpose(2, 0, 1)[None].astype('float32'), (w, h)


def _box_score(probability, points):
    h, w = probability.shape
    x0 = max(0, int(np.floor(points[:, 0].min())))
    y0 = max(0, int(np.floor(points[:, 1].min())))
    x1 = min(w - 1, int(np.ceil(points[:, 0].max())))
    y1 = min(h - 1, int(np.ceil(points[:, 1].max())))
    if x1 < x0 or y1 < y0:
        return 0.0
    mask = np.zeros((y1-y0+1, x1-x0+1), dtype='uint8')
    shifted = points.copy();shifted[:, 0] -= x0;shifted[:, 1] -= y0
    cv2.fillPoly(mask, [shifted.astype('int32')], 1)
    return float(cv2.mean(probability[y0:y1+1, x0:x1+1], mask)[0])


def det_postprocess(prediction, source_size, config):
    probability = np.asarray(prediction)
    if probability.ndim == 4:
        probability = probability[0, 0]
    if probability.ndim != 2:
        raise InvalidRecognitionOutput('Detection output must be a probability map')
    settings = config['PostProcess']
    threshold = float(settings['thresh']);box_threshold = float(settings['box_thresh'])
    unclip_ratio = float(settings['unclip_ratio']);maximum = int(settings['max_candidates'])
    contours, _ = cv2.findContours((probability > threshold).astype('uint8') * 255,
                                   cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    h, w = probability.shape
    source_w, source_h = source_size
    boxes = []
    for contour in contours[:maximum]:
        rectangle = cv2.minAreaRect(contour)
        if min(rectangle[1]) < 3:
            continue
        points = cv2.boxPoints(rectangle)
        score = _box_score(probability, points)
        if score < box_threshold:
            continue
        area = abs(cv2.contourArea(points));perimeter = cv2.arcLength(points, True)
        if perimeter <= 0:
            continue
        offset = pyclipper.PyclipperOffset()
        offset.AddPath(points.astype('int32').tolist(), pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
        expanded = offset.Execute(area * unclip_ratio / perimeter)
        if len(expanded) != 1:
            continue
        rectangle = cv2.minAreaRect(np.asarray(expanded[0], dtype='float32'))
        if min(rectangle[1]) < 5:
            continue
        points = cv2.boxPoints(rectangle)
        points[:, 0] = np.clip(np.round(points[:, 0] / w * source_w), 0, source_w - 1)
        points[:, 1] = np.clip(np.round(points[:, 1] / h * source_h), 0, source_h - 1)
        # TL, TR, BR, BL ordering for perspective crop.
        sums = points.sum(axis=1);diffs = np.diff(points, axis=1).ravel()
        ordered = np.asarray([points[np.argmin(sums)], points[np.argmin(diffs)],
                              points[np.argmax(sums)], points[np.argmax(diffs)]], dtype='float32')
        boxes.append({'polygon': ordered.tolist(), 'score': round(score, 6),
                      'bbox': [int(ordered[:,0].min()), int(ordered[:,1].min()),
                               int(ordered[:,0].max()), int(ordered[:,1].max())]})
    boxes.sort(key=lambda item: (item['bbox'][1] // 20, item['bbox'][0]))
    return boxes


def extract_text_crop(image, polygon):
    points = np.asarray(polygon, dtype='float32')
    width = max(1, int(max(np.linalg.norm(points[0]-points[1]), np.linalg.norm(points[2]-points[3]))))
    height = max(1, int(max(np.linalg.norm(points[0]-points[3]), np.linalg.norm(points[1]-points[2]))))
    target = np.array([[0,0],[width-1,0],[width-1,height-1],[0,height-1]], dtype='float32')
    crop = cv2.warpPerspective(image, cv2.getPerspectiveTransform(points,target),(width,height))
    if height / width >= 1.5:
        crop = cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
    return crop


def rec_preprocess(crop, config):
    shape = next(item['RecResizeImg']['image_shape'] for item in config['PreProcess']['transform_ops']
                 if 'RecResizeImg' in item)
    channels, height, width = shape
    h, w = crop.shape[:2]
    if h <= 0 or w <= 0 or channels != 3:
        raise RecognitionFailed('Invalid OCR text crop')
    resized_width = min(width, max(1, math.ceil(height * w / h)))
    resized = cv2.resize(crop, (resized_width, height)).astype('float32')
    image = resized.transpose(2,0,1) / 255.0
    image = (image - .5) / .5
    padded = np.zeros((channels,height,width), dtype='float32')
    padded[:,:,:resized_width] = image
    return padded[None]


def ctc_decode(prediction, charset):
    array = np.asarray(prediction)
    if array.ndim != 3 or array.shape[0] != 1 or array.shape[2] != len(charset):
        raise InvalidRecognitionOutput('CTC output has incompatible shape')
    indices = array[0].argmax(axis=1)
    probabilities = array[0].max(axis=1)
    previous = -1;characters = [];scores = []
    for index, confidence in zip(indices, probabilities):
        index = int(index)
        if index != 0 and index != previous:
            characters.append(charset[index]);scores.append(float(confidence))
        previous = index
    return ''.join(characters), round(float(np.mean(scores)),6) if scores else None


def recognize_image(image_path, bundle):
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RecognitionFailed('Cannot decode OCR image')
    started = time.perf_counter()
    inputs = bundle['session']['det'].get_inputs()[0].name
    tensor, size = det_preprocess(image, bundle['config']['det'])
    probability = bundle['session']['det'].run(None, {inputs: tensor})[0]
    boxes = det_postprocess(probability,size,bundle['config']['det'])
    lines=[]
    rec_input = bundle['session']['rec'].get_inputs()[0].name
    for box in boxes:
        crop = extract_text_crop(image, box['polygon'])
        tensor = rec_preprocess(crop,bundle['config']['rec'])
        output = bundle['session']['rec'].run(None,{rec_input:tensor})[0]
        text, confidence = ctc_decode(output,bundle['charset'])
        if text:
            lines.append({'text':text,'confidence':confidence,'box':box})
    return {'text':' '.join(item['text'] for item in lines),
            'confidence':round(float(np.mean([item['confidence'] for item in lines])),6) if lines else None,
            'boxes':boxes,'lines':lines,'latency_ms':int((time.perf_counter()-started)*1000)}
