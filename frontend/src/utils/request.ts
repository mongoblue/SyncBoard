import axios from 'axios'

const service = axios.create({
    baseURL:import.meta.env.Vite_API_URL,
    timeout:5000,
    xsrfCookieName: 'csrftoken', 
    xsrfHeaderName: 'X-CSRFToken', 
})

service.interceptors.request.use(
    (config) =>{
        //加请求头token
        return config;
    },
    error =>{
        return Promise.reject(error)
    }

)

service.interceptors.response.use(
    (reponse) =>{
        return reponse.data;
    },
    error =>{
        return Promise.reject(error)
    }
)

export default service;