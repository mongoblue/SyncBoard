from haystack import indexes
from .models import Task

class TaskIndex(indexes.SearchIndex, indexes.Indexable):
    # 使用 NgramField 替代 CharField 以支持中文子串搜索
    # 设置 min_gram_size=2 以支持双字中文词（如"任务"）
    text = indexes.NgramField(document=True, use_template=True)
    title = indexes.CharField(model_attr='title')
    content = indexes.CharField(model_attr='content')
    project_id = indexes.CharField(model_attr='column__project__id')
    
    # We can also index related fields if needed
    
    def get_model(self):
        return Task

    def index_queryset(self, using=None):
        """Used when the entire index for model is updated."""
        return self.get_model().objects.all()
