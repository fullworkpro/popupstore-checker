<template>
  <div>
    <h2 style="margin-bottom:20px">仪表盘</h2>
    <el-row :gutter="20">
      <el-col :span="6" v-for="card in cards" :key="card.label">
        <el-card shadow="hover" style="margin-bottom:20px">
          <div style="display:flex;align-items:center;justify-content:space-between">
            <div>
              <div style="color:#909399;font-size:14px">{{ card.label }}</div>
              <div style="font-size:28px;font-weight:bold;margin-top:8px">{{ card.value }}</div>
            </div>
            <el-icon :size="40" :color="card.color"><component :is="card.icon" /></el-icon>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card style="margin-top:20px">
      <template #header>最新快闪店</template>
      <el-table :data="stats.recent_stores || []" stripe>
        <el-table-column prop="title" label="标题" min-width="200" />
        <el-table-column prop="city" label="城市" width="100" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="view_count" label="浏览" width="80" />
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getDashboard } from '../api'

const stats = ref({})
const cards = ref([
  { label: '总快闪店', value: 0, icon: 'Shop', color: '#409EFF' },
  { label: '已发布', value: 0, icon: 'CircleCheck', color: '#67C23A' },
  { label: '待审核', value: 0, icon: 'Clock', color: '#E6A23C' },
  { label: '总浏览', value: 0, icon: 'View', color: '#F56C6C' },
])

onMounted(async () => {
  try {
    const { data } = await getDashboard()
    stats.value = data
    cards.value[0].value = data.total_stores || 0
    cards.value[1].value = data.published_count || 0
    cards.value[2].value = data.draft_count || 0
    cards.value[3].value = data.total_views || 0
  } catch (e) { /* handled by interceptor */ }
})

const statusType = (s) => ({
  published: 'success', draft: 'warning', archived: 'info', rejected: 'danger',
}[s] || 'info')
const statusLabel = (s) => ({
  published: '已发布', draft: '待审核', archived: '已归档', rejected: '已驳回',
}[s] || s)
const formatDate = (d) => d ? new Date(d).toLocaleString('zh-CN') : '-'
</script>
