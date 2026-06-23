"""
Celery 任务定义。

当前仅用于全文搜索索引的异步更新：
  - update_search_index:    模型保存后更新 ES 索引
  - remove_from_search_index: 模型删除后从索引移除

信号触发：room/models.py（Task/Project）中通过 post_save/post_delete 信号调用。
"""
from celery import shared_task
from django.apps import apps
from haystack import connections

@shared_task
def update_search_index(app_label, model_name, pk):
    try:
        model = apps.get_model(app_label, model_name)
        instance = model.objects.get(pk=pk)
        
        # Get the index for this model
        using = 'default'
        connection = connections[using]
        # Check if the model is indexed
        unified_index = connection.get_unified_index()
        try:
            index = unified_index.get_index(model)
            index.update_object(instance, using=using)
        except Exception:
            # Model not indexed, ignore
            pass
    except model.DoesNotExist:
        pass
    except Exception as e:
        print(f"Error updating search index for {app_label}.{model_name}:{pk} - {e}")

@shared_task
def remove_from_search_index(app_label, model_name, pk_str):
    try:
        # Construct the identifier used by Haystack (app.model.pk)
        identifier = f"{app_label}.{model_name}.{pk_str}"
        using = 'default'
        connection = connections[using]
        backend = connection.get_backend()
        backend.remove(identifier)
    except Exception as e:
        print(f"Error removing from search index for {app_label}.{model_name}:{pk_str} - {e}")