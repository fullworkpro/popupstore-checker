<template>
  <img
    v-if="!errored"
    :src="resolved"
    :style="style"
    :alt="alt"
    @error="onError"
    @load="onLoad"
  />
  <div v-else class="safe-image-fallback" :style="style" :title="`图片加载失败：${raw || '空地址'}`">
    <el-icon class="si-icon"><Picture /></el-icon>
    <span class="si-text">图片加载失败</span>
    <span v-if="raw" class="si-url">{{ raw }}</span>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Picture } from '@element-plus/icons-vue'
import { resolveImage } from '../utils/image'

const props = defineProps({
  src: { type: String, default: '' },
  alt: { type: String, default: '' },
  // 透传样式（宽高、圆角、边框等）
  style: { type: [String, Object], default: '' },
})

const raw = computed(() => props.src || '')
const resolved = computed(() => resolveImage(raw.value))
const errored = ref(false)

function onError() {
  errored.value = true
}
function onLoad() {
  errored.value = false
}
</script>

<style scoped>
.safe-image-fallback {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  background: #f5f5f5;
  color: #f56c6c;
  border: 1px dashed #f0c0c0;
  border-radius: 6px;
  font-size: 12px;
  text-align: center;
  padding: 6px;
  box-sizing: border-box;
}
.si-icon {
  font-size: 20px;
}
.si-url {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 10px;
  color: #bbb;
}
</style>
