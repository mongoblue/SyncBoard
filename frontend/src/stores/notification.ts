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
        socket.value = new WebSocket(`${protocol}//${host}/ws/global/`)

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
        socket.value.onclose = (event)=>{
            console.log('服务已断开', event.code);
            socket.value = null;
            // 仅在非主动关闭时重连
            if (authStore.user) {
                setTimeout(() => {
                    if (authStore.user && !socket.value) {
                        console.log('正在重连服务...');
                        InitNotificationSocket();
                    }
                }, 5000);
            }
        }
    }
    return{
        notifications,
        unreadCount,
        InitNotificationSocket
    }
})
