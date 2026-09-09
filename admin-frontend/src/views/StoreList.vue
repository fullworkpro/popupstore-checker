<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
      <h2>快闪店管理</h2>
      <div style="display:flex;gap:8px">
        <el-button @click="openImport">
          <el-icon><Upload /></el-icon> 导入JSON
        </el-button>
        <el-button type="primary" @click="$router.push('/stores/create')">
          <el-icon><Plus /></el-icon> 新建快闪店
        </el-button>
      </div>
    </div>

    <!-- 筛选栏 -->
    <el-card style="margin-bottom:16px">
      <el-form :inline="true" :model="filters">
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable placeholder="全部" style="width:120px" @change="fetchList">
            <el-option label="待审核" value="draft" />
            <el-option label="已发布" value="published" />
            <el-option label="已归档" value="archived" />
            <el-option label="已驳回" value="rejected" />
          </el-select>
        </el-form-item>
        <el-form-item label="城市">
          <el-select v-model="filters.city" clearable placeholder="全部" style="width:120px" @change="fetchList">
            <el-option v-for="c in cities" :key="c" :label="c" :value="c" />
          </el-select>
        </el-form-item>
        <el-form-item label="快闪类型">
          <el-select v-model="filters.store_type" clearable placeholder="全部" style="width:130px" @change="fetchList">
            <el-option v-for="t in storeTypes" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源">
          <el-select v-model="filters.source" clearable placeholder="全部" style="width:120px" @change="fetchList">
            <el-option label="手动" value="manual" />
            <el-option label="爬虫" value="crawler" />
            <el-option label="微信" value="wechat" />
            <el-option label="小红书" value="xiaohongshu" />
            <el-option label="微博" value="weibo" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-input v-model="filters.keyword" placeholder="搜索标题..." clearable @clear="fetchList" @keyup.enter="fetchList" style="width:200px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchList">搜索</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 列表 -->
    <el-card>
      <el-table :data="list" stripe v-loading="loading">
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column prop="city" label="城市" width="80" />
        <el-table-column prop="store_type_label" label="类型" width="100">
          <template #default="{ row }">
            <el-tag size="small" type="warning">{{ typeLabel(row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="80">
          <template #default="{ row }">
            <el-tag size="small">{{ sourceLabel(row.source) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="view_count" label="浏览" width="70" />
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="$router.push(`/stores/${row.id}/edit`)">编辑</el-button>
            <el-button
              v-if="row.status === 'draft'"
              size="small"
              type="success"
              @click="handleReview(row, 'published')"
            >发布</el-button>
            <el-button
              v-if="row.status === 'published'"
              size="small"
              type="warning"
              @click="handleReview(row, 'archived')"
            >归档</el-button>
            <el-button
              v-if="row.status === 'draft'"
              size="small"
              type="danger"
              @click="handleReview(row, 'rejected')"
            >驳回</el-button>
            <el-popconfirm title="确定删除？" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top:16px;text-align:right">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="fetchList"
        />
      </div>
    </el-card>

    <!-- 导入 JSON：WorkBuddy / content-hunter 产出的策展数据 -->
    <el-dialog v-model="importVisible" title="导入 JSON" width="900px" @closed="resetImport">
      <el-alert type="info" :closable="false" show-icon style="margin-bottom:12px"
        description="先点「检查」预览，确认无误后再点「确认导入」。导入成功的条目为「待审核」状态，小程序暂不可见，后台审核后才上线。缺原文链接只提示、不拦截。" />

      <div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap">
        <input ref="fileInput" type="file" accept=".json,application/json" style="display:none"
               @change="onPickFile" />
        <el-button @click="fileInput.click()">选择 JSON 文件</el-button>
        <el-button :loading="checking" :disabled="!importText" @click="checkImport">检查</el-button>
        <el-button type="primary" :loading="importing"
                   :disabled="!importResult || !importResult.importable" @click="doImport">
          确认导入
        </el-button>
        <span v-if="fileName" style="color:#909399;font-size:12px">{{ fileName }}</span>
      </div>

      <el-input v-model="importText" type="textarea" :rows="5"
                placeholder="也可以直接粘贴 JSON 内容（{&quot;items&quot;:[...]} 或 [...]）" />

      <!-- 校验结果 -->
      <template v-if="importResult">
        <div style="margin:14px 0 8px;display:flex;gap:14px;align-items:center;flex-wrap:wrap">
          <span>共 <b>{{ importResult.total }}</b> 条</span>
          <el-tag type="success" size="small">可导入 {{ importResult.importable }}</el-tag>
          <el-tag type="warning" size="small">重复 {{ importResult.duplicated }}</el-tag>
          <el-tag type="danger" size="small">不合格 {{ importResult.invalid }}</el-tag>
          <span v-if="importDone" style="color:#67c23a;font-weight:600">
            已入库 {{ importResult.added }} 条
          </span>
        </div>

        <el-table :data="importResult.items" size="small" max-height="320" border>
          <el-table-column type="index" label="#" width="46" />
          <el-table-column prop="title" label="标题" min-width="190" show-overflow-tooltip />
          <el-table-column label="结果" width="86">
            <template #default="{ row }">
              <el-tag :type="levelType(row.level)" size="small">{{ levelLabel(row.level) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="210">
            <template #default="{ row }">
              <span v-if="!row.issues || !row.issues.length">—</span>
              <span v-else style="color:#e6a23c">{{ row.issues.join('；') }}</span>
            </template>
          </el-table-column>
          <el-table-column label="原文链接" width="86" align="center">
            <template #default="{ row }">
              <a v-if="row.source_url" :href="row.source_url" target="_blank"
                 style="color:#409eff">打开</a>
              <span v-else style="color:#c0c4cc">—</span>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <template #footer>
        <el-button @click="importVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { getStores, deleteStore, reviewStore, getCities, importJsonStores } from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const loading = ref(false)
const list = ref([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const cities = ref([])
// 快闪类型：与后端 models/store.py 的 STORE_TYPES 保持一致
const storeTypes = [
  { value: 'popup', label: '联名快闪' },
  { value: 'exhibition', label: '特展' },
  { value: 'restaurant', label: '联名餐厅' },
]
const typeMap = storeTypes.reduce((m, t) => { m[t.value] = t.label; return m }, {})

const filters = reactive({ status: '', city: '', source: '', store_type: '', keyword: '' })

// ── 导入 JSON ──
const importVisible = ref(false)
const importText = ref('')
const fileName = ref('')
const fileInput = ref(null)
const checking = ref(false)
const importing = ref(false)
const importResult = ref(null)   // 检查结果 / 导入结果
const importDone = ref(false)    // 是否已真正导入过

const openImport = () => {
  importVisible.value = true
}
const resetImport = () => {
  importText.value = ''
  fileName.value = ''
  importResult.value = null
  importDone.value = false
}

const onPickFile = (e) => {
  const f = e.target.files && e.target.files[0]
  if (!f) return
  fileName.value = f.name
  const reader = new FileReader()
  reader.onload = () => { importText.value = String(reader.result || '') }
  reader.readAsText(f, 'utf-8')
  e.target.value = ''   // 允许重复选择同一个文件
}

// 解析输入框内容 → items 数组；失败返回 null
const parsePayload = () => {
  if (!importText.value.trim()) {
    ElMessage.warning('请先选择文件或粘贴 JSON')
    return null
  }
  try {
    const data = JSON.parse(importText.value)
    const items = Array.isArray(data) ? data : (data.items || [])
    if (!Array.isArray(items) || !items.length) {
      ElMessage.warning('没有解析到条目（items 为空）')
      return null
    }
    return items
  } catch (err) {
    ElMessage.error('JSON 解析失败：' + err.message)
    return null
  }
}

const checkImport = async () => {
  const items = parsePayload()
  if (!items) return
  checking.value = true
  try {
    const { data } = await importJsonStores({ items }, true)
    importResult.value = data
    importDone.value = false
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '检查失败')
  } finally {
    checking.value = false
  }
}

const doImport = async () => {
  const items = parsePayload()
  if (!items) return
  importing.value = true
  try {
    const { data } = await importJsonStores({ items }, false)
    importResult.value = data
    importDone.value = true
    fetchList()
    const skipped = (data.duplicated || 0) + (data.invalid || 0) + (data.failed || 0)
    await ElMessageBox.alert(
      `入库成功 ${data.added} 条，入库失败/跳过 ${skipped} 条。\n\n` +
      `· 成功 ${data.added} 条（已置为「待审核」，发布后小程序可见）\n` +
      `· 重复 ${data.duplicated} 条（原文链接或标题已存在）\n` +
      `· 不合格 ${data.invalid} 条（缺少标题）\n` +
      `· 处理异常 ${data.failed} 条`,
      '导入完成',
      { confirmButtonText: '知道了', type: data.added ? 'success' : 'warning' }
    )
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '导入失败')
  } finally {
    importing.value = false
  }
}

const levelLabel = (lv) => ({ ok: '可导入', warn: '待补全', dup: '重复', error: '不合格' }[lv] || lv)
const levelType = (lv) => ({ ok: 'success', warn: 'warning', dup: 'info', error: 'danger' }[lv] || 'info')

onMounted(async () => {
  await fetchList()
  try {
    const { data } = await getCities()
    cities.value = data
  } catch (e) { /* */ }
})

const fetchList = async () => {
  loading.value = true
  try {
    const { data } = await getStores({
      page: page.value,
      page_size: pageSize.value,
      ...filters,
    })
    list.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

const handleReview = async (row, status) => {
  try {
    await reviewStore(row.id, { status, comment: '' })
    ElMessage.success(status === 'published' ? '已发布' : status === 'archived' ? '已归档' : '已驳回')
    fetchList()
  } catch (e) { /* */ }
}

const handleDelete = async (id) => {
  try {
    await deleteStore(id)
    ElMessage.success('已删除')
    fetchList()
  } catch (e) { /* */ }
}

// 类型中文名：优先用后端返回的 store_type_label；缺失时按 store_type 本地兜底，
// 避免后端字段缺失时整列都被兜底成「联名快闪」而看不出特展/联名餐厅
const typeLabel = (row) => row.store_type_label || typeMap[row.store_type] || '联名快闪'
const sourceLabel = (s) => ({
  manual: '手动', crawler: '爬虫', wechat: '微信', xiaohongshu: '小红书', weibo: '微博',
}[s] || s)
const statusType = (s) => ({
  published: 'success', draft: 'warning', archived: 'info', rejected: 'danger',
}[s] || 'info')
const statusLabel = (s) => ({
  published: '已发布', draft: '待审核', archived: '已归档', rejected: '已驳回',
}[s] || s)
const formatDate = (d) => d ? new Date(d).toLocaleString('zh-CN') : '-'
</script>
