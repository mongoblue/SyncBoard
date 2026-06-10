<template>
  <div class="members-page">
    <!-- 页面头部 -->
    <header class="page-header">
      <div class="header-left">
        <span class="header-folio">N° 01</span>
        <div class="header-titles">
          <h1 class="page-title">成员管理</h1>
          <p class="page-subtitle">{{ members.length + 1 }} 名成员 · 共 {{ projectRoles.length }} 种角色</p>
        </div>
      </div>
      <button class="primary-btn" @click="inviteDialogVisible = true">
        <el-icon :size="12"><Plus /></el-icon>
        邀请成员
      </button>
    </header>

    <!-- 负责人 —— 顶部全宽 profile 行 -->
    <section v-if="projectOwner" class="owner-block">
      <div class="owner-grid">
        <div class="owner-cell owner-cell-label">
          <span class="cell-folio">ROLE</span>
          <span class="cell-name">项目负责人</span>
        </div>
        <div class="owner-cell owner-cell-id">
          <span class="cell-folio">ID</span>
          <span class="cell-name mono">U-{{ String(projectOwner.id).slice(-3).padStart(3, '0') }}</span>
        </div>
        <div class="owner-cell owner-cell-name">
          <div class="owner-identity">
            <div class="owner-avatar">
              <img v-if="projectOwner.profile?.avatar" :src="projectOwner.profile.avatar" alt="负责人" />
              <span v-else>{{ projectOwner.username?.charAt(0).toUpperCase() }}</span>
            </div>
            <div class="owner-text">
              <span class="owner-name">{{ projectOwner.username }}</span>
              <span class="owner-email" v-if="projectOwner.email">{{ projectOwner.email }}</span>
            </div>
          </div>
        </div>
        <div class="owner-cell owner-cell-role">
          <span class="role-chip role-chip-owner">Owner</span>
        </div>
      </div>
    </section>

    <!-- 成员区域 -->
    <section class="members-section">
      <div class="section-header">
        <div class="header-left">
          <span class="section-folio">N° 02</span>
          <h2 class="section-title">项目成员</h2>
        </div>
        <span class="section-count">{{ String(members.length).padStart(2, '0') }}</span>
      </div>

      <div v-if="members.length === 0" class="empty-state">
        <span class="empty-folio">EMPTY</span>
        <p class="empty-text">暂无成员，邀请协作者加入项目</p>
        <button class="primary-btn" @click="inviteDialogVisible = true">
          <el-icon :size="12"><Plus /></el-icon>
          邀请成员
        </button>
      </div>

      <div v-else class="members-grid">
        <article
          v-for="member in members"
          :key="member.id"
          class="member-card"
        >
          <div class="card-cell card-cell-id">
            <span class="cell-folio">ID</span>
            <span class="cell-name mono">U-{{ String(member.user_detail?.id || member.user?.id).slice(-3).padStart(3, '0') }}</span>
          </div>
          <div class="card-cell card-cell-name">
            <div class="member-identity">
              <div class="member-avatar">
                <img v-if="member.profile?.avatar" :src="member.profile.avatar" alt="成员" />
                <span v-else>{{ getInitials(member) }}</span>
              </div>
              <div class="member-text">
                <span class="member-name">{{ member.user_detail?.username || member.user?.username }}</span>
              </div>
            </div>
          </div>
          <div class="card-cell card-cell-role">
            <el-select
              v-if="isOwner"
              :model-value="member.role || member.role_detail?.id"
              placeholder="角色"
              class="role-select"
              @update:model-value="(val: number) => changeRole(member, val)"
            >
              <el-option v-for="r in projectRoles" :key="r.id" :label="r.name" :value="r.id" />
            </el-select>
            <span v-else class="role-chip" :class="'role-chip-' + (member.role_detail?.color || 'default')">
              {{ member.role_detail?.name || '成员' }}
            </span>
          </div>
          <div class="card-cell card-cell-actions">
            <button
              v-if="isOwner"
              class="card-icon-btn card-icon-btn-danger"
              @click="handleRemoveMember(member)"
              title="移除成员"
            >
              <el-icon :size="14"><Delete /></el-icon>
            </button>
          </div>
        </article>
      </div>
    </section>

    <!-- 邀请弹窗 -->
    <el-dialog v-model="inviteDialogVisible" width="420px" class="app-dialog" :show-close="false">
      <template #header>
        <div class="dialog-header">
          <span class="dialog-folio">NEW</span>
          <span class="dialog-title">邀请成员</span>
        </div>
      </template>
      <div class="invite-body">
        <span class="form-label">选择用户</span>
        <el-select
          v-model="selectedUser"
          filterable
          placeholder="搜索用户名称..."
          style="width: 100%"
          :filter-method="() => {}"
        >
          <el-option
            v-for="user in availableUsers"
            :key="user.id"
            :label="user.username"
            :value="user.username"
          >
            <div class="user-option">
              <div class="option-avatar">
                <img v-if="user.profile?.avatar" :src="user.profile.avatar" alt="avatar" />
                <span v-else>{{ user.username.charAt(0).toUpperCase() }}</span>
              </div>
              <span>{{ user.username }}</span>
            </div>
          </el-option>
        </el-select>
        <div v-if="availableUsers.length === 0" class="no-users-hint">
          暂无可邀请的用户
        </div>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <button class="text-btn" @click="inviteDialogVisible = false">取消</button>
          <button class="primary-btn" @click="handleInvite">确认邀请</button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { useBoardStore } from '@/stores/board';
import { useAuthStore } from '@/stores/Auth';
import service from '@/utils/request';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Plus, Delete } from '@element-plus/icons-vue';

const route = useRoute();
const boardStore = useBoardStore();
const authStore = useAuthStore();

const projectId = computed(() => route.params.projectId as string);
const projectOwner = computed(() => boardStore.currentProject?.owner_details);

const members = ref<any[]>([]);
const projectRoles = ref<any[]>([]);

const isOwner = computed(() => {
  return boardStore.currentProject?.owner_details?.id === authStore.user?.id;
});

const availableUsers = computed(() => {
  if (!boardStore.currentProject) return [];
  const memberIds = [
    boardStore.currentProject.owner_details.id,
    ...members.value.map(m => m.user_detail?.id || m.user?.id).filter(Boolean),
  ];
  return boardStore.Users.filter((u) => !memberIds.includes(u.id));
});

const getInitials = (member: any) => {
  const name = member.user_detail?.username || member.user?.username || '';
  return name.substring(0, 2).toUpperCase();
};

const fetchMembers = async () => {
  try {
    const [mRes, rRes] = await Promise.all([
      service.get(`/projects/${projectId.value}/members/`),
      service.get(`/projects/${projectId.value}/roles/`),
    ]);
    members.value = Array.isArray(mRes) ? mRes : (mRes as any).results || [];
    projectRoles.value = Array.isArray(rRes) ? rRes : (rRes as any).results || [];
  } catch { /* silent */ }
};

const changeRole = async (member: any, roleId: number) => {
  try {
    const userId = member.user_detail?.id || member.user?.id;
    await service.put(`/projects/${projectId.value}/members/`, {
      user_id: userId,
      role_id: roleId,
    });
    ElMessage.success('角色已更新');
    await fetchMembers();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '更新失败');
  }
};

const inviteDialogVisible = ref(false);
const selectedUser = ref('');

const handleInvite = async () => {
  if (!selectedUser.value) { ElMessage.warning('请选择成员'); return; }
  try {
    await service.post(`/projects/${projectId.value}/invite/`, { username: selectedUser.value });
    ElMessage.success('邀请成功');
    inviteDialogVisible.value = false;
    selectedUser.value = '';
    await fetchMembers();
    await boardStore.fetchProjectInfo(projectId.value);
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '邀请失败');
  }
};

const handleRemoveMember = async (member: any) => {
  try {
    const userId = member.user_detail?.id || member.user?.id;
    const username = member.user_detail?.username || member.user?.username;
    await ElMessageBox.confirm(`确定要移除 ${username} 吗？`, '移除成员', {
      confirmButtonText: '移除', cancelButtonText: '取消', type: 'warning',
    });
    await service.delete(`/projects/${projectId.value}/members/?user_id=${userId}`);
    ElMessage.success('成员已移除');
    await fetchMembers();
    await boardStore.fetchProjectInfo(projectId.value);
  } catch { /* cancelled */ }
};

onMounted(() => {
  boardStore.fetchUsers();
  fetchMembers();
});
</script>

<style scoped>
.members-page {
  display: flex;
  flex-direction: column;
  gap: 32px;
}

/* ── Page header ── */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--color-border);
  gap: 24px;
  flex-wrap: wrap;
}

.header-left {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  min-width: 0;
}

.header-folio {
  font: 600 11px/1 var(--font-mono);
  color: var(--color-accent);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-variant-numeric: tabular-nums;
  padding-top: 6px;
}

.header-titles {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.page-title {
  margin: 0;
  font: 600 26px/1.2 var(--font-heading);
  color: var(--color-text);
  letter-spacing: -0.01em;
}

.page-subtitle {
  margin: 0;
  font: 500 12px/1 var(--font-mono);
  color: var(--color-text-tertiary);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  font-variant-numeric: tabular-nums;
}

.primary-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 18px;
  background: var(--color-text);
  border: 1px solid var(--color-text);
  color: var(--color-text-inverse);
  cursor: pointer;
  font: 500 11px/1 var(--font-heading);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  transition: background var(--transition-fast), border-color var(--transition-fast);
  white-space: nowrap;
}

.primary-btn:hover {
  background: var(--color-primary);
  border-color: var(--color-primary);
}

.text-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 4px 0;
  font: 500 11px/1 var(--font-heading);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-secondary);
  transition: color var(--transition-fast);
}

.text-btn:hover {
  color: var(--color-text);
}

/* ── Owner block — full width typographic row ── */
.owner-block {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-left: 2px solid var(--color-accent);
  overflow: hidden;
}

.owner-grid {
  display: grid;
  grid-template-columns: 200px 140px 1fr 140px;
  align-items: stretch;
  min-height: 80px;
}

.owner-cell {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 18px 24px;
  border-right: 1px solid var(--color-border-light);
  min-width: 0;
}

.owner-cell:last-child {
  border-right: none;
}

.cell-folio {
  font: 600 9px/1 var(--font-mono);
  color: var(--color-text-tertiary);
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.cell-name {
  font: 500 13px/1.2 var(--font-heading);
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell-name.mono {
  font: 500 13px/1 var(--font-mono);
  font-variant-numeric: tabular-nums;
}

.owner-identity {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.owner-avatar {
  width: 40px;
  height: 40px;
  background: var(--color-text);
  color: var(--color-text-inverse);
  display: flex;
  align-items: center;
  justify-content: center;
  font: 600 14px/1 var(--font-mono);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
  overflow: hidden;
}

.owner-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.owner-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.owner-name {
  font: 600 16px/1 var(--font-heading);
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.owner-email {
  font: 500 11px/1 var(--font-mono);
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.owner-cell-role {
  align-items: flex-start;
  justify-content: center;
}

/* ── Role chip ── */
.role-chip {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border: 1px solid var(--color-border);
  font: 600 10px/1 var(--font-mono);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  font-variant-numeric: tabular-nums;
  color: var(--color-text-secondary);
  background: transparent;
}

.role-chip-owner {
  border-color: var(--color-accent);
  color: var(--color-accent);
  background: var(--color-accent-bg);
}

.role-chip-default {
  border-color: var(--color-border);
  color: var(--color-text-secondary);
}

/* ── Section header ── */
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--color-border);
}

.section-header .header-left {
  align-items: baseline;
}

.section-folio {
  font: 600 11px/1 var(--font-mono);
  color: var(--color-accent);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-variant-numeric: tabular-nums;
}

.section-title {
  margin: 0;
  font: 600 16px/1 var(--font-heading);
  color: var(--color-text);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.section-count {
  font: 500 11px/1 var(--font-mono);
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
  padding: 4px 8px;
  border: 1px solid var(--color-border);
  letter-spacing: 0.04em;
}

/* ── Members grid ── */
.members-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

/* ── Member card — row-style typographic block ── */
.member-card {
  display: grid;
  grid-template-columns: 60px 1fr 130px 40px;
  align-items: center;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  transition: border-color var(--transition-fast);
  min-height: 64px;
  overflow: hidden;
}

.member-card:hover {
  border-color: var(--color-text);
}

.card-cell {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 10px 12px;
  min-width: 0;
  border-right: 1px solid var(--color-border-light);
  height: 100%;
}

.card-cell:last-child {
  border-right: none;
  align-items: center;
  padding: 10px 8px;
}

.card-cell-id .cell-folio,
.card-cell-id .cell-name {
  font-size: 10px;
}

.card-cell-id .cell-name {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}

.member-identity {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.member-avatar {
  width: 32px;
  height: 32px;
  background: var(--color-surface-sunken);
  color: var(--color-text);
  display: flex;
  align-items: center;
  justify-content: center;
  font: 600 11px/1 var(--font-mono);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
  overflow: hidden;
  border: 1px solid var(--color-border);
}

.member-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.member-text {
  min-width: 0;
}

.member-name {
  font: 500 13px/1.2 var(--font-heading);
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-cell-role {
  align-items: stretch;
}

.role-select {
  width: 100%;
}

.role-select :deep(.el-input__wrapper) {
  border-radius: 0;
  box-shadow: 0 0 0 1px var(--color-border);
  background: transparent;
  padding-left: 8px;
  padding-right: 8px;
  min-height: 28px;
  height: 28px;
}

.role-select :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px var(--color-text-tertiary);
}

.role-select :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--color-text);
}

.role-select :deep(.el-input__inner) {
  font: 500 11px/1 var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.card-icon-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid transparent;
  cursor: pointer;
  color: var(--color-text-tertiary);
  transition: all var(--transition-fast);
  border-radius: 0;
  padding: 0;
  opacity: 0;
}

.member-card:hover .card-icon-btn {
  opacity: 1;
}

.card-icon-btn:hover {
  color: var(--color-text);
  border-color: var(--color-border);
}

.card-icon-btn.card-icon-btn-danger:hover {
  color: var(--color-danger);
  border-color: var(--color-danger);
}

/* ── Empty state ── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 64px 20px;
  background: var(--color-surface);
  border: 1px dashed var(--color-border);
  text-align: center;
}

.empty-folio {
  font: 600 10px/1 var(--font-mono);
  color: var(--color-text-tertiary);
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.empty-text {
  margin: 0;
  font: 400 14px/1.5 var(--font-body);
  color: var(--color-text-secondary);
}

/* ── Invite dialog ── */
.invite-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-label {
  font: 600 10px/1 var(--font-mono);
  color: var(--color-text-secondary);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.app-dialog :deep(.el-input__wrapper) {
  border-radius: 0;
  box-shadow: 0 1px 0 0 var(--color-border);
  background: transparent;
  padding-left: 0;
  padding-right: 0;
  transition: box-shadow var(--transition-fast);
}

.app-dialog :deep(.el-input__wrapper:hover) {
  box-shadow: 0 1px 0 0 var(--color-text-tertiary);
}

.app-dialog :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 1px 0 0 var(--color-text);
}

.user-option {
  display: flex;
  align-items: center;
  gap: 10px;
}

.option-avatar {
  width: 24px;
  height: 24px;
  background: var(--color-surface-sunken);
  color: var(--color-text);
  display: flex;
  align-items: center;
  justify-content: center;
  font: 600 10px/1 var(--font-mono);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
  overflow: hidden;
  border: 1px solid var(--color-border);
}

.option-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.no-users-hint {
  font: 500 11px/1.5 var(--font-mono);
  color: var(--color-text-tertiary);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 12px 0;
  text-align: center;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 16px;
  align-items: center;
}

/* ── Dialog chrome ── */
.app-dialog :deep(.el-dialog) {
  border-radius: 0;
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-md);
}

.app-dialog :deep(.el-dialog__header) {
  padding: 18px 24px;
  margin: 0;
  border-bottom: 1px solid var(--color-border);
}

.app-dialog :deep(.el-dialog__title) {
  display: none;
}

.app-dialog :deep(.el-dialog__headerbtn) {
  display: none;
}

.app-dialog :deep(.el-dialog__body) {
  padding: 24px;
}

.app-dialog :deep(.el-dialog__footer) {
  padding: 16px 24px;
  border-top: 1px solid var(--color-border);
  margin: 0;
}

.dialog-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.dialog-folio {
  font: 600 10px/1 var(--font-mono);
  color: var(--color-accent);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  font-variant-numeric: tabular-nums;
}

.dialog-title {
  font: 600 15px/1 var(--font-heading);
  color: var(--color-text);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

/* ── Responsive ── */
@media (max-width: 1024px) {
  .owner-grid {
    grid-template-columns: 160px 100px 1fr 120px;
  }
  .members-grid {
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  }
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
  }
  .primary-btn {
    align-self: flex-start;
  }
  .owner-grid {
    grid-template-columns: 1fr;
  }
  .owner-cell {
    border-right: none;
    border-bottom: 1px solid var(--color-border-light);
  }
  .owner-cell:last-child {
    border-bottom: none;
  }
  .member-card {
    grid-template-columns: 1fr 40px;
    grid-template-rows: auto auto;
  }
  .card-cell {
    border-right: none;
    border-bottom: 1px solid var(--color-border-light);
  }
  .card-cell-id,
  .card-cell-role {
    grid-column: 1 / -1;
  }
}
</style>
