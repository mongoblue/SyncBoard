import axios, { type AxiosInstance, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'

// 定义响应数据类型
export interface ApiResponse<T = any> {
  data: T;
  status: number;
  message?: string;
}

// 创建 axios 实例，使用自定义响应类型
const service: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 60000, // 增加到 60 秒以适配 AI 响应速度
  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken',
  withCredentials: true, // 允许发送 cookies
})

service.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // 加请求头token
    return config;
  },
  (error) => {
    return Promise.reject(error)
  }
)

service.interceptors.response.use(
  (response: AxiosResponse) => {
    // 直接返回响应数据，而不是整个 response 对象
    return response.data;
  },
  (error) => {
    // 静默处理 404 错误（接口未实现）
    if (error.response?.status === 404) {
      // 只记录简要信息，不显示详细错误
      console.log(`[API] 接口未找到: ${error.config?.url}`);
      return Promise.reject(error);
    }

    // 处理 500 服务器错误
    if (error.response?.status === 500) {
      console.error('[API] 服务器内部错误 (500):', error.config?.url);
      // 检查响应内容是否为 HTML 错误页面
      const responseData = error.response.data;
      if (typeof responseData === 'string' && responseData.includes('<!doctype html>')) {
        console.error('[API] 服务器返回 HTML 错误页面，可能是 Django 未捕获异常');
      }
    }

    // 其他错误正常显示
    console.error('API 请求错误:', error);

    if (error.response) {
      console.error('响应状态码:', error.response.status);
      console.error('响应数据:', error.response.data);
    } else if (error.request) {
      console.error('无响应，请求已发送:', error.request);
    } else {
      console.error('请求配置错误:', error.message);
    }

    return Promise.reject(error)
  }
)

export default service
