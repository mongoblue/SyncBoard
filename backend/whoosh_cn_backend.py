from haystack.backends.whoosh_backend import WhooshEngine, WhooshSearchBackend
from jieba.analyse import ChineseAnalyzer

class WhooshCnSearchBackend(WhooshSearchBackend):
    def build_schema(self, fields):
        content_field_name, schema = super(WhooshCnSearchBackend, self).build_schema(fields)
        
        # 针对 text 字段使用结巴分词
        if 'text' in schema:
            schema['text'].analyzer = ChineseAnalyzer()
            
        return content_field_name, schema

class WhooshCnEngine(WhooshEngine):
    backend = WhooshCnSearchBackend
