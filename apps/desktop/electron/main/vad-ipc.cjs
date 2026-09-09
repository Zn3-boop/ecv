const { ipcMain, BrowserWindow } = require('electron');
let vadEngine = null;
let currentWindow = null;

// 动态导入 VAD Engine
async function getVADEngine() {
  if (!vadEngine) {
    const { VADEngine } = await import('./vad-engine.js');
    vadEngine = new VADEngine();
    await vadEngine.init();
  }
  return vadEngine;
}

function setupVADIPC() {
  // 前端请求开始 VAD 监听
  ipcMain.handle('vad:start', async (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (!win) return { success: false, error: 'no window' };

    currentWindow = win;
    const engine = await getVADEngine();

    // 设置回调：VAD 检测到语音结束 → 通知前端停止录音
    engine.setCallbacks({
      onSpeechStart: () => {
        if (currentWindow && !currentWindow.isDestroyed()) {
          currentWindow.webContents.send('vad:speech-start');
        }
      },
      onSpeechEnd: () => {
        if (currentWindow && !currentWindow.isDestroyed()) {
          currentWindow.webContents.send('vad:speech-end');
        }
      },
    });

    engine.reset();
    return { success: true };
  });

  // 前端发送音频帧给 VAD 处理
  ipcMain.handle('vad:process', async (_, frameArray) => {
    const engine = await getVADEngine();
    const frame = new Float32Array(frameArray);
    const result = await engine.process(frame);
    return result;
  });

  // 前端请求停止
  ipcMain.handle('vad:stop', async () => {
    const engine = await getVADEngine();
    engine.setCallbacks({});
    engine.reset();
    return { success: true };
  });

  console.log('[VAD IPC] VAD IPC handlers registered');
}

module.exports = { setupVADIPC };