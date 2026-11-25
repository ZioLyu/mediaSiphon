<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { api, type ProbeResult, type Variant } from '../api/client'
import { store } from '../state/store'
import Icon from '../components/Icon.vue'
import Toggle from '../components/Toggle.vue'

const props = defineProps<{ active?: boolean }>()

const urlPlaceholder = 'https://example.com/index.m3u8 或 .mpd'
const bulkPlaceholder = '第一集,https://example.com/ep1.m3u8\nhttps://example.com/ep2.m3u8'

interface BulkRow {
  title: string
  url: string
}

const form = reactive({
  url: '',
  title: '',
  outDir: store.state.settings?.output_dir ?? '',
  isLive: false,
})

const options = reactive({
  autoTitle: true,
  keepTemp: store.state.settings?.keep_temp ?? false,
})

const probing = ref(false)
const submitting = ref(false)
const probe = ref<ProbeResult | null>(null)
const chosen = ref<number>(-1)

const bulkOpen = ref(false)
const bulkText = ref('')
const bulkRows = ref<BulkRow[]>([])

const sourceInput = ref<HTMLInputElement | null>(null)

const canSubmit = computed(() => form.url.trim().length > 0 && !submitting.value)
const playlistLike = computed(() => probe.value?.looksLikePlaylist ?? false)
const variantList = computed<Variant[]>(() => probe.value?.variants ?? [])

/** 协议标签：HLS / DASH / URL */
const protocol = computed(() => {
  const value = form.url.trim()
  if (!value) return ''
  if (/\.mpd(\?|#|$)/i.test(value)) return 'DASH'
  if (/\.m3u8(\?|#|$)/i.test(value)) return 'HLS'
  if (/^https?:\/\//i.test(value)) return 'URL'
  return ''
})

const previewMode = computed(() => (form.isLive ? '直播录制' : '点播下载'))
const previewDir = computed(() => {
  const dir = form.outDir || ''
  // 只显示最后一段目录名，完整路径放 title
  const parts = dir.split(/[\\/]/).filter(Boolean)
  return parts.length ? parts[parts.length - 1] : '默认目录'
})
const previewCount = computed(() => {
  if (bulkOpen.value && bulkRows.value.length) return `${bulkRows.value.length} 个`
  return form.url.trim() ? '1 个' : '0 个'
})
const previewName = computed(() => {
  if (form.title.trim()) return form.title.trim()
  if (bulkOpen.value && bulkRows.value.length) return `自动推断 × ${bulkRows.value.length}`
  return '自动推断'
})

let probeTimer: number | null = null

function onUrlInput(): void {
  probe.value = null
  chosen.value = -1
  if (probeTimer) window.clearTimeout(probeTimer)
  if (!form.url.trim()) return
  probeTimer = window.setTimeout(() => void runProbe(), 420)
}

async function runProbe(): Promise<void> {
  const url = form.url.trim()
  if (!url) return
  probing.value = true
  try {
    probe.value = await api.probe(url)
    if (variantList.value.length === 1) chosen.value = 0
    if (probe.value.kind === 'live') form.isLive = true
  } catch (err) {
    store.notify('warn', `探测失败：${(err as Error).message}`)
  } finally {
    probing.value = false
  }
}

function clearUrl(): void {
  form.url = ''
  probe.value = null
  chosen.value = -1
  nextTick(() => sourceInput.value?.focus())
}

function applyTitleFromUrl(): void {
  if (!options.autoTitle || form.title.trim()) return
  const clean = form.url.split('?')[0].split('#')[0]
  const base = clean.substring(clean.lastIndexOf('/') + 1)
  const stem = base.replace(/\.(m3u8|m3u|mpd)$/i, '')
  if (stem) form.title = decodeURIComponent(stem).replace(/[\\/:*?"<>|]/g, '_').slice(0, 120)
}

async function pickOutDir(): Promise<void> {
  try {
    const { path } = await api.pickDir(form.outDir)
    if (path) form.outDir = path
  } catch (err) {
    store.notify('warn', (err as Error).message)
  }
}

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  applyTitleFromUrl()
  const variant = chosen.value >= 0 ? variantList.value[chosen.value] : undefined

  submitting.value = true
  const ok = await store.startJob({
    url: form.url.trim(),
    title: form.title.trim(),
    outDir: form.outDir || undefined,
    variantWidth: variant?.width ?? 0,
    variantHeight: variant?.height ?? 0,
    variantFps: variant?.fps ?? 0,
    isLive: form.isLive,
    keepTemp: options.keepTemp,
  })
  submitting.value = false

  if (ok) {
    store.notify('ok', '已加入抓取队列')
    if (store.state.settings?.clear_form_after_submit) {
      form.url = ''
      form.title = ''
      probe.value = null
      chosen.value = -1
    }
  }
}

function parseBulk(): void {
  const rows: BulkRow[] = []
  for (const raw of bulkText.value.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line || line.startsWith('#')) continue
    const idx = line.indexOf(',')
    if (idx > 0) {
      const title = line.slice(0, idx).trim()
      const url = line.slice(idx + 1).trim()
      if (url) rows.push({ title, url })
    } else if (/^https?:\/\//i.test(line)) {
      rows.push({ title: '', url: line })
    }
  }
  bulkRows.value = rows
}

async function submitBulk(): Promise<void> {
  parseBulk()
  if (!bulkRows.value.length) {
    store.notify('warn', '没有解析到可用条目')
    return
  }
  const count = await store.startBatch(bulkRows.value, form.outDir)
  if (count > 0) {
    bulkText.value = ''
    bulkRows.value = []
    bulkOpen.value = false
  }
}

function toggleBulk(): void {
  bulkOpen.value = !bulkOpen.value
}

// 文件拖放：把路径或链接投递到输入框
function onDrop(event: DragEvent): void {
  event.preventDefault()
  const file = event.dataTransfer?.files?.[0]
  if (file) {
    form.url = file.name
    store.notify('ok', `已接收 ${file.name}`)
  } else {
    const text = event.dataTransfer?.getData('text') ?? ''
    if (text.trim()) {
      form.url = text.trim()
      store.notify('ok', '已接收链接')
    }
  }
  onUrlInput()
}

// 视图激活时重新触发交错淡入
watch(
  () => props.active,
  (isActive) => {
    if (!isActive) return
    nextTick(() => {
      document.querySelectorAll<HTMLElement>('.view-capture .reveal').forEach((el, index) => {
        el.classList.remove('in')
        window.setTimeout(() => el.classList.add('in'), index * 70)
      })
    })
  },
  { immediate: true },
)

/** Space 快捷启动：与设计稿一致，输入框内有焦点时不拦截 */
function onShortcut(event: KeyboardEvent): void {
  if (event.code !== 'Space') return
  const target = event.target
  if (target instanceof HTMLElement && target.matches('input, textarea, select, button')) return
  event.preventDefault()
  void submit()
}

onMounted(() => window.addEventListener('keydown', onShortcut))
onUnmounted(() => window.removeEventListener('keydown', onShortcut))
</script>

<template>
  <div class="view-capture">
    <div class="capture-layout">
      <div class="capture-primary">
        <!-- 01 源地址 -->
        <section class="panel reveal" @dragover.prevent @drop="onDrop">
          <div class="panel-head">
            <div class="panel-heading">
              <span class="panel-step">01</span>
              <h2>源地址</h2>
            </div>
            <button class="link-btn" @click="toggleBulk">
              {{ bulkOpen ? '− 收起' : '＋ 批量添加' }}
            </button>
          </div>
          <div class="panel-body">
            <div class="field-row">
              <label class="field-label" for="sourceUrl">清单地址</label>
              <div class="field-control">
                <div class="input-with-action">
                  <input
                    id="sourceUrl"
                    ref="sourceInput"
                    v-model="form.url"
                    type="text"
                    :placeholder="urlPlaceholder"
                    autocomplete="off"
                    spellcheck="false"
                    @input="onUrlInput"
                    @keydown.enter.prevent="submit"
                  />
                  <span class="protocol-tag" :hidden="!protocol">{{ protocol }}</span>
                  <button
                    v-if="form.url"
                    class="input-ico"
                    title="清空"
                    aria-label="清空"
                    @click="clearUrl"
                  >
                    <Icon name="x" :size="16" />
                  </button>
                  <button
                    v-else
                    class="input-ico"
                    title="探测"
                    aria-label="探测"
                    :disabled="probing"
                    @click="runProbe"
                  >
                    <Icon name="refresh" :size="16" />
                  </button>
                </div>
                <p class="field-help">
                  支持 .m3u8 / .mpd 直链或播放列表，也可将文件拖入此处
                  <template v-if="probing">
                    <span class="faint">· 正在探测…</span>
                  </template>
                  <template v-else-if="probe">
                    <span class="faint">
                      · {{ probe.kind === 'live' ? '直播流' : probe.kind === 'vod' ? '点播流' : '未识别' }}
                      · {{ variantList.length }} 个可变体
                    </span>
                  </template>
                </p>
              </div>
            </div>

            <div v-if="bulkOpen" class="batch-box">
              <div class="field-row">
                <label class="field-label" for="batchUrls">批量地址</label>
                <div class="field-control">
                  <textarea
                    id="batchUrls"
                    v-model="bulkText"
                    rows="4"
                    :placeholder="bulkPlaceholder"
                    @input="parseBulk"
                  />
                  <p class="field-help">
                    每行一条：<code>标题,地址</code> 或只写地址 ·
                    {{ bulkRows.length }} 条有效
                  </p>
                </div>
              </div>
              <div class="field-row">
                <span class="field-label" />
                <div class="field-control">
                  <button
                    class="btn-filled btn-sm"
                    :disabled="!bulkText.trim()"
                    @click="submitBulk"
                  >
                    <Icon name="download" :size="13" />批量加入队列
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 02 下载选项 -->
        <section class="panel reveal">
          <div class="panel-head">
            <div class="panel-heading">
              <span class="panel-step">02</span>
              <h2>下载选项</h2>
            </div>
            <span class="panel-meta">按需调整</span>
          </div>
          <div class="panel-body">
            <div class="field-row">
              <label class="field-label" for="fileName">保存名称</label>
              <div class="field-control">
                <input
                  id="fileName"
                  v-model="form.title"
                  type="text"
                  placeholder="留空则从地址推断"
                />
              </div>
            </div>

            <div class="field-row">
              <label class="field-label" for="saveDir">保存目录</label>
              <div class="field-control">
                <div class="input-with-action">
                  <input id="saveDir" v-model="form.outDir" type="text" placeholder="默认目录" />
                  <button class="input-ico" title="选择目录" aria-label="选择目录" @click="pickOutDir">
                    <Icon name="folder" :size="16" />
                  </button>
                </div>
              </div>
            </div>

            <!-- 清晰度选择 -->
            <div v-if="variantList.length" class="field-row">
              <span class="field-label">清晰度</span>
              <div class="field-control">
                <div class="variant-grid">
                  <button
                    v-for="(variant, index) in variantList"
                    :key="index"
                    class="variant"
                    :class="{ picked: chosen === index }"
                    @click="chosen = index"
                  >
                    <span class="row gap-2">
                      <Icon name="film" :size="13" />
                      <span>{{ variant.height ? `${variant.width}×${variant.height}` : '默认' }}</span>
                    </span>
                    <span class="faint mono">{{ variant.label || '—' }}</span>
                  </button>
                </div>
              </div>
            </div>
            <div v-else-if="playlistLike" class="field-row">
              <span class="field-label">清晰度</span>
              <div class="field-control">
                <p class="field-help">
                  <Icon name="alert" :size="13" /> 尚未探测到可变体，将使用引擎默认策略
                </p>
              </div>
            </div>

            <div class="divider" />

            <div class="switch-group">
              <Toggle v-model="form.isLive" label="直播录制" hint="按直播模式处理并实时合并分片" />
              <Toggle v-model="options.keepTemp" label="保留临时分片" hint="下载完成后保留 tmp 目录" />
              <Toggle v-model="options.autoTitle" label="自动生成名称" hint="保存名称为空时从地址推断" />
            </div>
          </div>
        </section>
      </div>

      <!-- 右侧检查器 -->
      <aside class="capture-side">
        <section class="panel inspector reveal">
          <div class="panel-head">
            <div class="panel-heading"><h2>任务预览</h2></div>
            <span v-if="form.isLive" class="live-chip"><i />LIVE</span>
          </div>

          <div class="inspector-art" aria-hidden="true">
            <svg viewBox="0 0 240 96">
              <path d="M8 48h224" stroke="var(--outline-variant)" stroke-width="1" stroke-dasharray="3 5" />
              <path
                class="pv-beam"
                d="M8 48h224"
                stroke="var(--primary)"
                stroke-width="2"
                stroke-dasharray="12 212"
              />
              <circle cx="8" cy="48" r="8" fill="var(--surface)" stroke="var(--tertiary)" stroke-width="1.5" />
              <circle cx="120" cy="48" r="8" fill="var(--surface)" stroke="var(--primary)" stroke-width="1.5" />
              <circle cx="232" cy="48" r="8" fill="var(--surface)" stroke="var(--tertiary)" stroke-width="1.5" />
              <text x="8" y="76" text-anchor="middle" fill="var(--on-surface-variant)" font-size="9" font-family="JetBrains Mono">IN</text>
              <text x="120" y="76" text-anchor="middle" fill="var(--on-surface-variant)" font-size="9" font-family="JetBrains Mono">PROCESS</text>
              <text x="232" y="76" text-anchor="middle" fill="var(--on-surface-variant)" font-size="9" font-family="JetBrains Mono">OUT</text>
            </svg>
          </div>

          <dl class="preview-list">
            <div>
              <dt>输出名称</dt>
              <dd :title="previewName">{{ previewName }}</dd>
            </div>
            <div>
              <dt>保存位置</dt>
              <dd :title="form.outDir">{{ previewDir }}</dd>
            </div>
            <div>
              <dt>捕获模式</dt>
              <dd>{{ previewMode }}</dd>
            </div>
            <div>
              <dt>任务数量</dt>
              <dd>{{ previewCount }}</dd>
            </div>
          </dl>

          <button class="btn-filled launch" :disabled="!canSubmit" @click="submit">
            <Icon name="play" :size="15" />
            {{ submitting ? '提交中…' : '开始抓取' }}
          </button>
          <p class="launch-hint">按 <kbd>Space</kbd> 快速启动</p>
        </section>

        <section class="panel activity-panel reveal">
          <div class="panel-head">
            <div class="panel-heading"><h2>活动</h2></div>
            <span class="panel-meta">LOG</span>
          </div>
          <ol class="activity-list" id="activityList">
            <li><i /><time>现在</time><span>引擎已就绪，等待地址</span></li>
          </ol>
        </section>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.capture-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 286px;
  gap: var(--sp-5);
  align-items: start;
}

.variant-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: var(--sp-2);
}

.variant {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border-radius: var(--r-xs);
  border: 1.5px solid var(--outline-variant);
  background: var(--background);
  text-align: left;
  font: var(--type-small);
  transition: all var(--dur-2) var(--ease-standard);
}

.variant:hover {
  border-color: var(--primary);
}

.variant.picked {
  border-color: var(--primary);
  background: var(--primary-container);
  color: var(--on-primary-container);
}

.field-help code {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  padding: 1px 4px;
  border-radius: 4px;
  background: var(--surface-variant);
}

.field-help {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

@media (max-width: 1080px) {
  .capture-layout {
    grid-template-columns: 1fr;
  }
  .capture-side {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--sp-4);
  }
}

@media (max-width: 720px) {
  .capture-side {
    grid-template-columns: 1fr;
  }
}
</style>
