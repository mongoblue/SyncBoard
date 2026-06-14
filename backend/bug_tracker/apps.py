from django.apps import AppConfig


class BugTrackerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bug_tracker'
    verbose_name = 'Bug 跟踪'
