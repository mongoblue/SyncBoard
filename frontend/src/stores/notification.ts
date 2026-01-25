import { defineStore } from "pinia";
import { ref } from "vue";
import { ElNotification } from "element-plus";
import { useAuthStore } from "./Auth";

export const useNotificationStore = defineStore('notification',()=>{
    const socket = ref<WebSocket |null>(null)
    const notifications = ref<string[]>([])
    const unreadCount = ref(0)
    const authStore = useAuthStore()

    const InitNotificationSocket = ()=>{
        if(socket.value?.readyState === WebSocket.OPEN)return;
        if(!authStore.user) return;
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        const port = 8000;
        socket.value = new WebSocket(`${protocol}//${host}:${port}/ws://127.0.0.1:8000/ws/global/`)

        socket.value.onopen = ()=>{
            console.log('服务已连接');
        }
        socket.value.onmessage = (event)=>{
            const data = JSON.parse(event.data)
            if (data.type === 'global_notification')
                ElNotification(
            {
                'title':'系统通知',
                'message':data.message,
                'type':data.level,
                'duration':3000
            })
            notifications.value.unshift(data.message)
            unreadCount.value++
        }
        socket.value.onclose = ()=>{
            console.log('服务已断开');
        }
        setTimeout(() => {
            if(authStore.user && (socket.value?.readyState !== WebSocket.OPEN)){
                console.log('正在重连服务...');
                InitNotificationSocket()
            }
        }, 5000);
    }
    return{
        notifications,
        unreadCount,
        InitNotificationSocket
    }
})
