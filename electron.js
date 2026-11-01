const { app, BrowserWindow, screen } = require('electron');
const path = require('path');
const url = require('url');
const fs = require('fs');
const { spawn } = require('child_process');

let serverProcess = null;

function getServerPath() {
  if (process.env.ELECTRON_START_URL) {
    return null;
  }
  if (process.platform === 'win32') {
    return path.join(process.resourcesPath, 'server.exe');
  }
  return path.join(process.resourcesPath, 'server');
}

function getDevPythonPath() {
  if (process.platform === 'win32') {
    return path.join(__dirname, '..', '..', 'venv', 'Scripts', 'python.exe');
  }
  const repoRoot = path.join(__dirname, '..', '..');
  const linuxVenv = path.join(repoRoot, 'venv_linux', 'bin', 'python');
  if (fs.existsSync(linuxVenv)) {
    return linuxVenv;
  }
  const linuxPython = path.join(repoRoot, 'venv', 'bin', 'python');
  if (fs.existsSync(linuxPython)) {
    return linuxPython;
  }
  return process.env.PYTHON || process.env.PYTHON3 || 'python3';
}

function startBackend() {
  if (process.env.JARVIS_SKIP_BACKEND === '1' || process.env.JARVIS_SKIP_BACKEND === 'true') {
    console.log('JARVIS_SKIP_BACKEND set — no se inicia server.py (¿servicio systemd u otro proceso?)');
    return;
  }
  const serverPath = getServerPath();
  if (serverPath && fs.existsSync(serverPath)) {
    serverProcess = spawn(serverPath, [], {
      detached: false,
      stdio: 'ignore',
    });
    serverProcess.unref();
  } else {
    const pythonPath = getDevPythonPath();
    const serverScript = path.join(__dirname, '..', '..', 'server.py');
    if (fs.existsSync(serverScript)) {
      serverProcess = spawn(pythonPath, [serverScript], {
        cwd: path.join(__dirname, '..', '..'),
        detached: false,
        stdio: 'ignore',
      });
      serverProcess.unref();
      console.log('Backend started with Python in development mode');
    } else {
      console.warn('Python or server.py not found for development');
    }
  }
}

function createWindow() {
  const isLinux = process.platform === 'linux';
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width: waWidth, height: waHeight } = primaryDisplay.workArea;

  const win = new BrowserWindow({
    x: 0,
    y: 0,
    width: waWidth,
    height: waHeight,
    minWidth: 80,
    minHeight: 80,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    hasShadow: false,
    alwaysOnTop: true,
    fullscreenable: false,
    skipTaskbar: false,
    resizable: false,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
    icon: path.join(__dirname, 'icon.png'),
  });

  // === CAMBIO CLAVE: Ignorar eventos de ratón en toda la ventana, excepto donde haya contenido opaco ===
  win.setIgnoreMouseEvents(true, { forward: true });

  if (process.platform === 'win32') {
    win.setTitle('Jarvis');
  }

  win.webContents.on('did-finish-load', () => {
    if (isLinux) {
      win.webContents
        .executeJavaScript(
          "document.documentElement.classList.add('jarvis-overlay');",
          true,
        )
        .catch(() => {});
    }
  });

  win.loadURL('http://127.0.0.1:5000');

  win.once('ready-to-show', () => {
    win.show();
  });
}

app.whenReady().then(() => {
  try {
    app.setLoginItemSettings({
      openAtLogin: false,
      openAsHidden: false,
      path: process.execPath,
    });
  } catch (_) {
    /* ok */
  }
  startBackend();
  createWindow();
});

app.on('before-quit', () => {
  if (serverProcess && !serverProcess.killed) {
    serverProcess.kill();
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});