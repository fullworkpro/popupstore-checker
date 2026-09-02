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

        <el-form-item label="快闪类型">
          <el-radio-group v-model="form.store_type">
            <el-radio v-for="t in storeTypes" :key="t.value" :value="t.value">
              {{ t.label }}
            </el-radio>
          </el-radio-group>
          <div style="font-size:12px;color:#909399;line-height:1.6;margin-top:4px">
            用于小程序首页「快闪类型」下拉筛选；默认「联名快闪」。
          </div>
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

        <!-- 图片：支持拖拽到区域上传（直传七牛图床）与 外链 URL 混用；列表可拖拽排序 -->
        <el-form-item label="图片">
          <div
            class="upload-dropzone"
            :class="{ 'is-dragover': isDragOver }"
            @dragover.prevent="onDragOver"
            @dragenter.prevent="onDragOver"
            @dragleave.prevent="onDragLeave"
            @drop.prevent="onDrop"
            @click="triggerFileInput"
          >
            <el-icon class="dz-icon"><UploadFilled /></el-icon>
            <div class="dz-title">将图片拖拽到此处上传</div>
            <div class="dz-sub">可从浏览器其他标签页直接拖入图片，或点击选择文件</div>
            <div class="dz-hint">支持 JPG / PNG / GIF / WEBP，单张 ≤ 10MB，自动直传七牛图床</div>
            <input
              ref="fileInput"
              type="file"
              accept="image/jpeg,image/png,image/gif,image/webp"
              multiple
              style="display:none"
              @change="onFileInputChange"
            />
          </div>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            style="margin:10px 0"
            title="上传的图片直传七牛图床（公网 CDN 访问）；也可直接填写外链图片 URL。拖拽左侧 ⠿ 调整顺序，第一张为封面。两种方式可同时存在。"
          />
          <div style="width:100%">
            <draggable
              v-model="form.imagesList"
              item-key="id"
              :animation="180"
              handle=".drag-handle"
              ghost-class="img-ghost"
            >
              <template #item="{ element, index }">
                <div style="display:flex;gap:10px;margin-bottom:10px;align-items:center">
                  <span class="drag-handle" title="拖拽调整顺序">⠿</span>
                  <el-input v-model="element.url" placeholder="粘贴图片 URL，如 https://..." style="flex:1" />
                  <el-button
                    v-if="form.imagesList.length > 1"
                    @click="removeImage(index)"
                    circle
                    text
                    type="danger"
                  >
                    <el-icon><Close /></el-icon>
                  </el-button>
                </div>
              </template>
            </draggable>
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
import { ArrowLeft, Plus, Close, UploadFilled } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { getStore, createStore, updateStore, uploadImage } from '../api'
import SafeImage from '../components/SafeImage.vue'
import draggable from 'vuedraggable'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const formRef = ref(null)
const saving = ref(false)
const uploading = ref(false)
const fileInput = ref(null)
const isDragOver = ref(false)
const isEdit = computed(() => !!route.params.id)

// 生成图片项稳定 id（拖拽排序需要唯一 key）
function uid() {
  return 'img_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

const presetTags = ['快闪店', '二次元', '动漫', '游戏', '联名', '限定', '主题店', 'ACG', '手办', '周边', 'cosplay']

// 快闪类型：与后端 models/store.py 的 STORE_TYPES 保持一致
const storeTypes = [
  { value: 'popup', label: '联名快闪' },
  { value: 'exhibition', label: '特展' },
  { value: 'restaurant', label: '联名餐厅' },
]
const DEFAULT_STORE_TYPE = 'popup'

const form = reactive({
  title: '',
  subtitle: '',
  description: '',
  start_date: null,
  end_date: null,
  organizer: '',
  store_type: DEFAULT_STORE_TYPE,
  reservation: 'no',
  tagsList: [],
  imagesList: [{ id: uid(), url: '' }],
  citiesList: [{ city: '', district: '', address: '' }],
  source: 'manual',
  source_url: '',
})

const rules = {
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
}

const previewImages = computed(() =>
  form.imagesList.map((o) => (o.url || '').trim()).filter(Boolean)
)

onMounted(async () => {
  if (isEdit.value) {
    try {
      const { data } = await getStore(route.params.id)
      // 多图
      let images = []
      try { images = JSON.parse(data.images || '[]') } catch { images = [] }
      if (!images.length && data.cover_image) images = [data.cover_image]
      form.imagesList = images.length ? images.map((url) => ({ id: uid(), url })) : [{ id: uid(), url: '' }]

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
      // 老数据可能没有 store_type，回退默认类型（后端也会兜底，这里保证表单不空白）
      form.store_type = data.store_type || DEFAULT_STORE_TYPE
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
const addImage = () => form.imagesList.push({ id: uid(), url: '' })
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

// 点击区域触发隐藏文件选择
const triggerFileInput = () => {
  if (uploading.value) return
  fileInput.value?.click()
}

// 拖拽悬停高亮
const onDragOver = () => {
  isDragOver.value = true
}
const onDragLeave = (e) => {
  // 进入子元素时不取消高亮
  if (e.currentTarget.contains(e.relatedTarget)) return
  isDragOver.value = false
}

// 从文件选择框选图
const onFileInputChange = (e) => {
  const files = Array.from(e.target.files || [])
  e.target.value = '' // 允许重复选择同一文件
  if (files.length) uploadFiles(files)
}

// 拖拽释放：处理从文件管理器或其他标签页拖入的图片
const onDrop = async (e) => {
  isDragOver.value = false
  if (uploading.value) return
  const dt = e.dataTransfer
  // 1) 优先取文件（Chrome/Firefox 从其他标签页拖图片通常会带 file）
  const files = Array.from(dt.files || []).filter((f) => f.type.startsWith('image/'))
  if (files.length) {
    await uploadFiles(files)
    return
  }
  // 2) 回退：只有链接（某些网页拖图片元素只给 URL）
  const uri = dt.getData('text/uri-list') || dt.getData('text/plain')
  if (uri && /^https?:\/\//i.test(uri)) {
    form.imagesList.push({ id: uid(), url: uri.trim() })
    ElMessage.success('已作为外链图片加入列表')
  }
}

// 批量上传（七牛直传，自动带 token）
const uploadFiles = async (files) => {
  const ok = []
  for (const file of files) {
    if (!beforeUpload(file)) continue
    uploading.value = true
    try {
      const { data } = await uploadImage(file)
      form.imagesList.push({ id: uid(), url: data.url })
      ok.push(file.name || '图片')
    } catch (e) {
      ElMessage.error('上传失败：' + (file.name || ''))
    } finally {
      uploading.value = false
    }
  }
  if (ok.length) ElMessage.success(`已上传 ${ok.length} 张图片`)
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
    const images = form.imagesList.map((o) => (o.url || '').trim()).filter(Boolean)

    const payload = {
      title: form.title,
      subtitle: form.subtitle,
      description: form.description,
      start_date: form.start_date || null,
      end_date: form.end_date || null,
      organizer: form.organizer,
      store_type: form.store_type || DEFAULT_STORE_TYPE,
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

<style scoped>
.upload-dropzone {
  width: 100%;
  min-height: 170px;
  border: 2px dashed #dcdfe6;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  background: #fafafa;
  transition: all 0.2s ease;
  text-align: center;
  padding: 24px;
  box-sizing: border-box;
}
.upload-dropzone:hover {
  border-color: #409eff;
  background: #f5f9ff;
}
.upload-dropzone.is-dragover {
  border-color: #409eff;
  background: #ecf5ff;
  transform: scale(1.01);
}
.dz-icon {
  font-size: 46px;
  color: #c0c4cc;
  transition: color 0.2s ease;
}
.upload-dropzone.is-dragover .dz-icon,
.upload-dropzone:hover .dz-icon {
  color: #409eff;
}
.dz-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
.dz-sub {
  font-size: 13px;
  color: #909399;
}
.dz-hint {
  font-size: 12px;
  color: #c0c4cc;
}
.drag-handle {
  cursor: grab;
  color: #c0c4cc;
  font-size: 18px;
  user-select: none;
  line-height: 1;
}
.drag-handle:active {
  cursor: grabbing;
}
.img-ghost {
  opacity: 0.4;
  background: #ecf5ff;
  border-radius: 6px;
}
</style>
