"""Rate limiting throttle classes for QA Center API views (Task 15).

Four levels of throttling:
- BurstRateThrottle:   10/min — general API usage
- TestExecuteThrottle:  5/min — test execution endpoints
- PipelineThrottle:     3/min — pipeline trigger/webhook
- WebhookThrottle:      2/min — external webhook endpoints (most restrictive)
"""

from rest_framework.throttling import UserRateThrottle


class BurstRateThrottle(UserRateThrottle):
    """General burst: 10 requests per minute."""
    rate = "10/minute"
    scope = "qa_burst"


class TestExecuteThrottle(UserRateThrottle):
    """Test execution: 5 requests per minute."""
    rate = "5/minute"
    scope = "qa_test_execute"


class PipelineThrottle(UserRateThrottle):
    """Pipeline trigger: 3 requests per minute."""
    rate = "3/minute"
    scope = "qa_pipeline"


class WebhookThrottle(UserRateThrottle):
    """Webhook endpoints: 2 requests per minute."""
    rate = "2/minute"
    scope = "qa_webhook"
