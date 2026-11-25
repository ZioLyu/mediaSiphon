<script setup lang="ts">
const props = defineProps<{
  modelValue: boolean
  label?: string
  hint?: string
  disabled?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

function toggle(): void {
  if (props.disabled) return
  emit('update:modelValue', !props.modelValue)
}
</script>

<template>
  <div class="switch-row">
    <div v-if="props.label || props.hint" class="switch-copy grow">
      <b v-if="props.label">{{ props.label }}</b>
      <small v-if="props.hint">{{ props.hint }}</small>
    </div>
    <label class="switch" :class="{ disabled: props.disabled }">
      <input
        type="checkbox"
        role="switch"
        :checked="props.modelValue"
        :disabled="props.disabled"
        :aria-checked="props.modelValue"
        @change="toggle"
      />
      <span />
    </label>
  </div>
</template>
