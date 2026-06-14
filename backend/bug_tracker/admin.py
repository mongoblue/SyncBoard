from django.contrib import admin
from .models import Bug, BugTransition, BugComment


@admin.register(Bug)
class BugAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'project', 'status', 'severity', 'priority',
                    'reporter', 'assignee', 'created_at')
    list_filter = ('status', 'severity', 'priority', 'source_test_type')
    search_fields = ('title', 'description')
    raw_id_fields = ('project', 'reporter', 'assignee', 'fixer', 'verifier', 'linked_task')


@admin.register(BugTransition)
class BugTransitionAdmin(admin.ModelAdmin):
    list_display = ('id', 'bug', 'operator', 'from_status', 'to_status', 'created_at')
    list_filter = ('to_status',)
    raw_id_fields = ('bug', 'operator')


@admin.register(BugComment)
class BugCommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'bug', 'author', 'created_at')
    raw_id_fields = ('bug', 'author')
