<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
      <h2>快闪店管理</h2>
      <el-button type="primary" @click="$router.push('/stores/create')">
        <el-icon><Plus /></el-icon> 新建快闪店
      </el-button>
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
            <el-tag size="small" type="warning">{{ row.store_type_label || '联名快闪' }}</el-tag>
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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { getStores, deleteStore, reviewStore, getCities } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const list = ref([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const cities = ref([])
const filters = reactive({ status: '', city: '', source: '', keyword: '' })

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
