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