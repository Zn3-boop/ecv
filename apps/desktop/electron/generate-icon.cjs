// 生成托盘图标的脚本 - 纯 Node.js 版本
const path = require('path')
const fs = require('fs')

const ASSETS_DIR = path.join(__dirname, 'assets')
const ICON_PATH = path.join(ASSETS_DIR, 'tray-icon.png')

// 确保目录存在
if (!fs.existsSync(ASSETS_DIR)) {
  fs.mkdirSync(ASSETS_DIR, { recursive: true })
}

// 创建一个 16x16 的简单 PNG 图标（蓝色方块）
// PNG 文件格式：签名 + IHDR + IDAT + IEND
function createPNG(width, height, rgbaCallback) {
  const signature = Buffer.from([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
  
  // IHDR chunk
  const ihdrData = Buffer.alloc(13)
  ihdrData.writeUInt32BE(width, 0)
  ihdrData.writeUInt32BE(height, 4)
  ihdrData[8] = 8  // bit depth
  ihdrData[9] = 6  // color type (RGBA)
  ihdrData[10] = 0 // compression
  ihdrData[11] = 0 // filter
  ihdrData[12] = 0 // interlace
  
  const ihdr = createChunk('IHDR', ihdrData)
  
  // IDAT chunk - raw pixel data with filter bytes
  const rawData = Buffer.alloc((width * 4 + 1) * height)
  for (let y = 0; y < height; y++) {
    rawData[y * (width * 4 + 1)] = 0 // filter type: none
    for (let x = 0; x < width; x++) {
      const offset = y * (width * 4 + 1) + 1 + x * 4
      const rgba = rgbaCallback(x, y)
      rawData[offset] = rgba.r
      rawData[offset + 1] = rgba.g
      rawData[offset + 2] = rgba.b
      rawData[offset + 3] = rgba.a
    }
  }
  
  // Compress with zlib
  const zlib = require('zlib')
  const compressed = zlib.deflateSync(rawData)
  const idat = createChunk('IDAT', compressed)
  
  // IEND chunk
  const iend = createChunk('IEND', Buffer.alloc(0))
  
  return Buffer.concat([signature, ihdr, idat, iend])
}

function createChunk(type, data) {
  const length = Buffer.alloc(4)
  length.writeUInt32BE(data.length, 0)
  
  const typeBuffer = Buffer.from(type, 'ascii')
  const crcData = Buffer.concat([typeBuffer, data])
  
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(crcData), 0)
  
  return Buffer.concat([length, typeBuffer, data, crc])
}

// CRC32 implementation
function crc32(buffer) {
  let crc = 0xFFFFFFFF
  const table = []
  
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) {
      c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1)
    }
    table[n] = c
  }
  
  for (let i = 0; i < buffer.length; i++) {
    crc = table[(crc ^ buffer[i]) & 0xFF] ^ (crc >>> 8)
  }
  
  return (crc ^ 0xFFFFFFFF) >>> 0
}

// 生成蓝色圆形图标
const size = 16
const png = createPNG(size, size, (x, y) => {
  const centerX = size / 2
  const centerY = size / 2
  const radius = 6
  const dist = Math.sqrt((x - centerX) ** 2 + (y - centerY) ** 2)
  
  if (dist <= radius) {
    return { r: 0x21, g: 0x96, b: 0xF3, a: 0xFF } // 蓝色
  }
  return { r: 0, g: 0, b: 0, a: 0 } // 透明
})

fs.writeFileSync(ICON_PATH, png)
console.log('Tray icon generated:', ICON_PATH)
