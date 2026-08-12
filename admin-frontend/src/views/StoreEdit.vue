<template>
  <div>
    <div style="display:flex;align-items:center;margin-bottom:20px">
      <el-button @click="$router.back()" text>
        <el-icon><ArrowLeft /></el-icon> 返回
      </el-button>
      <h2 style="margin:0">{{ isEdit ? '编辑快闪店' : '新建快闪店' }}</h2>
    </div>

    <el-card>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px" style="max-width:800px">
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" placeholder="快闪店标题" maxlength="200" show-word-limit />
        </el-form-item>

        <el-form-item label="副标题">
          <el-input v-model="form.subtitle" placeholder="简短描述" maxlength="300" />
        </el-form-item>

        <el-form-item label="详细描述">
          <el-input v-model="form.description" type="textarea" :rows="4" placeholder="活动详细介绍..." />
        </el-form-item>

        <!-- 城市与地址：支持多城市，按 + 新增 -->
        <el-form-item label="城市与地址">
          <div style="width:100%">
            <div
              v-for="(c, i) in form.citiesList"
              :key="i"
              style="display:flex;gap:10px;margin-bottom:10px;align-items:center"
            >
              <el-input v-model="c.city" placeholder="城市，如：上海" style="width:140px" />
              <el-input v-model="c.district" placeholder="区域，如：黄浦区" style="width:120px" />
              <el-input v-model="c.address" placeholder="详细地址" style="flex:1" />
              <el-button
                v-if="form.citiesList.length > 1"
                @click="removeCity(i)"
                circle
                text
                type="danger"
              >
                <el-icon><Close /></el-icon>
              </el-button>
            </div>
            <el-button @click="addCity" plain>
              <el-icon><Plus /></el-icon> 新增快闪城市
            </el-button>
          </div>
        </el-form-item>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="开始日期">
              <el-date-picker v-model="form.start_date" type="date" placeholder="选择日期" style="width:100%" value-format="YYYY-MM-DD" format="YYYY-MM-DD" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="结束日期">
              <el-date-picker v-model="form.end_date" type="date" placeholder="选择日期" style="width:100%" value-format="YYYY-MM-DD" format="YYYY-MM-DD" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="主办方">
          <el-input v-model="form.organizer" placeholder="品牌/主办方名称" />
        </el-form-item>

        <el-form-item label="预约方式">
          <el-radio-group v-model="form.reservation">
            <el-radio value="required">需预约</el-radio>
            <el-radio value="advance">前期需预约</el-radio>
            <el-radio value="no">无需预约</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="标签">
          <el-select v-model="form.tagsList" multiple filterable allow-create placeholder="输入标签回车添加" style="width:100%">
            <el-option v-for="t in presetTags" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>

        <!-- 图片：支持本地上传（按年月日归档、混淆文件名）与 外链 URL 混用 -->
        <el-form-item label="图片">
          <el-upload
            action="/api/v1/admin/upload"
            :http-request="customUpload"
            :before-upload="beforeUpload"
            :show-file-list="false"
            accept="image/jpeg,image/png,image/gif,image/webp"
            :disabled="uploading"
          >
            <el-button type="primary" plain :loading="uploading">
              <el-icon><Upload /></el-icon> 上传图片到服务器
            </el-button>
          </el-upload>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            style="margin:10px 0"
            title="上传的图片按 年/月/日 自动归档，文件名已混淆；外链直接填写图片 URL，两种方式可同时存在。"
          />
          <div style="width:100%">
            <div
              v-for="(img, i) in form.imagesList"
              :key="i"
              style="display:flex;gap:10px;margin-bottom:10px;align-items:center"
            >
              <el-input v-model="form.imagesList[i]" placeholder="粘贴图片 URL，如 https://..." style="flex:1" />
              <el-button
                v-if="form.imagesList.length > 1"
                @click="removeImage(i)"
                circle
                text
                type="danger"
              >
                <el-icon><Close /></el-icon>
              </el-button>
            </div>
            <el-button @click="addImage" plain>
              <el-icon><Plus /></el-icon> 新增图片
            </el-button>
            <div v-if="previewImages.length" style="display:flex;gap:10px;margin-top:12px;flex-wrap:wrap">
              <SafeImage
                v-for="(img, i) in previewImages"
                :key="i"
                :src="img"
                :style="{ width:'120px', height:'80px', objectFit:'cover', borderRadius:'6px', border:'1px solid #eee' }"
              />
            </div>
          </div>
        </el-form-item>

        <el-form-item label="来源">
          <el-select v-model="form.source" style="width:150px">
            <el-option label="手动" value="manual" />
            <el-option label="爬虫" value="crawler" />
          </el-select>
        </el-form-item>

        <el-form-item label="来源链接">
          <el-input v-model="form.source_url" placeholder="原始文章链接（可选）" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="saving" @click="handleSave">
            {{ isEdit ? '保存修改' : '创建快闪店' }}
          </el-button>
          <el-button @click="$router.back()">取消</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ArrowLeft, Plus, Close, Upload } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { getStore, createStore, updateStore, uploadImage } from '../api'
import SafeImage from '../components/SafeImage.vue'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const formRef = ref(null)
const saving = ref(false)
const uploading = ref(false)
const isEdit = computed(() => !!route.params.id)

const presetTags = ['快闪店', '二次元', '动漫', '游戏', '联名', '限定', '主题店', 'ACG', '手办', '周边', 'cosplay']

const form = reactive({
  title: '',
  subtitle: '',
  description: '',
  start_date: null,
  end_date: null,
  organizer: '',
  reservation: 'no',
  tagsList: [],
  imagesList: [''],
  citiesList: [{ city: '', district: '', address: '' }],
  source: 'manual',
  source_url: '',
})

const rules = {
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
}

const previewImages = computed(() =>
  form.imagesList.map((x) => (x || '').trim()).filter(Boolean)
)

onMounted(async () => {
  if (isEdit.value) {
    try {
      const { data } = await getStore(route.params.id)
      // 多图
      let images = []
      try { images = JSON.parse(data.images || '[]') } catch { images = [] }
      if (!images.length && data.cover_image) images = [data.cover_image]
      form.imagesList = images.length ? images : ['']

      // 多城市
      let cities = []
      try { cities = JSON.parse(data.cities || '[]') } catch { cities = [] }
      if (!cities.length && (data.city || data.address)) {
        cities = [{ city: data.city || '', district: data.district || '', address: data.address || '' }]
      }
      form.citiesList = cities.length ? cities : [{ city: '', district: '', address: '' }]

      form.title = data.title || ''
      form.subtitle = data.subtitle || ''
      form.description = data.description || ''
      form.start_date = data.start_date ? data.start_date.split('T')[0] : null
      form.end_date = data.end_date ? data.end_date.split('T')[0] : null
      form.organizer = data.organizer || ''
      form.reservation = data.reservation || 'no'
      form.source = data.source || 'manual'
      form.source_url = data.source_url || ''
      try {
        form.tagsList = JSON.parse(data.tags || '[]')
      } catch { form.tagsList = [] }
    } catch (e) {
      ElMessage.error('加载失败')
      router.back()
    }
  }
})

const addCity = () => form.citiesList.push({ city: '', district: '', address: '' })
const removeCity = (i) => form.citiesList.splice(i, 1)
const addImage = () => form.imagesList.push('')
const removeImage = (i) => form.imagesList.splice(i, 1)

// 上传前客户端校验（与后端文件头校验互补）
const beforeUpload = (file) => {
  const okTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
  if (!okTypes.includes(file.type)) {
    ElMessage.error('只能上传 JPG / PNG / GIF / WEBP 图片')
    return false
  }
  const isLt10M = file.size / 1024 / 1024 < 10
  if (!isLt10M) {
    ElMessage.error('图片大小不能超过 10MB')
    return false
  }
  return true
}

// 复用 api.uploadImage（走 axios 拦截器，自动带 token，相对路径 /api/v1）
const customUpload = async (options) => {
  uploading.value = true
  try {
    const { data } = await uploadImage(options.file)
    form.imagesList.push(data.url)
    ElMessage.success('上传成功，已加入图片列表')
  } catch (e) {
    ElMessage.error('上传失败，请重试')
  } finally {
    uploading.value = false
  }
}

const handleSave = async () => {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    const cities = form.citiesList
      .filter((c) => (c.city && c.city.trim()) || (c.address && c.address.trim()))
      .map((c) => ({
        city: (c.city || '').trim(),
        district: (c.district || '').trim(),
        address: (c.address || '').trim(),
      }))
    const images = form.imagesList.map((x) => (x || '').trim()).filter(Boolean)

    const payload = {
      title: form.title,
      subtitle: form.subtitle,
      description: form.description,
      start_date: form.start_date || null,
      end_date: form.end_date || null,
      organizer: form.organizer,
      reservation: form.reservation,
      source: form.source,
      source_url: form.source_url,
      tags: JSON.stringify(form.tagsList),
      images: JSON.stringify(images),
      cities: JSON.stringify(cities),
    }

    // 主城市/地址与封面用于筛选与列表展示兼容
    const firstCity = cities[0] || {}
    payload.city = firstCity.city || ''
    payload.district = firstCity.district || ''
    payload.address = firstCity.address || ''
    payload.cover_image = images[0] || ''

    if (isEdit.value) {
      await updateStore(route.params.id, payload)
      ElMessage.success('已更新')
    } else {
      await createStore(payload)
      ElMessage.success('已创建')
    }
    router.push('/stores')
  } finally {
    saving.value = false
  }
}
</script>
