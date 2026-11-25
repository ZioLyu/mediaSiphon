<script setup lang="ts">
/** 一套内联 SVG 图标：不依赖图标库，避免额外体积与版本问题。 */
type Name =
  | 'capture' | 'jobs' | 'settings' | 'play' | 'stop' | 'folder' | 'refresh'
  | 'check' | 'alert' | 'clock' | 'speed' | 'download'
  | 'plus' | 'x' | 'log' | 'spark' | 'live' | 'film'
  | 'panel-left' | 'copy'

const props = withDefaults(defineProps<{ name: Name; size?: number }>(), { size: 16 })

const paths: Record<Name, string> = {
  capture: 'M12 4v11m0 0l-4-4m4 4l4-4M5 19h14',
  jobs: 'M4 7h16M4 12h16M4 17h9',
  settings:
    'M12 9.2a2.8 2.8 0 1 0 0 5.6 2.8 2.8 0 0 0 0-5.6zm8 2.8c0-.4 0-.8-.1-1.2l1.9-1.4-1.9-3.3-2.2.9a6.4 6.4 0 0 0-2.2-1.3L15.2 3H8.8l-.3 2.7c-.9.3-1.6.7-2.2 1.3l-2.2-.9L2.2 9.4 4.1 10.8a7 7 0 0 0 0 2.4l-1.9 1.4 1.9 3.3 2.2-.9c.6.6 1.3 1 2.2 1.3l.3 2.7h6.4l.3-2.7c.9-.3 1.6-.7 2.2-1.3l2.2.9 1.9-3.3-1.9-1.4c.1-.4.1-.8.1-1.2z',
  play: 'M8 5l11 7-11 7z',
  stop: 'M7 7h10v10H7z',
  folder: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z',
  refresh: 'M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5',
  check: 'M4 12.5l5 5L20 6.5',
  alert:
    'M12 8v5m0 3.5v.5M10.3 3.9 2.6 17.2A2 2 0 0 0 4.3 20h15.4a2 2 0 0 0 1.7-2.8L13.7 3.9a2 2 0 0 0-3.4 0z',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2',
  speed: 'M12 20a8 8 0 1 1 0-16 8 8 0 0 1 0 16zm0-8 5-3',
  download: 'M12 4v11m0 0-4-4m4 4 4-4M5 19h14',
  plus: 'M12 5v14M5 12h14',
  x: 'M6 6l12 12M18 6 6 18',
  log: 'M6 3h9l5 5v13H6zM15 3v5h5',
  spark: 'M12 3l2.1 6.1 6.1 2.1-6.1 2.1L12 19.4l-2.1-6.1L3.8 11.2l6.1-2.1L12 3z',
  live: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6.3 6.3a8 8 0 0 0 0 11.4M17.7 6.3a8 8 0 0 1 0 11.4',
  film: 'M4 5h16v14H4zM8 5v14M16 5v14M4 9h4M4 15h4M16 9h4M16 15h4',
  'panel-left': 'M14 7l-5 5 5 5',
  copy: 'M8 8h10a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V8zM6 16H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h11a1 1 0 0 1 1 1v2',
}
</script>

<template>
  <svg
    :width="props.size"
    :height="props.size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="paths[props.name]" />
  </svg>
</template>

<style scoped>
svg {
  flex: none;
  display: block;
}
</style>
