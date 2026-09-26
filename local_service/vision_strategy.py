"""Business prompts and constrained parsing kept outside the generic MLX provider."""
import re
from local_service.answer_normalizer import normalize_answer
from local_service.errors import InvalidRecognitionOutput


class VisionRecognitionStrategy:
    FORMATS={
        'integer': ('仅输出整数数字字符。',r'[0-9]+'),
        'choice': ('仅输出 A、B、C、D 之一。',r'[ABCD]'),
        'comparison_symbol': ('仅输出 <、>、= 之一。',r'[<>=]'),
    }

    @classmethod
    def prompt(cls,answer_type):
        instruction=cls.FORMATS.get(answer_type,('仅输出答案内容。',None))[0]
        return '只识别图片里学生最终填写的内容。'+instruction+'如果无法判断，输出“无法判断”。不要解释。'

    @classmethod
    def parse(cls,answer_type,raw):
        result=normalize_answer(raw)
        normalized=result['normalized']
        if not normalized or normalized=='无法判断':
            raise InvalidRecognitionOutput('Vision model could not determine the answer')
        pattern=cls.FORMATS.get(answer_type,(None,None))[1]
        if pattern and not re.fullmatch(pattern,normalized):
            raise InvalidRecognitionOutput('Vision output does not satisfy '+answer_type+' format')
        return result
