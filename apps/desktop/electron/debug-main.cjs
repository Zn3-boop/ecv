const { app, BrowserWindow } = require('electron')

console.log('debug electron main loaded')
console.log('electron module keys:', Object.keys(require('electron')))
console.log('app exists:', !!app)
console.log('BrowserWindow exists:', !!BrowserWindow)

app.whenReady().then(() => {
  console.log('ready')
  const win = new BrowserWindow({ width: 800, height: 600 })
  win.loadURL('data:text/html,<h1>debug ok</h1>')
})
