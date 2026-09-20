<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="v => emit('update:visible', v)"
    :title="`小程序预览 · ${store?.title || ''}`"
    width="440px"
    top="3vh"
  >
    <div class="phone">
      <div class="phone-screen">
        <!-- 顶部导航条（仿小程序导航栏） -->
        <div class="navbar">详情</div>

        <div class="scroll">
          <!-- 图片轮播（小程序是 swiper，这里用可翻页的图区近似） -->
          <div class="hero">
            <SafeImage
              v-if="imgs.length"
              :src="imgs[idx]"
              style="width:100%;height:100%;object-fit:cover;display:block"
            />
            <div v-else class="hero-ph">🎌</div>

            <template v-if="imgs.length > 1">
              <div class="nav prev" @click="prev">‹</div>
              <div class="nav next" @click="next">›</div>
              <div class="dots">
                <span v-for="(u, i) in imgs" :key="i" :class="{ on: i === idx }" />
              </div>
            </template>
          </div>

          <div class="content">
            <div class="title">{{ store?.title }}</div>
            <div v-if="store?.subtitle" class="subtitle">{{ store.subtitle }}</div>

            <div v-if="tags.length" class="tags">
              <span v-for="t in tags" :key="t" class="tag">{{ t }}</span>
            </div>

            <div class="info-card">
              <template v-if="cities.length">
                <div v-for="(c, i) in cities" :key="i" class="info-row">
                  <span class="info-label">📍 地点{{ cities.length > 1 ? i + 1 : '' }}</span>
                  <span class="info-value">
                    {{ c.city }}<template v-if="c.district">·{{ c.district }}</template>
                    <template v-if="c.address"> · {{ c.address }}</template>
                  </span>
                </div>
              </template>
              <template v-else>
                <div v-if="store?.city" class="info-row">
                  <span class="info-label">📍 地点</span>
                  <span class="info-value">
                    {{ store.city }}<template v-if="store.district">·{{ store.district }}</template>
                  </span>
                </div>
                <div v-if="store?.address" class="info-row">
                  <span class="info-label">🏠 地址</span>
                  <span class="info-value">{{ store.address }}</span>
                </div>
              </template>

              <div v-if="store?.start_date || store?.end_date" class="info-row">
                <span class="info-label">📅 时间</span>
                <span class="info-value">{{ dateText }}</span>
              </div>
              <div v-if="store?.organizer" class="info-row">
                <span class="info-label">🎯 主办方</span>
                <span class="info-value">{{ store.organizer }}</span>
              </div>
              <div class="info-row">
                <span class="info-label">🎟 预约</span>
                <span class="info-value">{{ reservationLabel }}</span>
              </div>
            </div>

            <div v-if="store?.description" class="desc-card">
              <div class="section-title">活动详情</div>
              <div class="desc-text">{{ store.description }}</div>
            </div>

            <div class="stats">👁 {{ store?.view_count || 0 }} 次浏览</div>
          </div>
        </div>

        <!-- 底部操作栏 -->
        <div class="action-bar">
          <div class="fav-btn">☆ 收藏</div>
          <div class="share-btn">分享给好友</div>
        </div>
      </div>
    </div>

    <div class="path-row">
      <span class="path-label">小程序路径</span>
      <code class="path-value">{{ path }}</code>
      <el-button size="small" @click="copyText(path, '路径已复制，可粘到公众号编辑器')">复制</el-button>
    </div>
    <div class="tip">
      与小程序端基本一致；轮播在小程序里是自动播放，这里可点左右箭头翻页。
    </div>

    <template #footer>
      <el-button @click="emit('update:visible', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import SafeImage from './SafeImage.vue'
import { resolveImage } from '../utils/image'
import { copyText, mpPath } from '../utils/clipboard'

const props = defineProps({
  visible: { type: Boolean, default: false },
  store: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['update:visible'])

const idx = ref(0)

const parseList = (v) => {
  try {
    const a = JSON.parse(v || '[]')
    return Array.isArray(a) ? a : []
  } catch {
    return []
  }
}

const imgs = computed(() => {
  const list = parseList(props.store?.images)
    .filter((u) => typeof u === 'string' && u)
    .map(resolveImage)
  if (list.length) return list
  return props.store?.cover_image ? [resolveImage(props.store.cover_image)] : []
})
const tags = computed(() => parseList(props.store?.tags))
const cities = computed(() => parseList(props.store?.cities).filter((c) => c && (c.city || c.address)))
const path = computed(() => mpPath(props.store?.id || ''))

const reservationLabel = computed(
  () => ({ required: '需预约', advance: '前期需预约', no: '无需预约' })[props.store?.reservation] || '无需预约'
)

const parseDt = (s) => {
  if (!s) return null
  const str = String(s)
  const d = new Date(str.length === 10 ? str + 'T00:00:00' : str)
  return isNaN(d.getTime()) ? null : d
}
const dateText = computed(() => {
  const s = parseDt(props.store?.start_date)
  const e = parseDt(props.store?.end_date)
  const f = (d) => `${d.getMonth() + 1}/${d.getDate()}`
  if (s && e) return `${f(s)} ~ ${f(e)}`
  if (s) return `${f(s)} 起`
  if (e) return `${f(e)} 止`
  return '时间待定'
})

const prev = () => { idx.value = (idx.value - 1 + imgs.value.length) % imgs.value.length }
const next = () => { idx.value = (idx.value + 1) % imgs.value.length }

watch(() => props.store?.id, () => { idx.value = 0 })
</script>

<style scoped>
.phone {
  width: 320px;
  margin: 0 auto;
  background: #111;
  border-radius: 28px;
  padding: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, .25);
}
.phone-screen {
  background: #f2f2f2;
  border-radius: 22px;
  overflow: hidden;
  height: 560px;
  display: flex;
  flex-direction: column;
}
.navbar {
  height: 40px;
  line-height: 40px;
  text-align: center;
  background: #fff;
  font-size: 14px;
  color: #333;
  border-bottom: 1px solid #eee;
  flex: none;
}
.scroll {
  flex: 1;
  overflow-y: auto;
}
.hero {
  position: relative;
  height: 200px;
  background: linear-gradient(135deg, #a18cd1, #fbc2eb);
  display: flex;
  align-items: center;
  justify-content: center;
}
.hero-ph { font-size: 48px; }
.nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 26px;
  height: 26px;
  line-height: 24px;
  text-align: center;
  border-radius: 50%;
  background: rgba(0, 0, 0, .35);
  color: #fff;
  font-size: 18px;
  cursor: pointer;
  user-select: none;
}
.nav.prev { left: 8px; }
.nav.next { right: 8px; }
.dots {
  position: absolute;
  bottom: 8px;
  left: 0;
  right: 0;
  text-align: center;
}
.dots span {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin: 0 3px;
  border-radius: 3px;
  background: rgba(255, 255, 255, .5);
}
.dots span.on { background: #6C5CE7; }

.content { padding: 12px; }
.title { font-size: 16px; font-weight: 600; color: #333; line-height: 1.4; }
.subtitle { margin-top: 4px; font-size: 12px; color: #999; }
.tags { margin-top: 8px; }
.tag {
  display: inline-block;
  padding: 2px 8px;
  margin: 0 6px 4px 0;
  background: #f0e8ff;
  color: #6C5CE7;
  font-size: 11px;
  border-radius: 4px;
}
.info-card, .desc-card {
  margin-top: 10px;
  background: #fff;
  border-radius: 8px;
  padding: 10px;
}
.info-row { display: flex; padding: 4px 0; font-size: 12px; }
.info-label { width: 72px; color: #999; flex: none; }
.info-value { color: #333; flex: 1; word-break: break-all; }
.section-title { font-size: 13px; color: #333; font-weight: 600; }
.desc-text { margin-top: 6px; font-size: 12px; color: #555; line-height: 1.7; white-space: pre-wrap; }
.stats { margin: 12px 0 16px; font-size: 11px; color: #aaa; text-align: center; }

.action-bar {
  flex: none;
  display: flex;
  gap: 8px;
  padding: 8px 12px;
  background: #fff;
  border-top: 1px solid #eee;
}
.fav-btn {
  flex: none;
  padding: 6px 12px;
  border: 1px solid #ddd;
  border-radius: 16px;
  font-size: 12px;
  color: #666;
}
.share-btn {
  flex: 1;
  text-align: center;
  padding: 6px 0;
  background: #6C5CE7;
  color: #fff;
  border-radius: 16px;
  font-size: 12px;
}

.path-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px auto 0;
  width: 320px;
}
.path-label { font-size: 12px; color: #909399; flex: none; }
.path-value {
  flex: 1;
  font-size: 11px;
  background: #f5f7fa;
  padding: 4px 6px;
  border-radius: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tip {
  width: 320px;
  margin: 6px auto 0;
  font-size: 11px;
  color: #c0c4cc;
  line-height: 1.6;
}
</style>
