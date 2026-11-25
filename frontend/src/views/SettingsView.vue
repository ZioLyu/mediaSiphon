<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { api, type Settings } from '../api/client'
import { store } from '../state/store'
import Icon from '../components/Icon.vue'

const props = defineProps<{ active?: boolean }>()

const proxyPlaceholder = 'http://127.0.0.1:7890'
const refererPlaceholder = 'https://example.com/'

type PanelKey = 'paths' | 'params' | 'live' | 'ui'

const panels: { key: PanelKey; label: string; icon: string }[] = [
  { key: 'paths', label: '位置与引擎', icon: '⌂' },
  { key: 'params', label: '抓取参数', icon: '↓' },
  { key: 'live', label: '直播与封装', icon: '◉' },
  { key: 'ui', label: '界面', icon: '✦' },
]

const panel = ref<PanelKey>('paths')
const draft = reactive<Partial<Settings>>({})

watch(
  () => store.state.settings,
  (settings) => {
    if (settings) Object.assign(draft, settings)
  },
  { immediate: true, deep: true },
)

const dirty = computed(() => {
  const base = store.state.settings
  if (!base) return false
  return (Object.keys(draft) as (keyof Settings)[]).some((key) => draft[key] !== base[key])
})

const accents = [
  { value: '#5b5bd6', label: '靛蓝' },
  { value: '#7b61ff', label: '紫罗兰' },
  { value: '#0e9e87', label: '青绿' },
  { value: '#c2562f', label: '珊瑚' },
]

function set<K extends keyof Settings>(key: K, value: Settings[K]): void {
  draft[key] = value
}

function str(key: keyof Settings): string {
  const value = draft[key]
  return value === undefined || value === null ? '' : String(value)
}

function num(key: keyof Settings): number | string {
  const value = draft[key]
  return typeof value === 'number' ? value : ''
}

function onNumber(key: keyof Settings, event: Event): void {
  const raw = (event.target as HTMLInputElement).value
  set(key, (raw === '' ? 0 : Number(raw)) as never)
}

async function save(): Promise<void> {
  await store.saveSettings(draft)
}

async function resetAll(): Promise<void> {
  await store.resetSettings()
}

async function pickDirFor(key: keyof Settings, current: string): Promise<void> {
  try {
    const { path } = await api.pickDir(current)
    if (path) set(key, path as never)
  } catch (err) {
    store.notify('warn', (err as Error).message)
  }
}

/** 选择可执行文件：后端只有选目录接口，因此传当前所在目录并在结果里取上一级 */
async function pickExe(key: keyof Settings): Promise<void> {
  const current = str(key)
  const dir = current.replace(/[\\/][^\\/]*$/, '')
  try {
    const { path } = await api.pickDir(dir)
    if (path && path !== dir) set(key, path as never)
  } catch (err) {
    store.notify('warn', (err as Error).message)
  }
}

watch(
  () => props.active,
  (isActive) => {
    if (!isActive) return
    nextTick(() => {
      document.querySelectorAll<HTMLElement>('.view-settings .reveal').forEach((el) => {
        el.classList.remove('in')
        window.setTimeout(() => el.classList.add('in'), 60)
      })
    })
  },
  { immediate: true },
)
</script>

<template>
  <div class="view-settings">
    <div class="settings-layout reveal">
      <nav class="settings-nav" aria-label="设置分组">
        <button
          v-for="item in panels"
          :key="item.key"
          class="settings-tab"
          :class="{ active: panel === item.key }"
          @click="panel = item.key"
        >
          <span>{{ item.icon }}</span>{{ item.label }}
        </button>
      </nav>

      <div class="settings-content">
        <!-- 位置与引擎 -->
        <section class="settings-panel" :class="{ active: panel === 'paths' }">
          <header class="settings-head">
            <h2>位置与引擎</h2>
            <p>外部工具路径与默认保存位置</p>
          </header>
          <div class="settings-body">
            <div class="field-row">
              <label class="field-label" for="setSaveDir">保存目录</label>
              <div class="field-control">
                <div class="input-with-action">
                  <input id="setSaveDir" :value="str('output_dir')" type="text" @input="set('output_dir', ($event.target as HTMLInputElement).value)" />
                  <button class="input-ico" aria-label="选择目录" @click="pickDirFor('output_dir', str('output_dir'))">
                    <Icon name="folder" :size="16" />
                  </button>
                </div>
              </div>
            </div>

            <div class="field-row">
              <label class="field-label" for="setEngine">下载引擎</label>
              <div class="field-control">
                <div class="input-with-action">
                  <input id="setEngine" :value="str('downloader_exe')" type="text" @input="set('downloader_exe', ($event.target as HTMLInputElement).value)" />
                  <button class="input-ico" aria-label="选择文件" @click="pickExe('downloader_exe')">
                    <Icon name="folder" :size="16" />
                  </button>
                </div>
                <p class="field-help">N_m3u8DL-RE 可执行文件位置</p>
              </div>
            </div>

            <div class="field-row">
              <label class="field-label" for="setFfmpeg">多媒体工具</label>
              <div class="field-control">
                <div class="input-with-action">
                  <input id="setFfmpeg" :value="str('remuxer_exe')" type="text" @input="set('remuxer_exe', ($event.target as HTMLInputElement).value)" />
                  <button class="input-ico" aria-label="选择文件" @click="pickExe('remuxer_exe')">
                    <Icon name="folder" :size="16" />
                  </button>
                </div>
                <p class="field-help">ffmpeg 可执行文件位置</p>
              </div>
            </div>
          </div>
        </section>

        <!-- 抓取参数 -->
        <section class="settings-panel" :class="{ active: panel === 'params' }">
          <header class="settings-head">
            <h2>抓取参数</h2>
            <p>并发、限速与网络行为</p>
          </header>
          <div class="settings-body">
            <div class="field-row">
              <span class="field-label">并发与重试</span>
              <div class="field-control inline-fields">
                <div class="inline-field">
                  <label for="setThreads">并发分片数</label>
                  <input id="setThreads" type="number" min="1" max="128" :value="num('parallel_fragments')" @input="onNumber('parallel_fragments', $event)" />
                </div>
                <div class="inline-field">
                  <label for="setRetry">重试次数</label>
                  <input id="setRetry" type="number" min="0" max="50" :value="num('fragment_retries')" @input="onNumber('fragment_retries', $event)" />
                </div>
              </div>
            </div>

            <div class="field-row">
              <span class="field-label">请求控制</span>
              <div class="field-control inline-fields">
                <div class="inline-field">
                  <label for="setTimeout">超时 (秒)</label>
                  <input id="setTimeout" type="number" min="5" max="600" :value="num('request_timeout')" @input="onNumber('request_timeout', $event)" />
                </div>
                <div class="inline-field">
                  <label for="setLimit">限速 (KiB/s)</label>
                  <input id="setLimit" type="number" min="0" :value="num('speed_limit_kib')" @input="onNumber('speed_limit_kib', $event)" />
                </div>
              </div>
            </div>

            <div class="field-row">
              <label class="field-label" for="setProxy">代理模式</label>
              <div class="field-control">
                <select id="setProxy" :value="str('proxy_mode')" @change="set('proxy_mode', ($event.target as HTMLSelectElement).value as Settings['proxy_mode'])">
                  <option value="system">跟随系统</option>
                  <option value="none">不使用代理</option>
                  <option value="manual">手动代理</option>
                </select>
              </div>
            </div>

            <div class="field-row">
              <label class="field-label" for="setProxyAddr">手动代理</label>
              <div class="field-control">
                <input
                  id="setProxyAddr"
                  type="text"
                  :placeholder="proxyPlaceholder"
                  :disabled="draft.proxy_mode !== 'manual'"
                  :value="str('manual_proxy')"
                  @input="set('manual_proxy', ($event.target as HTMLInputElement).value)"
                />
              </div>
            </div>

            <div class="field-row">
              <label class="field-label" for="setHeaders">附加请求头</label>
              <div class="field-control">
                <textarea id="setHeaders" rows="3" :value="str('extra_headers')" placeholder="User-Agent: Mozilla/5.0&#10;Cookie: session=..." @input="set('extra_headers', ($event.target as HTMLTextAreaElement).value)" />
              </div>
            </div>

            <div class="field-row">
              <label class="field-label" for="setReferer">Referer</label>
              <div class="field-control">
                <input id="setReferer" type="text" :placeholder="refererPlaceholder" :value="str('referer')" @input="set('referer', ($event.target as HTMLInputElement).value)" />
              </div>
            </div>

            <div class="field-row">
              <span class="field-label">临时分片</span>
              <div class="field-control">
                <div class="switch-row">
                  <div class="switch-copy"><b>保留临时分片</b><small>下载完成后不删除 tmp 目录</small></div>
                  <label class="switch">
                    <input type="checkbox" :checked="Boolean(draft.keep_temp)" @change="set('keep_temp', ($event.target as HTMLInputElement).checked)" />
                    <span />
                  </label>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 直播与封装 -->
        <section class="settings-panel" :class="{ active: panel === 'live' }">
          <header class="settings-head">
            <h2>直播与封装</h2>
            <p>直播录制、解密与封装设置</p>
          </header>
          <div class="settings-body">
            <div class="field-row">
              <span class="field-label">直播</span>
              <div class="field-control">
                <div class="switch-row">
                  <div class="switch-copy"><b>实时合并</b><small>录制同时合并为可播放文件</small></div>
                  <label class="switch">
                    <input type="checkbox" :checked="Boolean(draft.live_realtime_merge)" @change="set('live_realtime_merge', ($event.target as HTMLInputElement).checked)" />
                    <span />
                  </label>
                </div>
                <div class="switch-row">
                  <div class="switch-copy"><b>保留直播分片</b></div>
                  <label class="switch">
                    <input type="checkbox" :checked="Boolean(draft.live_keep_fragments)" @change="set('live_keep_fragments', ($event.target as HTMLInputElement).checked)" />
                    <span />
                  </label>
                </div>
              </div>
            </div>

            <div class="field-row">
              <span class="field-label">停止与轮询</span>
              <div class="field-control inline-fields">
                <div class="inline-field">
                  <label for="setStop">自动停止时长</label>
                  <input id="setStop" type="text" placeholder="01:30:00" :value="str('live_stop_after')" @input="set('live_stop_after', ($event.target as HTMLInputElement).value)" />
                </div>
                <div class="inline-field">
                  <label for="setPoll">轮询间隔 (秒)</label>
                  <input id="setPoll" type="number" min="0" :value="num('live_poll_interval')" @input="onNumber('live_poll_interval', $event)" />
                </div>
              </div>
            </div>

            <div class="field-row">
              <label class="field-label" for="setDecrypt">解密引擎</label>
              <div class="field-control">
                <select id="setDecrypt" :value="str('decrypt_engine')" @change="set('decrypt_engine', ($event.target as HTMLSelectElement).value as Settings['decrypt_engine'])">
                  <option value="ffmpeg">ffmpeg</option>
                  <option value="mp4decrypt">mp4decrypt</option>
                  <option value="shaka">shaka packager</option>
                </select>
              </div>
            </div>

            <div class="field-row">
              <span class="field-label">封装</span>
              <div class="field-control inline-fields">
                <div class="inline-field">
                  <label for="setMux">封装参数</label>
                  <input id="setMux" type="text" placeholder="format=mp4" :value="str('remux_after_done')" @input="set('remux_after_done', ($event.target as HTMLInputElement).value)" />
                </div>
                <div class="inline-field">
                  <label for="setToolPath">解密工具路径</label>
                  <input id="setToolPath" type="text" placeholder="可选" :value="str('decrypt_tool_path')" @input="set('decrypt_tool_path', ($event.target as HTMLInputElement).value)" />
                </div>
              </div>
            </div>

            <div class="field-row">
              <label class="field-label" for="setKeys">密钥列表</label>
              <div class="field-control">
                <textarea id="setKeys" rows="2" placeholder="KID:KEY&#10;..." :value="str('decrypt_keys')" @input="set('decrypt_keys', ($event.target as HTMLTextAreaElement).value)" />
              </div>
            </div>

            <div class="field-row">
              <label class="field-label" for="setExtra">封装附加项</label>
              <div class="field-control">
                <textarea id="setExtra" rows="2" placeholder="path=video.mp4, lang=zh&#10;..." :value="str('remux_imports')" @input="set('remux_imports', ($event.target as HTMLTextAreaElement).value)" />
              </div>
            </div>
          </div>
        </section>

        <!-- 界面 -->
        <section class="settings-panel" :class="{ active: panel === 'ui' }">
          <header class="settings-head">
            <h2>界面</h2>
            <p>外观、语言与表单行为</p>
          </header>
          <div class="settings-body">
            <div class="field-row">
              <label class="field-label" for="setTheme">主题</label>
              <div class="field-control">
                <select id="setTheme" :value="str('theme')" @change="set('theme', ($event.target as HTMLSelectElement).value as Settings['theme'])">
                  <option value="auto">跟随系统</option>
                  <option value="light">浅色 · 明亮</option>
                  <option value="dark">深色 · 暗夜</option>
                </select>
              </div>
            </div>

            <div class="field-row">
              <span class="field-label">强调色</span>
              <div class="field-control">
                <div class="swatches">
                  <button
                    v-for="item in accents"
                    :key="item.value"
                    class="swatch"
                    :class="{ active: (str('accent') || '#5b5bd6').toLowerCase() === item.value }"                    :style="{ '--sw': item.value }"
                    :aria-label="item.label"
                    :title="item.label"
                    @click="set('accent', item.value)"
                  />
                </div>
              </div>
            </div>

            <div class="field-row">
              <label class="field-label" for="setLang">语言</label>
              <div class="field-control">
                <select id="setLang" :value="str('locale')" @change="set('locale', ($event.target as HTMLSelectElement).value)">
                  <option value="zh-CN">简体中文</option>
                  <option value="zh-TW">繁體中文</option>
                  <option value="en-US">English</option>
                </select>
              </div>
            </div>

            <div class="field-row">
              <span class="field-label">表单行为</span>
              <div class="field-control">
                <div class="switch-row">
                  <div class="switch-copy"><b>提交后清空表单</b></div>
                  <label class="switch">
                    <input type="checkbox" :checked="Boolean(draft.clear_form_after_submit)" @change="set('clear_form_after_submit', ($event.target as HTMLInputElement).checked)" />
                    <span />
                  </label>
                </div>
                <div class="switch-row">
                  <div class="switch-copy"><b>启动时检查更新</b></div>
                  <label class="switch">
                    <input type="checkbox" :checked="Boolean(draft.check_update_on_launch)" @change="set('check_update_on_launch', ($event.target as HTMLInputElement).checked)" />
                    <span />
                  </label>
                </div>
              </div>
            </div>
          </div>
        </section>

        <footer class="settings-footer">
          <button class="btn-text" @click="resetAll">恢复默认</button>
          <span class="grow" />
          <span v-if="dirty" class="faint dirty-hint">有未保存的更改</span>
          <button class="btn-filled" :disabled="!dirty" @click="save">保存设置</button>
        </footer>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dirty-hint {
  align-self: center;
  font: var(--type-small);
}
</style>
