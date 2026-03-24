import axios from 'axios'
import type { TripFormData, TripPlanResponse } from '@/types'
import { i18n } from '@/i18n'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''
const t = i18n.global.t

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 0, // 无超时限制，等待后端返回结果
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
apiClient.interceptors.request.use(
  (config) => {
    console.log('发送请求:', config.method?.toUpperCase(), config.url)
    return config
  },
  (error) => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => {
    console.log('收到响应:', response.status, response.config.url)
    return response
  },
  (error) => {
    console.error('响应错误:', error.response?.status, error.message)
    return Promise.reject(error)
  }
)

/**
 * 提交旅行规划任务（立即返回 task_id）
 */
export async function submitTripPlan(formData: TripFormData): Promise<{ task_id: string }> {
  try {
    const response = await apiClient.post('/api/trip/plan', formData)
    return response.data
  } catch (error: any) {
    console.error('提交旅行计划失败:', error)
    throw new Error(error.response?.data?.detail || error.message || t('api.submitTripPlanFailed'))
  }
}

/**
 * 轮询任务状态
 */
export async function pollTaskStatus(taskId: string): Promise<any> {
  try {
    const response = await apiClient.get(`/api/trip/status/${taskId}`)
    return response.data
  } catch (error: any) {
    console.error('查询任务状态失败:', error)
    throw new Error(error.response?.data?.detail || error.message || t('api.queryTaskStatusFailed'))
  }
}

/**
 * 生成旅行计划（兼容旧接口，内部使用轮询）
 */
export async function generateTripPlan(formData: TripFormData): Promise<TripPlanResponse> {
  // 1. 提交任务
  const { task_id } = await submitTripPlan(formData)

  // 2. 轮询结果（每3秒）
  return new Promise((resolve, reject) => {
    const interval = setInterval(async () => {
      try {
        const status = await pollTaskStatus(task_id)
        if (status.status === 'completed') {
          clearInterval(interval)
          resolve(status.result)
        } else if (status.status === 'failed') {
          clearInterval(interval)
          reject(new Error(status.error || t('api.generateTripPlanFailed')))
        }
        // status === 'processing' → 继续轮询
      } catch (err) {
        clearInterval(interval)
        reject(err)
      }
    }, 3000)
  })
}

/**
 * 健康检查
 */
export async function healthCheck(): Promise<any> {
  try {
    const response = await apiClient.get('/health')
    return response.data
  } catch (error: any) {
    console.error('健康检查失败:', error)
    throw new Error(error.message || t('api.healthCheckFailed'))
  }
}

export default apiClient

