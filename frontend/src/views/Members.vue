<template>
  <div class="members-page">
    <header class="page-header">
      <div>
        <h1 class="page-title">成员管理</h1>
        <p class="page-subtitle">{{ members.length + 1 }} 名成员 · 共 {{ projectRoles.length }} 种角色</p>
      </div>
      <el-button type="primary" @click="inviteDialogVisible = true">
        <el-icon style="margin-right: 4px"><Plus /></el-icon>
        邀请成员
      </el-button>
    </header>

    <!-- 负责人 -->
    <section v-if="projectOwner" class="owner-card card">
      <div class="owner-row">
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
        <span class="pill brand">项目负责人</span>
      </div>
    </section>

    <!-- 成员区域 -->
    <section class="members-section">
      <div class="section-header">
        <h2 class="card-section-title">项目成员</h2>
        <span class="section-count">{{ members.length }}</span>
      </div>

      <div v-if="members.length === 0" class="empty-state">
        <p class="empty-text">暂无成员，邀请协作者加入项目</p>
        <el-button type="primary" @click="inviteDialogVisible = true">
          <el-icon style="margin-right: 4px"><Plus /></el-icon>
          邀请成员
        </el-button>
      </div>

      <div v-else class="members-grid">
        <article
          v-for="member in members"
          :key="member.id"
          class="member-card card"
        >
          <div class="member-identity">
            <div class="member-avatar">
              <img v-if="member.profile?.avatar" :src="member.profile.avatar" alt="成员" />
              <span v-else>{{ getInitials(member) }}</span>
            </div>
            <div class="member-text">
              <span class="member-name">{{ member.user_detail?.username || member.user?.username }}</span>
              <span v-if="member.user_detail?.email" class="member-email">
                {{ member.user_detail.email }}
              </span>
            </div>
          </div>
          <div class="member-role">
            <el-select
              v-if="isOwner"
              :model-value="member.role || member.role_detail?.id"
              placeholder="角色"
              size="small"
              @update:model-value="(val: number) => changeRole(member, val)"
            >
              <el-option v-for="r in projectRoles" :key="r.id" :label="r.name" :value="r.id" />
            </el-select>
            <span v-else class="pill">
              {{ member.role_detail?.name || '成员' }}
            </span>
          </div>
          <div class="member-actions">
            <el-button
              v-if="isOwner"
              link
              size="small"
              type="danger"
              @click="handleRemoveMember(member)"
              title="移除成员"
            >
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </article>
      </div>
    </section>

    <!-- 邀请弹窗 -->
    <el-dialog v-model="inviteDialogVisible" title="邀请成员" width="420px">
      <div class="form-field">
        <label class="form-label">选择用户</label>
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
        <p v-if="availableUsers.length === 0" class="form-help">暂无可邀请的用户</p>
      </div>
      <template #footer>
        <el-button @click="inviteDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleInvite">确认邀请</el-button>
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
  gap: 24px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  padding-bottom: 16px;
  margin-bottom: 0;
  border-bottom: 1px solid var(--color-border-light);
  gap: 16px;
}

/* Owner card */
.owner-card {
  padding: 20px 24px;
  border-left: 3px solid var(--color-primary);
}

.owner-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.owner-identity {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
  flex: 1;
}

.owner-avatar {
  width: 44px;
  height: 44px;
  background: var(--color-primary);
  color: var(--color-text-inverse);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 600;
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
  gap: 2px;
  min-width: 0;
}

.owner-name {
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.owner-email {
  font-size: 12px;
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Members section */
.members-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--color-border-light);
}

.section-header .card-section-title {
  margin-bottom: 0;
}

.section-count {
  font-size: 13px;
  color: var(--color-text-secondary);
  font-weight: 500;
}

.members-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

/* Member card */
.member-card {
  display: grid;
  grid-template-columns: 1fr 140px 32px;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.member-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-card);
}

.member-identity {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.member-avatar {
  width: 36px;
  height: 36px;
  background: var(--color-surface-sunken);
  border: 1px solid var(--color-border);
  color: var(--color-text);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
  overflow: hidden;
}

.member-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.member-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.member-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.member-email {
  font-size: 12px;
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.member-role {
  min-width: 0;
}

.member-actions {
  display: flex;
  justify-content: center;
  opacity: 0;
  transition: opacity var(--transition-fast);
}

.member-card:hover .member-actions {
  opacity: 1;
}

/* Empty state */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px 20px;
  background: var(--color-surface);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  text-align: center;
}

.empty-text {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-secondary);
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
  border: 1px solid var(--color-border);
  color: var(--color-text);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
  overflow: hidden;
}

.option-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* Responsive */
@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
  }
  .members-grid {
    grid-template-columns: 1fr;
  }
  .member-card {
    grid-template-columns: 1fr 32px;
    grid-template-rows: auto auto;
  }
  .member-role {
    grid-column: 1 / 2;
    grid-row: 2;
  }
  .member-actions {
    grid-column: 2;
    grid-row: 1 / 3;
    opacity: 1;
  }
}
</style>
