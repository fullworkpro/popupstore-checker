<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h2>公众号推送</h2>
      <div style="display:flex;gap:8px;align-items:center">
        <el-tag type="info">已推送 {{ pushedCount }} 篇</el-tag>
        <el-tag :type="credOk ? 'success' : 'danger'">
          {{ credOk ? '凭据已配置' : '未配置凭据' }}
        </el-tag>
      </div>
    </div>

    <el-alert
      v-if="!credOk"
      type="warning" show-icon :closable="false" style="margin-bottom:16px"
      title="未检测到公众号凭据"
      description="在 backend/data/.wechat_mp 写入 WECHAT_APPID=... 与 WECHAT_APPSECRET=...，并把服务器出口 IP 加进开发者平台白名单，然后刷新本页。"
    />
    <el-alert
      v-else-if="!scriptExists"
      type="error" show-icon :closable="false" style="margin-bottom:16px"
      title="推送脚本缺失"
      description="容器内找不到 scripts/push_wechat_draft.py，请确认镜像已 COPY scripts 目录后重新构建 backend。"
    />

    <!-- 推送操作区 -->
    <el-card style="margin-bottom:16px">
      <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
        <span style="font-size:14px">已选 <b>{{ selected.length }}</b> 篇（多图文一次群发，上限 8）</span>
        <el-button type="primary" :disabled="!selected.length || running" :loading="starting" @click="doPush">
          推送到草稿箱
        </el-button>
        <el-button :disabled="!selected.length || running" @click="doPushDry">只看产物（dry-run）</el-button>

        <el-divider direction="vertical" />
        <span style="font-size:13px;color:#606266">周报</span>
        <el-select v-model="weeklyDays" style="width:110px">
          <el-option label="近 7 天" :value="7" />
          <el-option label="近 14 天" :value="14" />
          <el-option label="近 30 天" :value="30" />
        </el-select>
        <el-button :disabled="running" @click="doWeekly">生成周报草稿</el-button>

        <el-divider direction="vertical" />
        <el-switch v-model="light" active-text="轻量图（不占素材配额）" />
        <el-input
          v-model="urlLink" clearable style="width:300px"
          placeholder="阅读原文链接（可选，可填小程序 URL Link）"
        />
      </div>
      <div style="margin-top:8px;font-size:12px;color:#909399;line-height:1.7">
        图片默认转存为微信永久素材，文件名形如 <code>260921_标题_1.jpg</code>，素材库可按日期前缀检索；
        勾选「轻量图」则不进素材库（省配额，但不可管理）。草稿只进草稿箱，群发永远由你在公众号后台点。
      </div>
    </el-card>

    <!-- 任务状态 -->
    <el-card v-if="task.status && task.status !== 'idle'" style="margin-bottom:16px">
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px">
        <el-tag :type="taskTagType" effect="dark">{{ taskLabel }}</el-tag>
        <span style="font-size:13px;color:#606266">{{ task.message || '' }}</span>
        <span style="font-size:12px;color:#909399">
          {{ task.started_at || '' }}<span v-if="task.finished_at"> → {{ task.finished_at }}</span>
        </span>
        <el-button size="small" :loading="running" @click="loadStatus">刷新</el-button>
      </div>
      <pre v-if="task.log" class="log-box">{{ task.log }}</pre>
    </el-card>

    <!-- 已发布店铺 -->
    <el-card>
      <div style="display:flex;gap:12px;align-items:center;margin-bottom:12px;flex-wrap:wrap">
        <el-input v-model="keyword" placeholder="搜索标题..." clearable style="width:220px" />
        <el-checkbox v-model="onlyUnpushed">只看未推送</el-checkbox>
        <el-button @click="load">刷新列表</el-button>
        <span style="font-size:12px;color:#909399">共 {{ filtered.length }} 条（状态=已发布）</span>
      </div>

      <el-table ref="tableRef" :data="filtered" stripe v-loading="loading"
                row-key="id" @selection-change="onSel">
        <el-table-column type="selection" width="46" reserve-selection :selectable="canSelect" />
        <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
        <el-table-column prop="city" label="城市" width="90" />
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag size="small" type="warning">{{ row.store_type_label || '联名快闪' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="推送状态" width="110">
          <template #default="{ row }">
            <el-tag v-if="pushed[row.id]" size="small" type="success">已推送</el-tag>
            <el-tag v-else size="small" type="info">未推送</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="推送时间" width="160">
          <template #default="{ row }">{{ pushed[row.id]?.at || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openPreview(row)">预览</el-button>
            <el-button
              size="small" type="primary" :disabled="running"
              @click="pushOne(row)"
            >推送</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <StorePreview v-model:visible="previewVisible" :store="previewStore" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getStores, getWechatStatus, getWechatTask, pushWechatDraft } from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'
import StorePreview from '../components/StorePreview.vue'

const loading = ref(false)
const starting = ref(false)
const list = ref([])
const status = ref({ credential: {}, pushed: {}, task: {}, script_exists: true })
const selected = ref([])
const tableRef = ref(null)

const keyword = ref('')
const onlyUnpushed = ref(false)
const light = ref(false)
const urlLink = ref('')
const weeklyDays = ref(7)

const previewVisible = ref(false)
const previewStore = ref({})

const task = computed(() => status.value.task || {})
const running = computed(() => task.value.status === 'running')
const pushed = computed(() => status.value.pushed || {})
const pushedCount = computed(() => Object.keys(pushed.value).length)
const credOk = computed(() => !!status.value.credential?.configured)
const scriptExists = computed(() => status.value.script_exists !== false)

const taskLabel = computed(() => ({
  running: '进行中', success: '已完成', error: '失败', stale: '已失效', idle: '空闲',
}[task.value.status] || task.value.status || ''))
const taskTagType = computed(() => ({
  running: 'warning', success: 'success', error: 'danger', stale: 'info', idle: 'info',
}[task.value.status] || 'info'))

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return list.value.filter((s) => {
    if (onlyUnpushed.value && pushed.value[s.id]) return false
    if (kw && !(s.title || '').toLowerCase().includes(kw)) return false
    return true
  })
})

// 一次群发最多 8 篇
const canSelect = (row) => selected.value.length < 8 || selected.value.some((s) => s.id === row.id)
const onSel = (rows) => { selected.value = rows || [] }

const openPreview = (row) => {
  previewStore.value = row
  previewVisible.value = true
}

// ── 数据 ──
const loadStatus = async () => {
  try {
    const { data } = await getWechatStatus()
    status.value = data
  } catch (e) { /* 拦截器已提示 */ }
}

const load = async () => {
  loading.value = true
  try {
    const { data } = await getStores({ status: 'published', page: 1, page_size: 100 })
    list.value = data.items || []
  } finally {
    loading.value = false
  }
}

// ── 任务轮询 ──
let timer = null
const stopPolling = () => {
  if (timer) { clearInterval(timer); timer = null }
}
const startPolling = () => {
  stopPolling()
  timer = setInterval(async () => {
    try {
      const { data } = await getWechatTask()
      status.value.task = data
      if (data.status !== 'running') {
        stopPolling()
        await loadStatus()
        await load()
        ElMessageBox.alert(
          data.status === 'success'
            ? '草稿已创建，去公众号后台「草稿箱」核对后群发。'
            : `推送未成功（退出码 ${data.returncode}），请看上方日志。`,
          data.status === 'success' ? '推送完成' : '推送失败',
          { confirmButtonText: '知道了', type: data.status === 'success' ? 'success' : 'error' }
        )
      }
    } catch (e) { /* 忽略单次轮询失败 */ }
  }, 3000)
}

const submit = async (payload) => {
  starting.value = true
  try {
    const { data } = await pushWechatDraft(payload)
    status.value.task = data.task || { status: 'running' }
    ElMessage.success('已提交，正在转存图片并创建草稿…')
    startPolling()
  } catch (e) {
    /* 拦截器已提示（409=上一次还在跑，400=未配置凭据/未勾选） */
  } finally {
    starting.value = false
  }
}

const doPush = () => {
  if (!selected.value.length) return ElMessage.warning('请先勾选要推送的快闪店')
  submit({ ids: selected.value.map((s) => s.id), mode: 'single', light: light.value, url_link: urlLink.value })
}
const doPushDry = () => {
  if (!selected.value.length) return ElMessage.warning('请先勾选要推送的快闪店')
  submit({ ids: selected.value.map((s) => s.id), mode: 'single', light: light.value, url_link: urlLink.value, dry_run: true })
}
const doWeekly = () => {
  submit({ ids: [], mode: 'weekly', days: weeklyDays.value, light: light.value, url_link: urlLink.value })
}
const pushOne = (row) => {
  submit({ ids: [row.id], mode: 'single', light: light.value, url_link: urlLink.value })
}

onMounted(async () => {
  await loadStatus()
  await load()
  if (running.value) startPolling()
})
onUnmounted(stopPolling)
</script>

<style scoped>
.log-box {
  margin: 0;
  max-height: 260px;
  overflow: auto;
  background: #1e1e1e;
  color: #d4d4d4;
  font-size: 12px;
  line-height: 1.6;
  padding: 10px 12px;
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-all;
}
code {
  background: #f5f7fa;
  padding: 1px 4px;
  border-radius: 3px;
}
</style>
