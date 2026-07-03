
import os
plan_path = r'D:\Projects\SyncBoard\docs\superpowers\plans\2026-06-29-qa-center-production-upgrade.md'
os.makedirs(os.path.dirname(plan_path), exist_ok=True)

lines = []
lines.append('# QA Test Center Production Upgrade - Implementation Plan')
lines.append('')
lines.append('> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.')
lines.append('')
lines.append('**Goal:** Upgrade QA test center from feature-complete to production-reliable.')
lines.append('**Architecture:** Progressive hardening (Route A). P0 fixes 8 blockers, P1 establishes quality baseline.')
lines.append('**Tech Stack:** Django 5.x + DRF + Celery + Redis + Playwright + Locust + Jenkins/GitLab API + Vue 3 + Vitest')
lines.append('')
lines.append('---')
lines.append('')
lines.append('## Task 0: Environment Setup')
lines.append('')
lines.append('**Files:** Modify: backend/requirements.txt, backend/settings.py; Create: backend/celery_app.py')
lines.append('')
lines.append('- [ ] Add celery[redis]>=5.3,<6.0 and django-fernet-fields>=0.7 to requirements.txt')
lines.append('- [ ] pip install the new dependencies')
lines.append('- [ ] Add Celery config to settings.py: CELERY_BROKER_URL, CELERY_TASK_ACKS_LATE=True, CELERY_TASK_REJECT_ON_WORKER_LOST=True, CELERY_WORKER_PREFETCH_MULTIPLIER=1, feature flags (USE_CELERY_TASKS/USE_REAL_CI/USE_SEMAPHORE/PERF_MAX_CONCURRENT)')
lines.append('- [ ] Create backend/celery_app.py: app = Celery(syncboard); app.config_from_object(django.conf:settings, namespace=CELERY); app.autodiscover_tasks()')
lines.append('- [ ] Verify: cd backend && celery -A celery_app inspect ping')
lines.append('- [ ] Commit: chore: add Celery dependency and base configuration')
lines.append('')

with open(plan_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print('Script ready')
