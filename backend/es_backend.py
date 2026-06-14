from haystack.backends.elasticsearch7_backend import Elasticsearch7SearchBackend, Elasticsearch7SearchEngine

class CustomElasticsearch7SearchBackend(Elasticsearch7SearchBackend):
    def __init__(self, connection_alias, **connection_options):
        super().__init__(connection_alias, **connection_options)
        
        # 覆盖默认的分析器设置
        # 将 min_gram 从默认的 3 修改为 2，以支持 2 个字的中文搜索（如“任务”）
        # 甚至可以设为 1 以支持单字搜索，但在 NgramField 中通常 2 是合理的折衷
        self.DEFAULT_SETTINGS['settings']['analysis']['filter']['haystack_ngram']['min_gram'] = 2
        self.DEFAULT_SETTINGS['settings']['analysis']['filter']['haystack_edgengram']['min_gram'] = 2
        
        # 将 tokenizer 修改为 whitespace，以支持中文 Ngram
        # 默认的 standard tokenizer 会把中文切分为单字，导致 min_gram=2 的 Ngram 过滤器过滤掉所有内容
        # 使用 whitespace，中文句子（无空格）会被视为一个 token，然后被 Ngram 切分
        self.DEFAULT_SETTINGS['settings']['analysis']['analyzer']['ngram_analyzer']['tokenizer'] = 'whitespace'
        self.DEFAULT_SETTINGS['settings']['analysis']['analyzer']['edgengram_analyzer']['tokenizer'] = 'whitespace'

class CustomElasticsearch7SearchEngine(Elasticsearch7SearchEngine):
    backend = CustomElasticsearch7SearchBackend