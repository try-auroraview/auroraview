'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('ipc', {
  postMessage(message) {
    if (typeof message !== 'string' || message.length > 1024 * 1024) throw new Error('invalid bridge message');
    ipcRenderer.send('auroraview:bridge', message);
  },
  onMessage(callback) {
    if (typeof callback !== 'function') throw new Error('bridge callback required');
    const listener = (_event, message) => callback(message);
    ipcRenderer.on('auroraview:delivery', listener);
    return () => ipcRenderer.removeListener('auroraview:delivery', listener);
  },
});
