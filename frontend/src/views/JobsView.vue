<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { store } from '../state/store'
import { api } from '../api/client'
import Icon from '../components/Icon.vue'

const props = defineProps<{ active?: boolean }>()

type FilterKey = 'all' | 'running' | 'done' | 'failed'

const filters: { key: FilterKey; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'running', label: '进行中' },
  { key: 'done', label: '已完成' },
  { key: 'failed', label: '失败' },
]

const RING = 2 * Math.PI * 20

const logOpen = ref<string | null>(null)
const logLines = ref<string[]>([])
const confirmId = ref<string | null>(null)
const purgeOnDelete = ref(false)

const filter = computed<FilterKey>({
  get: () => store.state.filter as FilterKey,
  set: (value) => store.setFilter(value),
})

const jobs = computed(() => {
  const all = [...store.state.jobs].sort((a, b) => b.createdAt - a.createdAt)
  if (filter.value === 'all') return all
  if (filter.value === 'running') {
    return all.filter((j) => j.status === 'running' || j.status === 'queued')
  }
  return all.filter((j) => j.status === filter.value)
})

const counts = computed(() => {
  const all = store.state.jobs
  return {
    all: all.length,
    running: all.filter((j) => j.status === 'running' || j.status === 'queued').length,
    done: all.filter((j) => j.status === 'done').length,
    failed: all.filter((j) => j.status === 'failed').length,
  }
})

/** 累计抓取量：只统计已下载字节，避免把失败任务的预估计入 */
const volume = computed(() => {
  let bytes = 0
  for (const job of store.state.jobs) {
    const downloaded = job.status === 'done' ? job.bytesTotal : job.progress?.haveBytes ?? 0
    bytes += downloaded || 0
  }
  return bytes
})

const volumeText = computed(() => {
  const bytes = volume.value
  if (!bytes) return '0 MB'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  return `${value.toFixed(index <= 1 ? 0 : 1)} ${units[index]}`
})

const statusMeta: Record<
  string,
  { label: string; cls: string; icon: 'clock' | 'download' | 'check' | 'alert' | 'x' }
> = {
  queued: { label: '排队中', cls: '', icon: 'clock' },
  running: { label: '进行中', cls: 'running', icon: 'download' },
  done: { label: '已完成', cls: 'done', icon: 'check' },
  failed: { label: '失败', cls: 'failed', icon: 'alert' },
  cancelled: { label: '已取消', cls: 'cancelled', icon: 'x' },
}

function percent(job: { status: string; progress?: { percent?: number } }): number {
  if (job.status === 'done') return 100
  const raw = job.progress?.percent
  if (typeof raw === 'number' && Number.isFinite(raw)) {
    return Math.min(100, Math.max(0, Math.round(raw)))
  }
  return 0
}

function ringOffset(job: { status: string; progress?: { percent?: number } }): number {
  return RING * (1 - percent(job) / 100)
}

function size(bytes: number): string {
  if (!bytes) return '—'
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  return `${value.toFixed(value >= 100 || index === 0 ? 0 : 1)} ${units[index]}`
}

function when(ts: number): string {
  const date = new Date(ts * 1000)
  const now = new Date()
  const sameDay = date.toDateString() === now.toDateString()
  return sameDay
    ? date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    : date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

async function openLog(id: string): Promise<void> {
  if (logOpen.value === id) {
    logOpen.value = null
    return
  }
  try {
    const { lines } = await api.jobLog(id, 300)
    logLines.value = lines
    logOpen.value = id
  } catch (err) {
    store.notify('warn', (err as Error).message)
  }
}

async function reveal(job: { outDir: string; fileHint: string }): Promise<void> {
  const target = job.fileHint || job.outDir
  if (!target) return
  try {
    const { ok } = await api.reveal(target)
    if (!ok) store.notify('warn', '无法打开位置')
  } catch (err) {
    store.notify('warn', (err as Error).message)
  }
}

function askDelete(id: string): void {
  confirmId.value = id
  purgeOnDelete.value = false
}

async function confirmDelete(): Promise<void> {
  if (!confirmId.value) return
  await store.deleteJob(confirmId.value, purgeOnDelete.value)
  confirmId.value = null
}

function copySource(source: string): void {
  navigator.clipboard?.writeText(source).then(
    () => store.notify('ok', '地址已复制'),
    () => store.notify('warn', '复制失败'),
  )
}

watch(
  () => props.active,
  (isActive) => {
    if (!isActive) return
    nextTick(() => {
      document.querySelectorAll<HTMLElement>('.view-jobs .reveal').forEach((el, index) => {
        el.classList.remove('in')
        window.setTimeout(() => el.classList.add('in'), index * 70)
      })
    })
  },
  { immediate: true },
)
</script>

<template>
  <div class="view-jobs">
    <!-- 统计行 -->
    <div class="stat-row reveal">
      <div class="stat">
        <b>{{ counts.all }}</b>
        <span>全部</span>
      </div>
      <div class="stat">
        <b>{{ counts.running }}</b>
        <span>进行中</span>
      </div>
      <div class="stat">
        <b>{{ counts.done }}</b>
        <span>已完成</span>
      </div>
      <div class="stat">
        <b>{{ counts.failed }}</b>
        <span>失败</span>
      </div>
      <div class="stat accent">
        <b>{{ volumeText }}</b>
        <span>累计抓取</span>
      </div>
    </div>

    <!-- 过滤 Tab -->
    <div class="tabs reveal" role="tablist">
      <button
        v-for="item in filters"
        :key="item.key"
        class="tab"
        :class="{ active: filter === item.key }"
        role="tab"
        :aria-selected="filter === item.key"
        @click="filter = item.key"
      >
        {{ item.label }}
      </button>
    </div>

    <div class="task-list reveal">
      <!-- 空态 -->
      <div v-if="!jobs.length" class="empty">
        <div class="empty-art">
          <svg viewBox="0 0 120 120" aria-hidden="true">
            <circle cx="60" cy="60" r="48" fill="var(--primary-container)" />
            <path
              d="M60 40l4 12 12 4-12 4-4 12-4-12-12-4 12-4 4-12z"
              fill="var(--primary)"
            />
            <circle cx="86" cy="38" r="4" fill="var(--primary)" opacity=".5" />
          </svg>
        </div>
        <h3>这里还很安静</h3>
        <p>去「抓取」页添加第一个地址吧。</p>
      </div>

      <!-- 任务卡片 -->
      <div
        v-for="job in jobs"
        :key="job.id"
        class="task-item"
        :class="statusMeta[job.status]?.cls"
      >
        <div class="ring">
          <svg viewBox="0 0 48 48">
            <circle class="ring-bg" cx="24" cy="24" r="20" />
            <circle
              class="ring-fg"
              cx="24"
              cy="24"
              r="20"
              :stroke-dasharray="RING"
              :stroke-dashoffset="ringOffset(job)"
            />
          </svg>
          <span v-if="job.status === 'queued'" class="ring-val idle">等待</span>
          <span v-else-if="job.status === 'done'" class="ring-val">✓</span>
          <span v-else-if="job.status === 'failed'" class="ring-val">!</span>
          <span v-else class="ring-val">{{ percent(job) }}%</span>
        </div>

        <div class="task-info">
          <div class="task-name">{{ job.title || '(未命名)' }}</div>
          <div class="task-url" :title="job.source">{{ job.source }}</div>
          <div class="task-meta">
            <span v-if="job.progress?.speed">{{ job.progress.speed }}</span>
            <span v-if="job.progress?.eta">剩余 {{ job.progress.eta }}</span>
            <span v-if="job.bytesTotal">{{ size(job.bytesTotal) }}</span>
            <span>{{ when(job.createdAt) }}</span>
            <span v-if="job.note" class="ellipsis">{{ job.note }}</span>
          </div>
        </div>

        <div class="task-side">
          <span class="task-status">
            {{ statusMeta[job.status]?.label ?? job.status }}
          </span>
          <div class="task-actions">
            <button
              v-if="job.status === 'running' || job.status === 'queued'"
              class="mini-btn"
              title="停止"
              @click="store.cancelJob(job.id)"
            >
              <Icon name="stop" :size="13" />
            </button>
            <button
              v-else
              class="mini-btn"
              title="重试"
              @click="store.retryJob(job.id)"
            >
              <Icon name="refresh" :size="13" />
            </button>
            <button class="mini-btn" title="打开位置" @click="reveal(job)">
              <Icon name="folder" :size="13" />
            </button>
            <button class="mini-btn" title="查看日志" @click="openLog(job.id)">
              <Icon name="log" :size="13" />
            </button>
            <button class="mini-btn" title="复制地址" @click="copySource(job.source)">
              <Icon name="copy" :size="13" />
            </button>
            <button class="mini-btn danger" title="移除" @click="askDelete(job.id)">
              <Icon name="x" :size="13" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 日志面板 -->
    <Transition name="slide">
      <section v-if="logOpen" class="panel log-panel">
        <div class="panel-head">
          <div class="panel-heading">
            <Icon name="log" :size="14" />
            <h2 class="mono-title">运行日志</h2>
          </div>
          <button class="link-btn" @click="logOpen = null">关闭</button>
        </div>
        <pre class="log-body">{{ logLines.join('\n') || '（暂无输出）' }}</pre>
      </section>
    </Transition>

    <!-- 删除确认 -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="confirmId" class="modal-mask" @click.self="confirmId = null">
          <div class="modal">
            <div class="modal-body">
              <p class="modal-title">删除这个任务？</p>
              <p class="muted">任务记录会从列表移除。</p>
              <label class="purge">
                <input v-model="purgeOnDelete" type="checkbox" />
                <span>同时删除已下载的视频文件</span>
              </label>
            </div>
            <div class="modal-foot">
              <span class="grow" />
              <button class="btn-text" @click="confirmId = null">取消</button>
              <button class="btn-filled" @click="confirmDelete">删除</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.mono-title {
  font: var(--type-label);
}

.log-panel {
  margin-top: var(--sp-4);
  margin-bottom: 0;
}

.modal-foot .btn-filled {
  background: var(--error);
  color: #fff;
}

.modal-foot .btn-filled:hover {
  filter: brightness(1.08);
}
</style>
