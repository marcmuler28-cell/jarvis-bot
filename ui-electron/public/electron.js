/**
 * electron.js v8 - Versión estable y limpia
 *
 * REGLAS DE ORO IMPLEMENTADAS:
 * 1. Carga Local (Opción A): El botón carga walkie_button.html con loadFile()
 * 2. focusable: false: El botón no roba foco del teclado
 * 3. Arrastre manual: Como focusable:false bloquea el arrastre nativo en KWin,
 *    implementamos el arrastre manual capturando mousedown/mousemove y
 *    moviendo la ventana con buttonWindow.setPosition()
 */

const { app, BrowserWindow, screen, Tray, Menu, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
let notifier;
try { notifier = require('node-notifier'); } catch(e) { console.log('[JARVIS] node-notifier no disponible'); }

let serverProcess = null;
let wallpaperWindow = null;
let buttonWindow = null;
let tray = null;

const BACKEND_URL = 'http://127.0.0.1:5000';
const BACKEND_HOST = '127.0.0.1';
const BACKEND_PORT = 5000;
const MAX_RETRIES = 60;
const RETRY_INTERVAL_MS = 1000;
const BUTTON_SIZE = 140;
const BUTTON_POS_FILE = path.join(process.env.HOME || '/tmp', '.jarvis', 'button_pos.json');

// ============================================================
// PERSISTENCIA DE POSICIÓN DEL BOTÓN
// ============================================================
function loadButtonPos() {
  try {
    if (fs.existsSync(BUTTON_POS_FILE)) {
      return JSON.parse(fs.readFileSync(BUTTON_POS_FILE, 'utf-8'));
    }
  } catch (e) {}
  return null;
}

function saveButtonPos(x, y) {
  try {
    const dir = path.dirname(BUTTON_POS_FILE);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(BUTTON_POS_FILE, JSON.stringify({ x, y }));
  } catch (e) {}
}

// ============================================================
// GESTIÓN DEL BACKEND
// ============================================================
function startBackend() {
  if (process.env.JARVIS_SKIP_BACKEND === '1' || process.env.JARVIS_SKIP_BACKEND === 'true') {
    console.log('[JARVIS] JARVIS_SKIP_BACKEND=1 → backend externo.');
    return;
  }
  const repoRoot = path.join(__dirname, '..', '..');
  const candidates = [
    path.join(repoRoot, 'venv_linux', 'bin', 'python'),
    path.join(repoRoot, 'venv', 'bin', 'python'),
    process.env.PYTHON, process.env.PYTHON3, 'python3',
  ];
  let pythonPath = 'python3';
  for (const c of candidates) if (c && fs.existsSync(c)) { pythonPath = c; break; }
  const serverScript = path.join(repoRoot, 'server.py');
  if (!fs.existsSync(serverScript)) {
    console.error('[JARVIS] No se encuentra server.py');
    return;
  }
  console.log('[JARVIS] Iniciando backend con Python:', pythonPath);
  serverProcess = spawn(pythonPath, [serverScript], {
    cwd: repoRoot, detached: false, stdio: 'ignore',
  });
  serverProcess.unref();
}

function checkBackendReady() {
  return new Promise((resolve) => {
    const req = http.get(
      { hostname: BACKEND_HOST, port: BACKEND_PORT, path: '/', timeout: 2000 },
      (res) => { res.resume(); resolve(res.statusCode !== undefined); }
    );
    req.on('error', () => resolve(false));
    req.on('timeout', () => { req.destroy(); resolve(false); });
  });
}

async function waitForBackend() {
  console.log('[JARVIS] Esperando backend...');
  for (let i = 1; i <= MAX_RETRIES; i++) {
    const ready = await checkBackendReady();
    if (ready) {
      console.log('[JARVIS] ✅ Backend listo tras ' + i + ' intento(s)');
      return true;
    }
    if (i === 1 || i % 10 === 0) {
      console.log('[JARVIS] Intento ' + i + '/' + MAX_RETRIES + '...');
    }
    await new Promise(r => setTimeout(r, RETRY_INTERVAL_MS));
  }
  console.log('[JARVIS] ❌ Backend no respondió');
  return false;
}

// ============================================================
// VENTANA 1: WALLPAPER
// ============================================================

// ============================================================
// NOTIFICACIONES NATIVAS DE KDE (vía node-notifier / notify-send)
// ============================================================
function showNativeNotification(title, message, iconPath) {
  if (!notifier) {
    // Fallback: notify-send directo
    const { exec } = require('child_process');
    const icon = iconPath || '';
    exec(`notify-send "${title}" "${message}" --icon="${icon}" --app-name="JarvisBot"`, (err) => {
      if (err) console.log('[JARVIS] notify-send no disponible');
    });
      return;
  }
  notifier.notify({
    title: title,
    message: message,
    icon: iconPath || path.join(__dirname, 'icon.png'),
                  appID: 'JarvisBot',
                  sound: false,
                  wait: false,
  });
  console.log('[JARVIS] Notificación nativa:', title);
}

function createDashboardWindow() {
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width, height } = primaryDisplay.workArea;

  wallpaperWindow = new BrowserWindow({
    x: 0, y: 0, width, height,
    minWidth: 80, minHeight: 80,
    frame: false,
    transparent: false,
    backgroundColor: '#000000',
    hasShadow: false,
    // type: 'toolbar',  (removido)            // Cambiado: toolbar evita que KWin la trate como app fullscreen
    alwaysOnTop: false,
    fullscreenable: false,
    fullscreen: false,
    skipTaskbar: true,
    skipPager: true,
    resizable: false,
    focusable: false,           // Confirmado: no roba foco
    title: 'JarvisBot Wallpaper',
    webPreferences: { nodeIntegration: true, contextIsolation: false },
    icon: path.join(__dirname, 'icon.png'),
  });

  console.log('[JARVIS] Ventana wallpaper creada (type=toolbar, tamaño: ' + width + 'x' + height + ')');
  wallpaperWindow.setIgnoreMouseEvents(true, { forward: true });
  wallpaperWindow.setAlwaysOnTop(false);
  // Quitar foco inmediatamente para que KWin no la priorice
  wallpaperWindow.blur();
  // Hacer visible en todos los escritorios virtuales
  wallpaperWindow.setVisibleOnAllWorkspaces(true);

  // Forzar layer "below" en KWin usando wmctrl (KWin ignora type:desktop a veces)
  const { exec } = require('child_process');
  const forceBelow = () => {
    if (!wallpaperWindow || wallpaperWindow.isDestroyed()) return;
    // Obtener el ID nativo de la ventana (X11 window ID)
    const handle = wallpaperWindow.getNativeWindowHandle();
    // El handle es un Buffer, convertir a número hex
    const winId = '0x' + handle.toString('hex');
    console.log('[JARVIS] Wallpaper native window ID:', winId);

    // Usar xdotool con el ID exacto (no depende del título)
    const XDOTOOL = '/usr/bin/xdotool';
    const WMCTRL = '/usr/bin/wmctrl';
    const cmd = `"${WMCTRL}" -i -r "${winId}" -b add,below,skip_taskbar,skip_pager`;
    exec(cmd, (err) => {
      if (err) {
        console.log('[JARVIS] wmctrl -i falló, intentando xdotool...');
        // Fallback: xdotool con window ID
        exec(`"${XDOTOOL}" set_window --below ${winId}`, (err2) => {
          if (err2) console.log('[JARVIS] xdotool tampoco disponible, usando type:desktop nativo');
          else console.log('[JARVIS] ✅ Wallpaper forzado below via xdotool');
        });
      } else {
        console.log('[JARVIS] ✅ Wallpaper forzado a layer "below" via wmctrl -i');
      }
    });
  };
  // Aplicar después de que la ventana sea visible (reintentar por si tarda)
  setTimeout(forceBelow, 500);
  setTimeout(forceBelow, 2000);
  setTimeout(forceBelow, 5000);

  // Cargar dashboard.html SOLO cuando el backend esté 100% listo
  waitForBackend().then((ready) => {
    if (ready && wallpaperWindow && !wallpaperWindow.isDestroyed()) {
      console.log('[JARVIS] Backend listo. Cargando Dashboard...');
      wallpaperWindow.loadURL(BACKEND_URL + '/dashboard').catch(err => {
        console.error('[JARVIS] Error cargando Dashboard:', err.message);
      });
    } else {
      console.error('[JARVIS] Backend no disponible, Dashboard no cargado.');
    }
  });

  // IPC: mostrar/ocultar dashboard desde el botón
  ipcMain.on('dashboard-toggle', () => {
    if (!wallpaperWindow || wallpaperWindow.isDestroyed()) return;
    if (wallpaperWindow.isVisible()) {
      wallpaperWindow.hide();
      console.log('[JARVIS] Dashboard oculto');
    } else {
      wallpaperWindow.show();
      wallpaperWindow.focus();
      console.log('[JARVIS] Dashboard visible');
    }
  });


  // IPC: recibir solicitud de notificación desde el renderer
  ipcMain.on('show-notification', (event, title, message) => {
    showNativeNotification(title, message);
  });


  // IPC: redimensionar la ventana del botón (para PIN panel)
  ipcMain.on('resize-button-window', (event, width, height) => {
    if (!buttonWindow || buttonWindow.isDestroyed()) return;
    const [currentX, currentY] = buttonWindow.getPosition();
    const [currentW, currentH] = buttonWindow.getSize();

    // Calcular offset para mantener el CENTRO del botón en el mismo lugar
    const offsetX = (width - currentW) / 2;
    const offsetY = (height - currentH) / 2;

    buttonWindow.setBounds({
      x: Math.round(currentX - offsetX),
                           y: Math.round(currentY - offsetY),
                           width: width,
                           height: height
    });
    console.log('[JARVIS] Botón redimensionado a:', width, 'x', height);
  });

  ipcMain.on('dashboard-hide', () => {
    if (wallpaperWindow && !wallpaperWindow.isDestroyed()) {
      wallpaperWindow.hide();
      console.log('[JARVIS] Dashboard oculto via Esc');
    }
  });
}

// ============================================================
// VENTANA 2: BOTÓN FLOTANTE (CARGA LOCAL + ARRASTRE MANUAL)
// ============================================================
function createButtonWindow() {
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width: scrWidth, height: scrHeight } = primaryDisplay.workArea;

  const safeWidth = (scrWidth && scrWidth > 100) ? scrWidth : 1920;
  const safeHeight = (scrHeight && scrHeight > 100) ? scrHeight : 1080;

  const savedPos = loadButtonPos();
  let x = safeWidth - BUTTON_SIZE - 20;
  let y = safeHeight - BUTTON_SIZE - 20;
  if (savedPos && savedPos.x > 100 && savedPos.y > 100) {
    x = savedPos.x;
    y = savedPos.y;
    console.log('[JARVIS] Usando posición guardada:', x, y);
  } else {
    console.log('[JARVIS] Usando posición default:', x, y);
  }
  const maxX = safeWidth - BUTTON_SIZE;
  const maxY = safeHeight - BUTTON_SIZE;
  x = Math.max(0, Math.min(x, maxX));
  y = Math.max(0, Math.min(y, maxY));

  buttonWindow = new BrowserWindow({
    width: BUTTON_SIZE,
    height: BUTTON_SIZE,
    x: x,
    y: y,
    minWidth: BUTTON_SIZE,
    minHeight: BUTTON_SIZE,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    hasShadow: false,
    alwaysOnTop: true,
    fullscreenable: false,
    skipTaskbar: true,
    resizable: false,
    focusable: false,
    title: 'JarvisBot Button',
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
    icon: path.join(__dirname, 'icon.png'),
  });

  console.log('[JARVIS] Ventana botón creada en posición:', x, y);

  // REGLA #1: Cargar HTML LOCAL, pero NO mostrar hasta que backend esté listo
  const buttonHtmlPath = path.join(__dirname, 'walkie_button.html');
  if (fs.existsSync(buttonHtmlPath)) {
    console.log('[JARVIS] Cargando HTML del botón localmente...');
    buttonWindow.loadFile(buttonHtmlPath).then(() => {
      console.log('[JARVIS] ✅ Botón cargado localmente (walkie_button.html)');
      // Esperar al backend antes de mostrar el botón
      waitForBackend().then((ready) => {
        if (ready && buttonWindow && !buttonWindow.isDestroyed()) {
          buttonWindow.show();
          console.log('[JARVIS] Botón visible (backend listo)');
        }
      });
    }).catch(err => {
      console.error('[JARVIS] ❌ Error cargando botón local:', err.message);
    });
  } else {
    console.error('[JARVIS] ❌ No se encuentra walkie_button.html en:', buttonHtmlPath);
  }

  // Forzar alwaysOnTop después de 2s
  setTimeout(() => {
    if (buttonWindow && !buttonWindow.isDestroyed()) {
      buttonWindow.setAlwaysOnTop(true, 'screen-saver');
      console.log('[JARVIS] alwaysOnTop forzado en botón');
    }
  }, 2000);

  // REGLA #3: Arrastre nativo con screen.getCursorScreenPoint()
  // En Linux/Wayland con focusable:false, las coords del evento mouse del renderer
  // pueden ser poco fiables. Usamos la API nativa de Electron en el main process.
  let dragOffsetX = 0;
  let dragOffsetY = 0;
  let isDragging = false;
  let dragInterval = null;

  ipcMain.on('button-drag-start', (event, offsetX, offsetY) => {
    if (!buttonWindow) return;
    // Capturar offset: diferencia entre cursor y esquina de la ventana
    const cursor = screen.getCursorScreenPoint();
    const [winX, winY] = buttonWindow.getPosition();
    dragOffsetX = cursor.x - winX;
    dragOffsetY = cursor.y - winY;
    isDragging = true;
    console.log('[JARVIS] Drag start - cursor:', cursor.x, cursor.y, '| offset:', dragOffsetX, dragOffsetY);

    // Loop nativo (cada 16ms = 60fps) para mover la ventana siguiendo el cursor
    if (dragInterval) clearInterval(dragInterval);
    dragInterval = setInterval(() => {
      if (!isDragging || !buttonWindow || buttonWindow.isDestroyed()) {
        if (dragInterval) { clearInterval(dragInterval); dragInterval = null; }
        return;
      }
      const c = screen.getCursorScreenPoint();
      const newX = c.x - dragOffsetX;
      const newY = c.y - dragOffsetY;
      const [w, h] = buttonWindow.getSize();
      buttonWindow.setBounds({ x: newX, y: newY, width: w, height: h });
    }, 16);
  });

  ipcMain.on('button-drag-end', () => {
    isDragging = false;
    if (dragInterval) { clearInterval(dragInterval); dragInterval = null; }
    if (!buttonWindow) return;
    const [px, py] = buttonWindow.getPosition();
    saveButtonPos(px, py);
    console.log('[JARVIS] Botón movido a:', px, py);
  });
}

// ============================================================
// SYSTEM TRAY
// ============================================================
function createTray() {
  const iconPath = path.join(__dirname, 'icon.png');
  if (!fs.existsSync(iconPath)) return;
  tray = new Tray(iconPath);
  tray.setToolTip('JarvisBot');
  const contextMenu = Menu.buildFromTemplate([
    { label: ' JarvisBot', enabled: false },
    { type: 'separator' },
    { label: 'Reiniciar Backend', click: () => {
      const { exec } = require('child_process');
      exec('systemctl --user restart jarvisbot.service', (error) => {
        if (!error) {
          console.log('[JARVIS] Backend reiniciado');
          setTimeout(() => {
            if (wallpaperWindow) wallpaperWindow.loadURL(BACKEND_URL);
          }, 5000);
        }
      });
    }},
    { label: 'Resetear posición del botón', click: () => {
      try { fs.unlinkSync(BUTTON_POS_FILE); } catch (e) {}
      const primaryDisplay = screen.getPrimaryDisplay();
      const { width, height } = primaryDisplay.workArea;
      if (buttonWindow) buttonWindow.setPosition(width - BUTTON_SIZE - 20, height - BUTTON_SIZE - 20);
      console.log('[JARVIS] Posición del botón reseteada');
    }},
    { type: 'separator' },
    { label: 'Salir', click: () => app.quit() }
  ]);
  tray.setContextMenu(contextMenu);
  tray.on('click', () => {
    if (buttonWindow) {
      if (buttonWindow.isVisible()) buttonWindow.hide();
      else buttonWindow.show();
    }
  });
}

// ============================================================
// CICLO DE VIDA DE LA APP
// ============================================================
app.whenReady().then(async () => {
  app.setLoginItemSettings({ openAtLogin: false });
  startBackend();
  if (!process.env.JARVIS_SKIP_BACKEND) {
    await new Promise(r => setTimeout(r, 1000));
  }
  createDashboardWindow();
  createButtonWindow();
  createTray();
});

app.on('before-quit', () => {
  if (serverProcess && !serverProcess.killed) serverProcess.kill();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createDashboardWindow();
    createButtonWindow();
  }
});
