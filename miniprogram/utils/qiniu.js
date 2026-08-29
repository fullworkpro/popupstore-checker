/**
 * 七牛云 KODO 图床直传工具
 *
 * 流程：后端 /qiniu/uptoken 用 SecretKey 签发有时效的上传凭证（uptoken）并生成 key，
 *      小程序 wx.uploadFile 直传七牛上传域名，上传成功即得到公网 URL。
 *      SecretKey 不落地前端，七牛流量不占业务服务器带宽。
 */
const { getQiniuUptoken } = require('./api')

/**
 * 上传一张本地图片到七牛图床
 * @param {string} filePath wx.chooseMedia / chooseImage 得到的本地临时路径
 * @param {string} ext 扩展名（不含点），如 jpg / png / webp
 * @returns {Promise<string>} 公网可访问的图片 URL
 */
function uploadImage(filePath, ext = 'jpg') {
  return new Promise((resolve, reject) => {
    getQiniuUptoken(ext)
      .then((info) => {
        wx.uploadFile({
          url: info.upload_domain,
          filePath,
          name: 'file',
          formData: {
            token: info.uptoken,
            key: info.key,
          },
          success(res) {
            if (res.statusCode === 200) {
              // 七牛返回 { key, hash }；公网 URL 已由后端拼好（info.public_url）
              resolve(info.public_url)
            } else {
              reject(res)
            }
          },
          fail(err) {
            reject(err)
          },
        })
      })
      .catch((err) => reject(err))
  })
}

module.exports = { uploadImage }
