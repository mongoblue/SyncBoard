from haystack.signals import BaseSignalProcessor
from .tasks import update_search_index, remove_from_search_index

class CelerySignalProcessor(BaseSignalProcessor):
    def handle_save(self, sender, instance, **kwargs):
        # Check if this model is indexed
        using = 'default'
        connection = self.connections[using]
        # 使用 get_index 检查是否索引
        try:
            connection.get_unified_index().get_index(instance.__class__)
        except Exception:
            # 如果没有找到对应的 Index 类，说明该模型未被索引
            return
            
        update_search_index.delay(
            instance._meta.app_label,
            instance._meta.model_name,
            instance.pk
        )

    def handle_delete(self, sender, instance, **kwargs):
        using = 'default'
        connection = self.connections[using]
        try:
            connection.get_unified_index().get_index(instance.__class__)
        except Exception:
            return

        remove_from_search_index.delay(
            instance._meta.app_label,
            instance._meta.model_name,
            str(instance.pk)
        )