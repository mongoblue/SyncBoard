<template>
  <div class="test-result-hub">
    <header class="page-header">
      <div>
        <h1 class="page-title">测试结果</h1>
        <p class="page-subtitle">按测试类型分流查看执行结果</p>
      </div>
    </header>

    <div class="feature-cards">
      <el-card class="feature-card" shadow="hover" @click="goTo('api')">
        <div class="feature-icon" :style="{ background: 'var(--color-primary-bg)', color: 'var(--color-primary)' }">
          <el-icon><Document /></el-icon>
        </div>
        <div class="feature-title">API 测试结果</div>
        <div class="feature-desc">接口自动化测试执行记录</div>
      </el-card>

      <el-card class="feature-card" shadow="hover" @click="goTo('ui')">
        <div class="feature-icon" :style="{ background: 'var(--color-success-bg)', color: 'var(--color-success)' }">
          <el-icon><Monitor /></el-icon>
        </div>
        <div class="feature-title">UI 测试结果</div>
        <div class="feature-desc">UI 自动化与 E2E 测试执行记录</div>
      </el-card>

      <el-card class="feature-card" shadow="hover" @click="goTo('performance')">
        <div class="feature-icon" :style="{ background: 'var(--color-warning-bg)', color: 'var(--color-warning)' }">
          <el-icon><Lightning /></el-icon>
        </div>
        <div class="feature-title">性能测试结果</div>
        <div class="feature-desc">Locust 压测报告与实时监控</div>
      </el-card>

      <el-card class="feature-card" shadow="hover" @click="goToDevOps">
        <div class="feature-icon" :style="{ background: 'var(--color-info-bg)', color: 'var(--color-info)' }">
          <el-icon><Platform /></el-icon>
        </div>
        <div class="feature-title">DevOps 测试结果</div>
        <div class="feature-desc">CI/CD 触发的测试任务与 plan</div>
      </el-card>

      <el-card class="feature-card" shadow="hover" @click="goToTestRuns">
        <div class="feature-icon" :style="{ background: 'var(--color-info-bg)', color: 'var(--color-info)' }">
          <el-icon><List /></el-icon>
        </div>
        <div class="feature-title">批量执行历史</div>
        <div class="feature-desc">按批次查看 TestRun 与通过率</div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router';
import { Document, Monitor, Lightning, Platform, List } from '@element-plus/icons-vue';
import { useBoardStore } from '@/stores/board';

const router = useRouter();
const boardStore = useBoardStore();

const projectQuery = () => ({ project: boardStore.currentProject?.id });

const goTo = (testType: 'api' | 'ui' | 'performance') => {
  router.push({ name: 'TestResultList', query: { ...projectQuery(), test_type: testType } });
};

const goToDevOps = () => {
  router.push({ name: 'TestResultList', query: { ...projectQuery(), source: 'devops' } });
};

const goToTestRuns = () => {
  router.push({ name: 'TestRunList', query: projectQuery() });
};
</script>

<style scoped>
.test-result-hub { padding: 0; }

.page-header {
  margin-bottom: 24px;
}

.page-title {
  font-size: 22px;
  font-weight: 600;
  margin: 0;
}

.page-subtitle {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin: 6px 0 0;
}

.feature-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}

.feature-card {
  cursor: pointer;
  text-align: center;
  padding: 8px 0;
  transition: all 0.2s ease;
}

.feature-card:hover {
  border-color: var(--color-primary);
  transform: translateY(-2px);
}

.feature-icon {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 12px;
  font-size: 28px;
}

.feature-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 4px;
}

.feature-desc {
  font-size: 12px;
  color: var(--color-text-secondary);
}
</style>
