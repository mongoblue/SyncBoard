import {ref} from 'vue';
import service from '@/utils/request';
import {defineStore} from 'pinia';
import type { BoardColumn, TaskCard,User } from '@/types/kanban';
import { useWebSocket } from '@/stores/composables/useWebSocket';
import { ElMessage } from 'element-plus';

export const useBoardStore = defineStore('board', () => {
    const Columns =ref<BoardColumn[]>([])
    const Users = ref<User[]>([])
    const {connect,addMessageListener,isConnected} = useWebSocket();
    const currentProjectId = ref<string>('');
    
    const currentProject = ref<any>(null); // ✨ 新增：存项目详情

    // 修改：fetchColumns 顺便获取项目详情 
    // (或者你也可以单独写一个 fetchProjectInfo)
    const fetchProjectInfo = async (projectId: string) => {
        try {
            // 这里我们需要一个获取单个项目的接口 GET /api/projects/:id/
            // 之前的 ProjectListView 只能拿列表，建议复用那个列表数据或者单独调接口
            // 简单做法：我们假设 ProjectListView 返回的列表里已经有这些信息了
            // 但为了严谨，我们直接调之前写的 GET /api/projects/
            const projects = await service.get<any,any[]>('/api/projects/');
            const found = projects.find((p: any) => p.id == projectId || p.id == Number(projectId));
            if (found) {
                currentProject.value = found;
            }
        } catch (e) {
            console.error(e);
        }
    }



    const fetchUsers = async()=>{
        try{
            const data = await service.get<any,User[]>('/api/users/');
            Users.value = data;
        }catch(error){
            console.error("获取用户列表",error);
        }
    }
    const fetchColumns = async(projectId:string) => {
        try{
            currentProjectId.value = projectId;
            const data = await service.get<any,BoardColumn[]>(`/api/columns/?project=${projectId}`);
            Columns.value = data
        }catch(error){
            console.error('获取看板失败');
        }
};

    const createTask = async (columnId: string, title: string) => {
        try {
            // ✅ 加上 /api 前缀
            await service.post('/api/tasks/', {
                column: columnId, 
                title: title,
                content: '', // 默认内容为空
                position: 0  // 默认放最上面
            });
            console.log('任务创建指令已发送');
        } catch (error) {
            console.error('创建任务失败', error);
        }
    };

    const deleteTask = async(taskID:string)=>{
        try{
            await service.delete(`/api/tasks/${taskID}/`)
            console.log(`任务${taskID}删除指令已发送`);
        }catch(error){
            console.error('删除任务失败',error);
    }
    }
    const updateTask = async(taskID:string,payload:Partial<TaskCard>)=>{
        try{
            await service.patch(`/api/tasks/${taskID}/`,payload)
            console.log(`任务 ${taskID} 更新成功`);
        }catch(error){
            console.error('更新任务失败',error);
        }
    }

    const handleSocketMessage = (payload: any) => {
            const { action, user } = payload.data || payload;
            
            if (action === 'user_joined') {
                ElMessage.success(`${user.username} 进入了看板`);
                // (进阶) 这里可以把 user.id 存入一个 "onlineUsers" 数组来高亮头像
            }
            if (action === 'user_left') {
                // ElMessage.info(`有人离开了看板`);
            }
            if (action === 'refresh') {
                fetchColumns(currentProjectId.value);   
            }
        };
    const initSocket = (projectId: string) =>{
        connect(`ws://localhost:8000/ws/board/${projectId}/`)
        addMessageListener(handleSocketMessage)
        }
        

    
    return{
        Columns,
        isConnected,
        Users,
        currentProjectId,
        createTask,
        fetchColumns,
        updateTask,
        initSocket,
        deleteTask,
        fetchUsers,
        fetchProjectInfo,
        currentProject, // ✨ 导出 currentProject
    }
})
