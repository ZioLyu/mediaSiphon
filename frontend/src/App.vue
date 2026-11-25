<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, toRef, watch } from 'vue'
import { store } from './state/store'
import Icon from './components/Icon.vue'
import ToastHost from './components/ToastHost.vue'
import CaptureView from './views/CaptureView.vue'
import JobsView from './views/JobsView.vue'
import SettingsView from './views/SettingsView.vue'

type Tab = 'capture' | 'jobs' | 'settings'

const tab = ref<Tab>('capture')
const collapsed = ref(false)
const settings = toRef(store.state, 'settings')
const jobs = toRef(store.state, 'jobs')
const ready = toRef(store.state, 'ready')

const pageMeta: Record<Tab, { title: string; sub: string }> = {
  capture: { title: '抓取', sub: '添加地址并开始捕获' },
  jobs: { title: '任务', sub: '查看所有捕获任务的进度' },
  settings: { title: '设置', sub: '调整工具路径与偏好' },
}

const running = computed(
  () => jobs.value.filter((j) => j.status === 'running' || j.status === 'queued').length,
)

const totalSpeed = computed(() => {
  let bytes = 0
  for (const job of jobs.value) {
    const raw = job.progress?.speed ?? ''
    const match = /([\d.]+)\s*([KMGB]?)B\/s/i.exec(raw)
    if (!match) continue
    const scale =
      ({ '': 1, K: 1024, M: 1024 ** 2, G: 1024 ** 3 } as Record<string, number>)[
        match[2].toUpperCase()
      ] ?? 1
    bytes += parseFloat(match[1]) * scale
  }
  if (!bytes) return '0.00 MB/s'
  return bytes >= 1024 ** 2
    ? `${(bytes / 1024 ** 2).toFixed(2)} MB/s`
    : `${(bytes / 1024).toFixed(0)} KB/s`
})

const engineReady = computed(() => store.state.engineReady)

const navItems = computed(() => [
  {
    key: 'capture' as Tab,
    label: '抓取',
    icon: 'capture' as const,
    group: '工作区',
    kbd: '1',
  },
  {
    key: 'jobs' as Tab,
    label: '任务',
    icon: 'jobs' as const,
    group: '工作区',
    kbd: '',
  },
  {
    key: 'settings' as Tab,
    label: '设置',
    icon: 'settings' as const,
    group: '偏好',
    kbd: '3',
  },
])

function switchTab(next: Tab): void {
  tab.value = next
}

function onToolbarRefresh(): void {
  store.refreshJobs().then(() => store.notify('ok', '已刷新'))
}

function onToolbarNew(): void {
  switchTab('capture')
  window.setTimeout(() => {
    document.querySelector<HTMLInputElement>('#sourceUrl')?.focus()
  }, 60)
}

function applyTheme(): void {
  const mode = settings.value?.theme ?? 'auto'
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
  const resolved = mode === 'auto' ? (prefersDark ? 'dark' : 'light') : mode
  document.documentElement.dataset.theme = resolved

  // 强调色：只有落在设计稿预设内才采纳，靛蓝为 token 默认值，无需额外属性
  const accent = (settings.value?.accent ?? '').toLowerCase()
  const preset = accentToPreset(accent)
  if (preset && preset !== 'indigo') document.documentElement.dataset.accent = preset
  else delete document.documentElement.dataset.accent

  // --accent 是旧组件沿用的变量名，需要跟随当前主色
  document.documentElement.style.removeProperty('--accent')
}

/** 把 accent 色映射到设计稿的四套预设之一，未知色值返回空串 */
function accentToPreset(accent: string): string {
  const table: Record<string, string> = {
    '#5b5bd6': 'indigo',
    '#7b61ff': 'violet',
    '#0e9e87': 'teal',
    '#0e8f7e': 'teal',
    '#c2562f': 'coral',
    '#e07a5f': 'coral',
  }
  return table[accent] ?? ''
}

watch(settings, applyTheme, { deep: true })

function onKeydown(event: KeyboardEvent): void {
  const target = event.target
  if (target instanceof HTMLElement && target.matches('input, textarea, select')) return
  if (event.key === '1') switchTab('capture')
  else if (event.key === '2') switchTab('jobs')
  else if (event.key === '3') switchTab('settings')
}

onMounted(() => {
  applyTheme()
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyTheme)
  window.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="window" :class="{ collapsed }">
    <div class="window-body">
      <!-- 侧栏 -->
      <aside class="sidebar">
        <div class="sidebar-brand">
          <div class="app-icon"><Icon name="spark" :size="20" /></div>
          <div class="brand-copy">
            <strong>mediaSiphon</strong>
            <span>流媒体抓取</span>
          </div>
        </div>

        <nav class="side-nav" aria-label="主导航">
          <template v-for="(item, index) in navItems" :key="item.key">
            <p
              v-if="index === 0 || navItems[index - 1].group !== item.group"
              class="nav-group"
            >
              {{ item.group }}
            </p>
            <button
              class="nav-item"
              :class="{ active: tab === item.key }"
              :title="item.label"
              @click="switchTab(item.key)"
            >
              <span class="nav-ico"><Icon :name="item.icon" :size="19" /></span>
              <span class="nav-text">{{ item.label }}</span>
              <kbd v-if="item.kbd">{{ item.kbd }}</kbd>
              <b
                v-if="item.key === 'jobs' && running"
                class="nav-count"
                :data-zero="running === 0"
              >{{ running }}</b>
            </button>
          </template>
        </nav>

        <div class="sidebar-bottom">
          <div class="engine-card" :class="{ bad: !engineReady }">
            <span class="engine-dot" />
            <div>
              <b>{{ engineReady ? '引擎就绪' : '引擎缺失' }}</b>
              <small>N_m3u8DL-RE</small>
            </div>
          </div>
          <button
            class="collapse-btn"
            :title="collapsed ? '展开侧边栏' : '折叠侧边栏'"
            aria-label="折叠侧边栏"
            @click="collapsed = !collapsed"
          >
            <Icon name="panel-left" :size="18" />
          </button>
        </div>
      </aside>

      <!-- 内容区 -->
      <div class="content">
        <div class="toolbar">
          <div class="toolbar-title">
            <h1>{{ pageMeta[tab].title }}</h1>
            <span class="toolbar-sub">{{ pageMeta[tab].sub }}</span>
          </div>
          <div class="toolbar-actions">
            <button class="tool-btn" @click="onToolbarRefresh">
              <Icon name="refresh" :size="16" /><span>刷新</span>
            </button>
            <button class="tool-btn primary" @click="onToolbarNew">
              <Icon name="plus" :size="16" /><span>新建任务</span>
            </button>
          </div>
        </div>

        <main class="content-scroll">
          <Transition name="fade" mode="out-in">
            <CaptureView v-if="tab === 'capture'" key="capture" :active="tab === 'capture'" />
            <JobsView v-else-if="tab === 'jobs'" key="jobs" :active="tab === 'jobs'" />
            <SettingsView v-else key="settings" :active="tab === 'settings'" />
          </Transition>
        </main>
      </div>
    </div>

    <!-- 状态栏 -->
    <footer class="statusbar">
      <div class="status-left">
        <span class="status-item">
          <i class="status-dot" :class="{ bad: !engineReady }" />
          {{ engineReady ? '引擎就绪' : '引擎缺失' }}
        </span>
        <span class="status-sep" />
        <span class="status-item">{{ jobs.length }} 个任务</span>
        <span v-if="running" class="status-sep" />
        <span v-if="running" class="status-item">{{ running }} 个进行中</span>
      </div>
      <div class="status-right">
        <span class="status-item">{{ totalSpeed }}</span>
        <span class="status-sep" />
        <span class="status-item">v{{ store.state.version || '0.1.0' }}</span>
      </div>
    </footer>
  </div>

  <ToastHost />

  <Transition name="fade">
    <div v-if="!ready" class="boot">
      <div class="spinner" />
      <span class="faint">正在连接本地服务…</span>
    </div>
  </Transition>
</template>
