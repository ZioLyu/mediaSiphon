<script setup lang="ts">
import { toRef } from 'vue'
import { store } from '../state/store'
import Icon from './Icon.vue'

const toast = toRef(store.state, 'toast')

const icons = { ok: 'check', warn: 'alert', bad: 'alert' } as const
</script>

<template>
  <Transition name="slide">
    <div v-if="toast" :key="toast.id" class="toast show" :class="toast.level">
      <Icon :name="icons[toast.level]" :size="15" />
      <span class="grow">{{ toast.text }}</span>
      <button class="toast-x" aria-label="关闭" @click="store.dismissToast()">
        <Icon name="x" :size="13" />
      </button>
    </div>
  </Transition>
</template>

<style scoped>
.toast.ok :deep(svg) {
  color: var(--success);
}
.toast.warn :deep(svg) {
  color: var(--warn);
}
.toast.bad :deep(svg) {
  color: var(--error);
}
.toast.ok > svg {
  color: var(--success);
}
.toast.warn > svg {
  color: var(--warn);
}
.toast.bad > svg {
  color: var(--error);
}
</style>
