<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
      <h2>爬虫日志</h2>
      <el-button type="primary" :loading="triggering" @click="handleTrigger">
        <el-icon><VideoPlay /></el-icon> 手动触发爬虫
      </el-button>
    </div>

    <el-card>
      <el-table :data="list" stripe v-loading="loading">
        <el-table-column prop="source" label="数据源" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ sourceLabel(row.source) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="keyword" label="关键词" width="200" show-overflow-tooltip />
        <el-table-column prop="total_found" label="发现" width="70" />
        <el-table-column prop="new_added" label="新增" width="70" />
        <el-table-column prop="error_count" label="错误" width="70" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : row.status === 'partial' ? 'warning' : 'danger'" size="small">
              {{ row.status === 'success' ? '成功' : row.status === 'partial' ? '部分成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="error_detail" label="错误详情" min-width="200" show-overflow-tooltip />
        <el-table-column label="时间" width="160">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
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
import { ref, onMounted } from 'vue'
import { getCrawlLogs, triggerCrawl } from '../api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const triggering = ref(false)
const list = ref([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

onMounted(() => fetchList())

const fetchList = async () => {
  loading.value = true
  try {
    const { data } = await getCrawlLogs({ page: page.value, page_size: pageSize.value })
    list.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

const handleTrigger = async () => {
  triggering.value = true
  try {
    const { data } = await triggerCrawl()
    ElMessage.success(data.message)
    fetchList()
  } finally {
    triggering.value = false
  }
}

const sourceLabel = (s) => ({
  wechat: '微信', xiaohongshu: '小红书', weibo: '微博', crawler: '爬虫',
}[s] || s)
const formatDate = (d) => d ? new Date(d).toLocaleString('zh-CN') : '-'
</script>
