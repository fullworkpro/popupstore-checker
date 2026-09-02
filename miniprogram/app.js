// ── 手动环境切换 ──
// 设为 'develop' / 'trial' / 'release' 可强制覆盖自动识别；设为 null 则按小程序运行环境自动判断。
// 切换环境只需改这一行：
const MANUAL_ENV = 'release'

// 小程序端版本标记：miniprogram/ 不在 popstore-docker/ 内，不随 docker 部署，
// 必须另用微信开发者工具上传发布。改了小程序却「没生效」时，先在开发者工具
// 控制台确认这里打印的版本是否为最新。
const MP_VERSION = '2026-09-02-mini-type-filter-loadinggate-v1.4.3'

App({
  onLaunch() {
    console.log('PopStore 小程序启动 | 版本:', MP_VERSION)

    // 根据小程序运行环境自动切换 API 地址
    // envVersion: develop(开发版) / trial(体验版) / release(正式版)
    let env = 'develop'
    try {
      env = wx.getAccountInfoSync().miniProgram.envVersion
    } catch (e) {
      // 拿不到环境信息时默认走开发地址
    }

    // 手动切换优先：若设置了 MANUAL_ENV 则强制使用该环境
    if (MANUAL_ENV) {
      env = MANUAL_ENV
      console.log('已手动指定环境:', env)
    }

    const API = {
      develop: 'http://127.0.0.1:8000/api/v1',        // 本地开发：连本机后台
      trial: 'http://192.168.50.147:9114/api/v1',      // 体验版：连局域网/测试机后台（按需修改 IP）
      release: 'https://popstore.nas.ccxiang.top/api/v1',       // 正式版：HTTPS 域名（上线前改成真实域名）
    }

    this.globalData.apiBase = API[env] || API.develop
    console.log('当前 API:', this.globalData.apiBase, '| env:', env)
  },
  globalData: {
    apiBase: 'http://127.0.0.1:8000/api/v1'
  }
})
