import { ipcMain, BrowserWindow } from 'electron';
import { vadEngine } from './vad-engine';

let currentWindow: BrowserWindow | null = null;

export function setupVADIPC() {
  // 前端请求开始 VAD 监听
  ipcMain.handle('vad:start', async (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (!win) return { success: false, error: 'no window' };

    currentWindow = win;

    // 设置回调：VAD 检测到语音结束 → 通知前端停止录音
    vadEngine.setCallbacks({
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

    vadEngine.reset();
    return { success: true };
  });

  // 前端发送音频帧给 VAD 处理
  ipcMain.handle('vad:process', async (_, frameArray: number[]) => {
    const frame = new Float32Array(frameArray);
    const result = await vadEngine.process(frame);
    return result;
  });

  // 前端请求停止
  ipcMain.handle('vad:stop', async () => {
    vadEngine.setCallbacks({});
    vadEngine.reset();
    return { success: true };
  });

  console.log('[VAD IPC] VAD IPC handlers registered');
}
