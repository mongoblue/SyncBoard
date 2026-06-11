from django.contrib import admin
from .models import (
    ApiAutoTestSuite, ApiAutoTestCase, ApiAutoTestAssertion,
    ApiAutoTestResult, ApiAutoTestCaseResult
)


@admin.register(ApiAutoTestSuite)
class ApiAutoTestSuiteAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'project', 'is_active', 'created_by', 'created_at']
    list_filter = ['is_active', 'project']
    search_fields = ['name', 'description']
    raw_id_fields = ['project', 'created_by']


class ApiAutoTestCaseInline(admin.TabularInline):
    model = ApiAutoTestCase
    extra = 0
    fields = ['name', 'method', 'url', 'expected_status', 'is_active', 'sort_order']


class ApiAutoTestAssertionInline(admin.TabularInline):
    model = ApiAutoTestAssertion
    extra = 0
    fields = ['assertion_type', 'json_path', 'expected_value', 'comparison_operator', 'is_active']


@admin.register(ApiAutoTestCase)
class ApiAutoTestCaseAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'suite', 'method', 'url', 'expected_status', 'is_active', 'created_at']
    list_filter = ['method', 'is_active', 'suite']
    search_fields = ['name', 'url']
    raw_id_fields = ['suite', 'created_by']
    inlines = [ApiAutoTestAssertionInline]


@admin.register(ApiAutoTestAssertion)
class ApiAutoTestAssertionAdmin(admin.ModelAdmin):
    list_display = ['id', 'case', 'assertion_type', 'json_path', 'expected_value', 'comparison_operator', 'is_active']
    list_filter = ['assertion_type', 'is_active']
    search_fields = ['json_path', 'expected_value']
    raw_id_fields = ['case']


@admin.register(ApiAutoTestResult)
class ApiAutoTestResultAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'suite', 'status', 'total_cases', 'passed_cases', 'failed_cases', 'duration_ms', 'executed_by', 'created_at']
    list_filter = ['status', 'suite']
    search_fields = ['name']
    raw_id_fields = ['suite', 'executed_by']


@admin.register(ApiAutoTestCaseResult)
class ApiAutoTestCaseResultAdmin(admin.ModelAdmin):
    list_display = ['id', 'case', 'status_code', 'response_time_ms', 'passed', 'executed_at']
    list_filter = ['passed', 'status_code']
    search_fields = ['case__name']
    raw_id_fields = ['case', 'test_result']
