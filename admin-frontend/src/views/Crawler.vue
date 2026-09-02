<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
      <h2>爬虫</h2>
      <div>
        <el-button :loading="triggering" type="primary" @click="handleTrigger">
          <el-icon><VideoPlay /></el-icon> 手动触发（微博）
        </el-button>
        <el-button :loading="loading" @click="loadAll">刷新</el-button>
      </div>
    </div>

    <!-- 运行状态 -->
    <el-card class="block">
      <template #header><span>运行状态</span></template>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="定时爬虫">
          <el-tag :type="config.enabled ? 'success' : 'info'" size="small">
            {{ config.enabled ? '已开启' : '已关闭' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="微博抓取模式">
          <el-tag v-if="form.weibo_uid_enabled && form.weibo_keyword_enabled" type="success" size="small">
            UID优先 + 关键词补充
          </el-tag>
          <el-tag v-else-if="form.weibo_uid_enabled" size="small">仅 UID 账号监控</el-tag>
          <el-tag v-else-if="form.weibo_keyword_enabled" type="warning" size="small">仅关键词搜索</el-tag>
          <el-tag v-else type="danger" size="small">均已停用</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="待发布（微博）">
          <el-tag type="warning">{{ config.pending_weibo_draft }}</el-tag> 条
        </el-descriptions-item>
        <el-descriptions-item label="上次成功运行">
          {{ fmt(config.last_success_at) || '尚未成功' }}
        </el-descriptions-item>
        <el-descriptions-item label="上次运行">
          {{ fmt(config.last_run_at) || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="上次错误" :span="2">
          <span v-if="config.last_error" style="color:#f56c6c">{{ config.last_error }}</span>
          <span v-else>无</span>
        </el-descriptions-item>
        <el-descriptions-item label="最近一次日志" :span="2">
          <template v-if="config.last_log">
            {{ sourceLabel(config.last_log.source) }} ·
            发现 {{ config.last_log.total_found }} / 新增 {{ config.last_log.new_added }} /
            错误 {{ config.last_log.error_count }} ·
            <el-tag :type="config.last_log.status==='success'?'success':config.last_log.status==='partial'?'warning':'danger'" size="small">
              {{ config.last_log.status==='success'?'成功':config.last_log.status==='partial'?'部分成功':'失败' }}
            </el-tag>
          </template>
          <span v-else>暂无</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- ① UID 账号监控（优先级最高，独立开关 + 折叠置灰） -->
    <el-card class="block">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span>① UID 账号监控（首选，优先级最高）</span>
          <el-switch
            v-model="form.weibo_uid_enabled"
            active-text="启用"
            inactive-text="停用"
            @change="onUidToggle"
          />
        </div>
      </template>
      <el-collapse-transition>
        <div v-show="uidExpanded">
          <el-alert :type="form.weibo_uid_enabled ? 'success' : 'info'" :closable="false" style="margin-bottom:16px">
            监控下列官方/品牌微博账号的时间线，自动抓取<strong>【原创】</strong>且含「快闪/快闪店」的帖子。
            游客即可读取时间线，比全站关键词搜索（ok=-100 重灾区）稳定得多，且精准锁定目标品牌。
            <strong>与关键词模式可同时启用</strong>：UID 先跑、优先级最高，关键词结果作为补充。
          </el-alert>
          <el-form label-width="120px">
            <el-form-item label="监控账号">
              <div style="width:100%">
                <div v-for="(acc, i) in form.weibo_accounts" :key="i" class="row">
                  <el-input v-model="form.weibo_accounts[i].name" placeholder="账号显示名，如 良笑goodsmile"
                    style="width:240px" :disabled="!form.weibo_uid_enabled" />
                  <el-input v-model="form.weibo_accounts[i].uid" placeholder="数字 UID（主页 /u/ 后的数字）"
                    style="width:240px;margin-left:8px" :disabled="!form.weibo_uid_enabled" />
                  <el-button type="danger" text @click="form.weibo_accounts.splice(i,1)"
                    style="margin-left:8px" :disabled="!form.weibo_uid_enabled">删除</el-button>
                </div>
                <el-button @click="form.weibo_accounts.push({name:'',uid:''})" :disabled="!form.weibo_uid_enabled">
                  + 添加账号
                </el-button>
                <span style="color:#909399;margin-left:10px">UID 留空将被跳过；填好即生效</span>
              </div>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingAccount" @click="saveAccounts"
                :disabled="!form.weibo_uid_enabled">保存账号监控</el-button>
            </el-form-item>
          </el-form>
        </div>
      </el-collapse-transition>
      <div v-if="!uidExpanded" class="collapsed-hint">
        <el-tag type="info" size="small">已停用并折叠（内容保留、不可编辑）</el-tag>
        <el-link type="primary" :underline="false" style="margin-left:12px" @click="uidExpanded = true">
          展开查看
        </el-link>
      </div>
    </el-card>

    <!-- ② 全站关键词搜索（UID 的补充，独立开关 + 折叠置灰） -->
    <el-card class="block">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span>② 全站关键词搜索（补充，优先级次于 UID）</span>
          <el-switch
            v-model="form.weibo_keyword_enabled"
            active-text="启用"
            inactive-text="停用"
            @change="onKeywordToggle"
          />
        </div>
      </template>
      <el-collapse-transition>
        <div v-show="keywordExpanded">
          <el-alert :type="form.weibo_keyword_enabled ? 'success' : 'info'" :closable="false" style="margin-bottom:16px">
            针对每个「二次元 IP 关键词」在全站搜索<strong>原创</strong>微博，仅保留正文含「快闪 / 快闪店」且命中该 IP 的帖子。
            <strong>作为 UID 的补充</strong>：与 UID 同时启用时，先跑完 UID 再跑关键词，用于覆盖 UID 之外的长尾信息。
            停用只会折叠置灰、<strong>不会清空已配置的关键词</strong>。
          </el-alert>
          <el-form label-width="150px">
            <el-form-item label="二次元 IP 关键词">
              <div style="width:100%">
                <div v-for="(kw, i) in form.weibo_keywords" :key="i" class="row">
                  <el-input v-model="form.weibo_keywords[i]" placeholder="如 龙珠 / 原神 / 鸣潮 / chiikawa"
                    style="width:260px" :disabled="!form.weibo_keyword_enabled" />
                  <el-button type="danger" text @click="form.weibo_keywords.splice(i,1)"
                    style="margin-left:8px" :disabled="!form.weibo_keyword_enabled">删除</el-button>
                </div>
                <el-button @click="form.weibo_keywords.push('')" :disabled="!form.weibo_keyword_enabled">
                  + 添加关键词
                </el-button>
                <span style="color:#909399;margin-left:10px">命中其一即视为二次元快闪主题</span>
              </div>
            </el-form-item>
            <el-form-item label="每关键词搜索页数">
              <el-input-number v-model="form.weibo_max_pages" :min="1" :max="20"
                :disabled="!form.weibo_keyword_enabled" />
              <span style="color:#909399;margin-left:10px">每页约 10 条；页数越多覆盖越全但请求越多</span>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingKeyword" @click="saveKeyword"
                :disabled="!form.weibo_keyword_enabled">保存关键词配置</el-button>
            </el-form-item>
          </el-form>
        </div>
      </el-collapse-transition>
      <div v-if="!keywordExpanded" class="collapsed-hint">
        <el-tag type="info" size="small">已停用并折叠（关键词保留、不可编辑）</el-tag>
        <el-link type="primary" :underline="false" style="margin-left:12px" @click="keywordExpanded = true">
          展开查看
        </el-link>
      </div>
    </el-card>

    <!-- ③ 访客凭证 / Cookie（默认 visitor，独立保存） -->
    <el-card class="block">
      <template #header><span>③ 访客凭证 / Cookie（默认使用自动访客）</span></template>
      <el-alert type="success" :closable="false" style="margin-bottom:16px">
        <strong>默认无需任何操作：</strong>爬虫每次运行会自动向微博领取一个<strong>临时访客身份（visitor）</strong>作为凭证，
        无需登录、无需填写 Cookie。只有在遇到 <code>HTTP 432</code>（出口 IP 被微博 WAF 拦截）时才需要手动填写 Cookie。
      </el-alert>
      <el-form label-width="150px">
        <el-form-item label="微博 Cookie">
          <template #label>
            <span>
              微博 Cookie
              <el-tooltip placement="top" effect="dark" width="320">
                <template #content>
                  <div style="max-width:320px;line-height:1.6">
                    <b>如何获取 Cookie（敏感信息，仅存于本机数据库）：</b><br/>
                    1. 电脑浏览器登录 weibo.com；<br/>
                    2. 按 F12 打开「开发者工具」→「网络(Network)」；<br/>
                    3. 刷新页面，在请求列表点任意一个 weibo.com 请求；<br/>
                    4. 在「请求头(Request Headers)」里找到 <code>Cookie:</code> 整行复制；<br/>
                    5. 粘贴到下方输入框并点「保存 Cookie」。<br/>
                    ⚠️ Cookie 含登录凭证，相当于账号临时密码，请勿外泄；
                    仅在服务器 IP 被微博 WAF(HTTP 432) 拦截时才需要填写。
                  </div>
                </template>
                <el-icon style="margin-left:4px;color:#909399;cursor:help"><QuestionFilled /></el-icon>
              </el-tooltip>
            </span>
          </template>
          <el-input v-model="form.weibo_cookie" type="textarea" :rows="3"
            :placeholder="config.has_cookie ? '已保存（留空表示不修改；填新值将覆盖；清空并保存可删除）' : '可选。仅在遇到 HTTP 432（IP 被微博 WAF 拦截）时才需要填写'"
            style="max-width:560px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="savingCookie" @click="saveCookie">保存 Cookie</el-button>
          <span style="color:#909399;margin-left:10px">留空并保存 = 清除已存 Cookie（恢复纯 visitor 模式）</span>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ④ 定时任务（启用 / 排程时刻 / 回看天数，独立保存） -->
    <el-card class="block">
      <template #header><span>④ 定时任务（启用 / 排程 / 回看）</span></template>
      <el-form label-width="150px">
        <el-form-item label="启用定时爬虫">
          <el-switch v-model="form.enabled" active-text="开启" inactive-text="关闭" @change="saveSchedule" />
        </el-form-item>
        <el-form-item label="排程时刻（每天）">
          <div>
            <div v-for="(t, i) in form.schedule" :key="i" class="row">
              <el-time-picker v-model="form.schedule[i]" format="HH:mm" value-format="HH:mm"
                placeholder="选择时刻" style="width:160px" />
              <el-button type="danger" text @click="form.schedule.splice(i,1)" style="margin-left:8px">删除</el-button>
            </div>
            <el-button @click="form.schedule.push('02:00')">+ 添加时刻</el-button>
            <span style="color:#909399;margin-left:10px">时区 Asia/Shanghai</span>
          </div>
        </el-form-item>
        <el-form-item label="首次回看天数">
          <el-input-number v-model="form.lookback_days" :min="0" :max="365" />
          <span style="color:#909399;margin-left:10px">无历史成功记录时向前回看的天数</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="savingSchedule" @click="saveSchedule">保存定时任务</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 其它平台（规划中） -->
    <el-card class="block">
      <template #header><span>其它平台（规划中）</span></template>
      <el-alert type="warning" :closable="false" style="margin-bottom:16px">
        微博爬虫验证通过后，将依次实现<strong>小红书</strong>与<strong>抖音</strong>的监控。
        下方开关与 Cookie 现已可填写保存，但当前调度会跳过未实现源；届时直接开启即可。
      </el-alert>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form label-width="90px">
            <el-form-item label="小红书">
              <el-switch v-model="form.xhs_enabled" />
              <span style="color:#909399;margin-left:8px">尚未实现，开启后本次仍跳过</span>
            </el-form-item>
            <el-form-item label="Cookie">
              <el-input v-model="form.xhs_cookie" type="textarea" :rows="2" :disabled="true"
                placeholder="待开放后填写" style="max-width:320px" />
            </el-form-item>
          </el-form>
        </el-col>
        <el-col :span="12">
          <el-form label-width="90px">
            <el-form-item label="抖音">
              <el-switch v-model="form.douyin_enabled" />
              <span style="color:#909399;margin-left:8px">尚未实现，开启后本次仍跳过</span>
            </el-form-item>
            <el-form-item label="Cookie">
              <el-input v-model="form.douyin_cookie" type="textarea" :rows="2" :disabled="true"
                placeholder="待开放后填写" style="max-width:320px" />
            </el-form-item>
          </el-form>
        </el-col>
      </el-row>
    </el-card>

    <!-- 日志 -->
    <el-card class="block">
      <template #header><span>爬取日志</span></template>
      <el-table :data="logs" stripe v-loading="logsLoading">
        <el-table-column prop="source" label="数据源" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ sourceLabel(row.source) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="keyword" label="关键词" width="220" show-overflow-tooltip />
        <el-table-column prop="total_found" label="发现" width="70" />
        <el-table-column prop="new_added" label="新增" width="70" />
        <el-table-column prop="error_count" label="错误" width="70" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status==='success'?'success':row.status==='partial'?'warning':'danger'" size="small">
              {{ row.status==='success'?'成功':row.status==='partial'?'部分成功':'失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="error_detail" label="错误详情" min-width="200" show-overflow-tooltip />
        <el-table-column label="时间" width="160">
          <template #default="{ row }">{{ fmt(row.created_at) }}</template>
        </el-table-column>
      </el-table>
      <div style="margin-top:16px;text-align:right">
        <el-pagination v-model:current-page="logPage" :page-size="logPageSize" :total="logTotal"
          layout="total, prev, pager, next" @current-change="fetchLogs" />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { getCrawlerConfig, updateCrawlerConfig, runWeiboCrawler, getCrawlLogs } from '../api'
import { ElMessage } from 'element-plus'

const config = ref({})
const form = reactive({
  enabled: true,
  weibo_keywords: [],
  weibo_accounts: [],
  weibo_uid_enabled: true,       // UID 账号监控开关（默认开，优先级最高）
  weibo_keyword_enabled: false,  // 全站关键词搜索开关（默认关，作为 UID 的补充）
  weibo_max_pages: 3,
  schedule: [],
  lookback_days: 1,
  weibo_cookie: '',
  xhs_enabled: false,
  xhs_cookie: '',
  douyin_enabled: false,
  douyin_cookie: '',
})

const loading = ref(false)
const savingAccount = ref(false)
const savingKeyword = ref(false)
const savingCookie = ref(false)
const savingSchedule = ref(false)
const triggering = ref(false)
const logsLoading = ref(false)
const logs = ref([])
const logPage = ref(1)
const logPageSize = ref(20)
const logTotal = ref(0)
// 折叠态：开关关闭 → 折叠；开启 → 展开
const uidExpanded = ref(true)
const keywordExpanded = ref(false)

const fmt = (d) => d ? new Date(d).toLocaleString('zh-CN') : ''
const sourceLabel = (s) => ({ wechat:'微信', xiaohongshu:'小红书', weibo:'微博', douyin:'抖音', crawler:'爬虫' }[s] || s)

const loadConfig = async () => {
  loading.value = true
  try {
    const { data } = await getCrawlerConfig()
    config.value = data
    form.enabled = data.enabled
    form.weibo_keywords = JSON.parse(JSON.stringify(data.weibo_keywords || []))
    form.weibo_accounts = JSON.parse(JSON.stringify(data.weibo_accounts || []))
    form.weibo_uid_enabled = data.weibo_uid_enabled ?? true
    form.weibo_keyword_enabled = data.weibo_keyword_enabled ?? false
    form.weibo_max_pages = data.weibo_max_pages ?? 3
    form.schedule = JSON.parse(JSON.stringify(data.schedule || []))
    form.lookback_days = data.lookback_days
    form.weibo_cookie = data.has_cookie ? '********' : ''  // 不回显明文，仅占位
    form.xhs_enabled = data.xhs_enabled
    form.xhs_cookie = data.has_xhs_cookie ? '********' : ''
    form.douyin_enabled = data.douyin_enabled
    form.douyin_cookie = data.has_douyin_cookie ? '********' : ''
    // 折叠态跟随开关：启用即展开，停用即折叠（内容保留，不清空）
    uidExpanded.value = form.weibo_uid_enabled
    keywordExpanded.value = form.weibo_keyword_enabled
  } finally {
    loading.value = false
  }
}

const fetchLogs = async () => {
  logsLoading.value = true
  try {
    const { data } = await getCrawlLogs({ page: logPage.value, page_size: logPageSize.value })
    logs.value = data.items
    logTotal.value = data.total
  } finally {
    logsLoading.value = false
  }
}

const loadAll = () => { loadConfig(); fetchLogs() }

// 开关：启用即展开、停用即折叠，并立即持久化开关状态（不改动已配置内容）
const onUidToggle = (val) => {
  uidExpanded.value = val
  saveAccounts()
}

const onKeywordToggle = (val) => {
  keywordExpanded.value = val
  if (val && form.weibo_keywords.length === 0) {
    form.weibo_keywords.push('')  // 由停用切到启用且无关键词时，预填一行方便编辑
  }
  saveKeyword()
}

// ① 账号监控：独立保存（含开关）
const saveAccounts = async () => {
  savingAccount.value = true
  try {
    const accounts = form.weibo_accounts
      .filter(a => (a.name || '').trim())
      .map(a => ({ name: a.name.trim(), uid: (a.uid || '').trim() }))
    await updateCrawlerConfig({
      weibo_uid_enabled: form.weibo_uid_enabled,
      weibo_accounts: accounts,
    })
    ElMessage.success('账号监控已保存')
    loadConfig()
  } finally {
    savingAccount.value = false
  }
}

// ② 全站关键词搜索：独立保存（含开关；停用不清空关键词）
const saveKeyword = async () => {
  savingKeyword.value = true
  try {
    const keywords = form.weibo_keywords.map(s => s.trim()).filter(Boolean)
    if (form.weibo_keyword_enabled && keywords.length === 0) {
      ElMessage.error('启用关键词搜索时，请至少添加一个二次元 IP 关键词')
      return
    }
    await updateCrawlerConfig({
      weibo_keyword_enabled: form.weibo_keyword_enabled,
      weibo_keywords: keywords,
      weibo_max_pages: form.weibo_max_pages,
    })
    ElMessage.success('关键词配置已保存')
    loadConfig()
  } finally {
    savingKeyword.value = false
  }
}

// ③ Cookie：独立保存（默认 visitor，可填可清）
const saveCookie = async () => {
  savingCookie.value = true
  try {
    if (form.weibo_cookie === '********' && config.value.has_cookie) {
      ElMessage.info('Cookie 未改动，无需保存')
      return
    }
    await updateCrawlerConfig({ weibo_cookie: form.weibo_cookie || '' })
    ElMessage.success(form.weibo_cookie ? 'Cookie 已保存' : 'Cookie 已清除（恢复纯 visitor 模式）')
    loadConfig()
  } finally {
    savingCookie.value = false
  }
}

// ④ 定时任务（启用 / 排程 / 回看）：独立保存
const saveSchedule = async () => {
  savingSchedule.value = true
  try {
    await updateCrawlerConfig({
      enabled: form.enabled,
      schedule: form.schedule,
      lookback_days: form.lookback_days,
    })
    ElMessage.success('定时任务配置已保存')
    loadConfig()
  } finally {
    savingSchedule.value = false
  }
}

const handleTrigger = async () => {
  triggering.value = true
  try {
    const { data } = await runWeiboCrawler()
    ElMessage.success(data.message)
    loadAll()
  } finally {
    triggering.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.block { margin-bottom: 20px; }
.row { display:flex; align-items:center; margin-bottom:8px; }
.collapsed-hint { display:flex; align-items:center; padding:4px 0; }
</style>
