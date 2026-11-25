/** 全局状态：设置 + 任务 + 实时进度。用简单的 reactive store，不引入额外依赖。 */

import { reactive, readonly } from 'vue'
import { api, type Job, type JobStatus, type ProgressPayload, type Settings, type StartPayload } from '../api/client'

interface JobState extends Job {
  progress?: ProgressPayload
  thumb?: string
}

interface State {
  ready: boolean
  engineReady: boolean
  version: string
  settings: Settings | null
  jobs: JobState[]
  filter: JobStatus | 'all'
  toast: { id: number; level: 'ok' | 'warn' | 'bad'; text: string } | null
}

const state = reactive<State>({
  ready: false,
  engineReady: false,
  version: '',
  settings: null,
  jobs: [],
  filter: 'all',
  toast: null,
})

let toastSeq = 0

function findJob(id: string): JobState | undefined {
  return state.jobs.find((job) => job.id === id)
}

function upsert(job: Job): void {
  const existing = findJob(job.id)
  if (existing) {
    Object.assign(existing, job)
    return
  }
  state.jobs.unshift({ ...job })
}

export const store = {
  state: readonly(state) as Readonly<State>,

  async bootstrap(): Promise<void> {
    try {
      const health = await api.health()
      state.version = health.version
      state.engineReady = health.engineReady
      state.settings = await api.getSettings()
      const { jobs } = await api.listJobs('all')
      state.jobs = jobs.map((job) => ({ ...job }))
      state.ready = true
    } catch (err) {
      this.notify('bad', `后端未就绪：${(err as Error).message}`)
    }
  },

  setFilter(filter: JobStatus | 'all'): void {
    state.filter = filter
  },

  notify(level: 'ok' | 'warn' | 'bad', text: string): void {
    state.toast = { id: ++toastSeq, level, text }
    const current = state.toast.id
    window.setTimeout(() => {
      if (state.toast?.id === current) state.toast = null
    }, 4200)
  },

  dismissToast(): void {
    state.toast = null
  },

  async saveSettings(patch: Partial<Settings>): Promise<void> {
    try {
      state.settings = await api.patchSettings(patch)
      if ('downloader_exe' in patch) {
        const health = await api.health()
        state.engineReady = health.engineReady
      }
      this.notify('ok', '设置已保存')
    } catch (err) {
      this.notify('bad', (err as Error).message)
    }
  },

  async resetSettings(): Promise<void> {
    try {
      state.settings = await api.resetSettings()
      this.notify('ok', '已恢复默认设置')
    } catch (err) {
      this.notify('bad', (err as Error).message)
    }
  },

  async refreshJobs(): Promise<void> {
    try {
      const { jobs } = await api.listJobs('all')
      state.jobs = jobs.map((job) => {
        const previous = findJob(job.id)
        return { ...job, progress: previous?.progress, thumb: previous?.thumb }
      })
    } catch (err) {
      this.notify('bad', (err as Error).message)
    }
  },

  async startJob(payload: StartPayload): Promise<boolean> {
    try {
      const job = await api.startJob(payload)
      upsert(job)
      return true
    } catch (err) {
      this.notify('bad', (err as Error).message)
      return false
    }
  },

  async startBatch(items: { title: string; url: string }[], outDir = ''): Promise<number> {
    try {
      const result = await api.startBatch(items, outDir)
      result.created.forEach(upsert)
      if (result.skipped.length) {
        this.notify('warn', `${result.created.length} 条已加入，${result.skipped.length} 条被跳过`)
      } else {
        this.notify('ok', `${result.created.length} 条任务已加入队列`)
      }
      return result.created.length
    } catch (err) {
      this.notify('bad', (err as Error).message)
      return 0
    }
  },

  async cancelJob(id: string): Promise<void> {
    try {
      await api.cancelJob(id)
    } catch (err) {
      this.notify('bad', (err as Error).message)
    }
  },

  async retryJob(id: string): Promise<void> {
    try {
      const job = await api.retryJob(id)
      upsert(job)
      this.notify('ok', '已重新提交')
    } catch (err) {
      this.notify('bad', (err as Error).message)
    }
  },

  async deleteJob(id: string, purge: boolean): Promise<void> {
    try {
      const result = await api.deleteJob(id, purge)
      state.jobs = state.jobs.filter((job) => job.id !== id)
      this.notify('ok', result.removedFile ? '任务与文件已删除' : '任务已删除')
    } catch (err) {
      this.notify('bad', (err as Error).message)
    }
  },

  applyEvent(event: Record<string, unknown>): void {
    const type = event.type as string
    switch (type) {
      case 'job.created': {
        const job = event.job as Job
        if (job) upsert(job)
        break
      }
      case 'job.status': {
        const job = findJob(event.id as string)
        if (job) {
          job.status = event.status as JobStatus
          job.updatedAt = Date.now() / 1000
        }
        break
      }
      case 'job.progress': {
        const job = findJob(event.id as string)
        if (job) {
          job.progress = event.progress as ProgressPayload
          if (job.progress.totalBytes) job.bytesTotal = job.progress.totalBytes
        }
        break
      }
      case 'job.thumb': {
        const job = findJob(event.id as string)
        if (job) job.thumb = event.thumb as string
        break
      }
      case 'job.finished': {
        const job = findJob(event.id as string)
        if (job) {
          job.status = event.status as JobStatus
          job.note = (event.note as string) || job.note
          if (event.file) job.fileHint = event.file as string
          if (event.bytes) job.bytesTotal = event.bytes as number
          job.progress = undefined
        }
        if (event.status === 'done') this.notify('ok', `完成：${job?.title ?? ''}`)
        else if (event.status === 'failed') this.notify('bad', `失败：${job?.title ?? ''}`)
        break
      }
      case 'job.deleted': {
        state.jobs = state.jobs.filter((job) => job.id !== event.id)
        break
      }
      case 'settings.changed': {
        state.settings = event.settings as Settings
        break
      }
      default:
        break
    }
  },
}
