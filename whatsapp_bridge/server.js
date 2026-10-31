#!/usr/bin/env node
/**
 * whatsapp_bridge/server.js — puente local entre el cerebro Python (JarvisBot)
 * y TU PROPIO WhatsApp, con whatsapp-web.js + LocalAuth (sesión de WhatsApp Web).
 *
 *   cerebro (jarvis_whatsapp.py) --HTTP 127.0.0.1--> este proceso
 *        └─ whatsapp-web.js (puppeteer + chromium, headless)
 *             └─ sesión persistente en ./.wwebjs_auth  (¡NO subir a git!)
 *
 * Endpoints (todos exigen X-Jarvis-Token == JARVIS_WA_BRIDGE_TOKEN,
 * o ?t=TOKEN para abrir el QR desde el navegador):
 *   GET  /status    -> {ready, iniciando, conQR, info}
 *   GET  /qr        -> página HTML con el QR (o JSON si ?json=1)
 *   POST /send      -> {to: "5199...", message: "texto"}  (solo números; el
 *                      apodo lo resuelve antes jarvis_whatsapp.py)
 *   GET  /mensajes?desde=EPOCH -> mensajes escritos en TU PROPIO chat
 *                      (te escribes a ti mismo desde el celular y Jarvis
 *                      los lee con `python3 jarvis_whatsapp.py escuchar`)
 *
 * Escucha SOLO en 127.0.0.1: nadie de tu red puede hablar con él.
 */
const http = require('http');
const path = require('path');
const fs = require('fs');
const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode');

const PUERTO = parseInt(process.env.JARVIS_WA_BRIDGE_PORT || '5015', 10);
const TOKEN = process.env.JARVIS_WA_BRIDGE_TOKEN || '';
const HOST = '127.0.0.1';

const CHROME =
  process.env.CHROME_PATH ||
  ['/usr/bin/chromium', '/usr/bin/chromium-browser',
   '/usr/bin/google-chrome-stable', '/usr/bin/google-chrome']
    .find((p) => fs.existsSync(p)) || undefined;

function log(...a) {
  console.log(new Date().toLocaleTimeString('es-PE'), '-', ...a);
}

let ultimoQR = null;
let qrDataUrl = null;
let listo = false;
let iniciando = true;
let authYaAvisado = false;

// Chat propio: mensajes que MARC escribe a sí mismo desde el celular.
const arrancadoEn = Math.floor(Date.now() / 1000);
const colaChat = [];              // {id, ts, texto} — solo el chat propio
const idsDelPuente = new Set();   // ids que ESTE puente envió (para no re-leerlos)

/** true si el mensaje es un «estado» de WhatsApp o un broadcast, no un chat */
function esEstado(msg) {
  if (!msg) return true;
  if (msg.isStatus) return true;
  const de = String(msg.from || '');
  return de === 'status@broadcast' || de.endsWith('@broadcast');
}

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: path.join(__dirname, '.wwebjs_auth') }),
  puppeteer: {
    headless: true,
    executablePath: CHROME,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  },
});

client.on('qr', async (qr) => {
  ultimoQR = qr;
  qrDataUrl = null;
  try { qrDataUrl = await qrcode.toDataURL(qr, { margin: 1, width: 480 }); } catch (_) {}
  try { console.log('\n' + await qrcode.toString(qr, { small: true }) + '\n'); } catch (_) {}
  log('QR NUEVO → escanéalo con WhatsApp → Dispositivos vinculados → Vincular un dispositivo');
});
client.on('loading_screen', (pct) => log(`Cargando WhatsApp Web… ${pct}%`));
client.on('authenticated', () => {
  // whatsapp-web.js puede emitir este evento varias veces durante el arranque:
  // avisamos solo una vez hasta que se desconecte.
  if (authYaAvisado) return;
  authYaAvisado = true;
  log('Sesión autenticada (LocalAuth).');
});
client.on('auth_failure', (m) => log('FALLO de autenticación:', m));
client.on('ready', () => {
  listo = true; iniciando = false; ultimoQR = null; qrDataUrl = null;
  const n = client.info && client.info.wid ? client.info.wid.user : '?';
  log(`WhatsApp LISTO con tu número +${n}. Ya puedes hablar con Jarvis.`);
});
client.on('change_state', (s) => log('Estado:', s));
client.on('disconnected', (razon) => {
  listo = false; iniciando = false; authYaAvisado = false;
  log('Desconectado:', razon, '— reinicia el puente para reconectar.');
});
client.on('message', (msg) => {
  // Los estados de los contactos (status@broadcast) llegan como mensajes:
  // los ignoramos para no inundar la terminal ni responderlos por error.
  if (esEstado(msg)) return;
  if (!msg.fromMe && msg.body) {
    log('💬 mensaje entrante de', msg.from, '→', String(msg.body).slice(0, 80));
  }
});

// message_create SÍ dispara para mensajes escritos desde tu propio celular
// (el evento 'message' ignora los fromMe). Solo nos interesa TU chat propio.
client.on('message_create', (msg) => {
  if (esEstado(msg)) return;
  const serial = msg.id && (msg.id._serialized || msg.id.id);
  if (serial && idsDelPuente.has(serial)) return; // respuesta que envió Jarvis
  const mio = client.info && client.info.wid ? client.info.wid._serialized : null;
  if (!mio || !msg.fromMe || msg.from !== mio) return; // solo el chat contigo
  if ((msg.timestamp || 0) < arrancadoEn) return;      // historial viejo
  const texto = String(msg.body || '').trim();
  if (!texto) return;
  colaChat.push({ id: serial || '', ts: msg.timestamp || arrancadoEn, texto });
  if (colaChat.length > 200) colaChat.splice(0, colaChat.length - 200);
  log('💬 TÚ (chat propio):', texto.slice(0, 80));
});

client.initialize().catch((e) => {
  iniciando = false;
  log('ERROR al iniciar el cliente:', e && e.message);
});

// ── HTTP ─────────────────────────────────────────────────────────────
function httpError(code, mensaje) {
  const e = new Error(mensaje);
  e.status = code;
  return e;
}

function autorizado(req, url) {
  if (!TOKEN) return true; // sin token: solo escucha en 127.0.0.1
  if (req.headers['x-jarvis-token'] === TOKEN) return true;
  if (url.searchParams.get('t') === TOKEN) return true;
  return false;
}

function json(res, code, obj) {
  const body = JSON.stringify(obj, null, 2);
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(body);
}

function paginaQR() {
  const refresco = qrDataUrl
    ? ''
    : '<p>Aún no hay QR en pantalla. Si el puente acaba de arrancar, espera 5 s ' +
      '(esta página se refresca sola) y si la sesión ya está activa, no hace falta QR.</p>';
  return `<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="5">
<title>Jarvis · QR de WhatsApp</title>
<style>
  body{font-family:system-ui,sans-serif;background:#0b141a;color:#e9edef;
       display:flex;flex-direction:column;align-items:center;gap:1rem;padding:2rem}
  img{background:#fff;border-radius:12px;padding:12px;max-width:420px}
  code{background:#111;border:1px solid #333;padding:.2rem .5rem;border-radius:6px}
</style></head><body>
<h1>📱 Vincula tu WhatsApp con Jarvis</h1>
<p>WhatsApp → <b>Dispositivos vinculados</b> → <b>Vincular un dispositivo</b></p>
${qrDataUrl ? `<img alt="QR de WhatsApp" src="${qrDataUrl}">` : ''}
${refresco}
<p><small>Sesión local en <code>.wwebjs_auth/</code> · solo 127.0.0.1 · no subas esa carpeta a git</small></p>
</body></html>`;
}

async function enviar(to, message) {
  if (!listo || !client.info) {
    throw httpError(503, 'WhatsApp todavía no está listo (¿falta escanear el QR?)');
  }
  if (!message || !String(message).trim()) {
    throw httpError(400, 'message vacío');
  }
  const digits = String(to || '').replace(/\D/g, '');
  if (digits.length < 9) {
    throw httpError(400, `número inválido: «${to}» (esperado código de país + número)`);
  }
  // Enviarte a TI MISMO: getNumberId a veces falla con tu propio número;
  // usamos directamente el wid de la sesión.
  const propioUser = client.info && client.info.wid ? client.info.wid.user : null;
  let wid = null;
  if (propioUser && digits === propioUser) {
    wid = client.info.wid;
  } else {
    wid = await client.getNumberId(digits); // null si no tiene WhatsApp
  }
  if (!wid) {
    throw httpError(404, `el número +${digits} no tiene WhatsApp registrado`);
  }
  const texto = String(message);
  const esPropio = propioUser && digits === propioUser;

  // Envío a TI MISMO: whatsapp-web.js es quisquilloso con tu propio chat
  // (getChatById puede traer null y chat.sendMessage devuelve undefined).
  // Probamos 3 caminos y hasta 2 rondas; mientras NO haya excepción real,
  // el mensaje SÍ llega al chat «Message yourself».
  let enviado = null;
  let errores = [];
  let directoSinError = false;
  for (let ronda = 0; ronda < 2 && (!enviado || !enviado.id); ronda++) {
    if (ronda > 0) {
      await new Promise((r) => setTimeout(r, 2000)); // pausa anti rate-limit
      errores = [];
      directoSinError = false;
    }
    // Camino 1: chat del propio número
    try {
      const chat = await client.getChatById(wid._serialized);
      if (chat) enviado = await chat.sendMessage(texto);
    } catch (e) { errores.push('chat: ' + (e && e.message)); }
    // Camino 2: sendMessage directo (el clásico; a veces responde undefined)
    if (!enviado || !enviado.id) {
      try {
        const r2 = await client.sendMessage(wid._serialized, texto);
        if (r2 && r2.id) enviado = r2;
        else if (esPropio) directoSinError = true;
      } catch (e) { errores.push('directo: ' + (e && e.message)); }
    }
    // Camino 3 (solo a ti mismo): buscar el chat en la lista y enviarle
    if ((!enviado || !enviado.id) && esPropio) {
      try {
        const chats = await client.getChats();
        const propio = (chats || []).find(
          (c) => c && c.id && c.id._serialized === wid._serialized);
        if (propio) {
          const r3 = await propio.sendMessage(texto);
          if (r3 && r3.id) enviado = r3;
        }
      } catch (e) { errores.push('lista: ' + (e && e.message)); }
    }
  }

  const idSer = enviado && enviado.id ? (enviado.id._serialized || enviado.id.id) : null;
  if (!idSer) {
    // Sin excepción y a ti mismo = entregado aunque WhatsApp no confirme.
    if (esPropio && (errores.length === 0 || directoSinError)) {
      log('📤 enviado a TI MISMO', wid._serialized, '(sin confirmación de WhatsApp)');
      return { ok: true, chatId: wid._serialized, id: null,
               nota: 'entregado sin confirmación de WhatsApp' };
    }
    throw httpError(502,
      `WhatsApp no aceptó el envío a +${digits}: ${errores.join(' | ') || 'sin confirmación'}`);
  }
  // Recordar el id que envió el puente para no volver a leerlo como
  // si fuera una orden tuya (evita el bucle Jarvis ↔ Jarvis).
  try {
    idsDelPuente.add(idSer);
    if (idsDelPuente.size > 1000) idsDelPuente.clear();
  } catch (_) {}
  log('📤 enviado a', wid._serialized);
  return { ok: true, chatId: wid._serialized, id: idSer };
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${HOST}:${PUERTO}`);
  try {
    if (!autorizado(req, url)) return json(res, 401, { error: 'token inválido' });

    if (req.method === 'GET' && url.pathname === '/status') {
      return json(res, 200, {
        ready: listo,
        iniciando,
        conQR: Boolean(ultimoQR),
        info: listo && client.info
          ? { pushname: client.info.pushname, wid: client.info.wid.user }
          : null,
      });
    }

    if (req.method === 'GET' && url.pathname === '/qr') {
      if (listo) return json(res, 200, { listo: true, mensaje: 'sesión ya activa; no hace falta QR' });
      if (!qrDataUrl) return json(res, 404, { error: 'sin QR ahora mismo' });
      if (url.searchParams.get('json') === '1') {
        return json(res, 200, { qr: qrDataUrl });
      }
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      return res.end(paginaQR());
    }

    if (req.method === 'POST' && url.pathname === '/send') {
      let cuerpo = '';
      req.on('data', (c) => { cuerpo += c; if (cuerpo.length > 1e6) req.destroy(); });
      req.on('end', async () => {
        try {
          const d = JSON.parse(cuerpo || '{}');
          return json(res, 200, await enviar(d.to, d.message));
        } catch (e) {
          return json(res, e.status || 500, { error: e.message });
        }
      });
      return;
    }

    if (req.method === 'GET' && url.pathname === '/mensajes') {
      const desde = parseInt(url.searchParams.get('desde') || '0', 10) || 0;
      const ahora = Math.floor(Date.now() / 1000);
      // purga: nada de más de 1 hora
      while (colaChat.length && ahora - colaChat[0].ts > 3600) colaChat.shift();
      return json(res, 200, { ok: true, mensajes: colaChat.filter((m) => m.ts > desde) });
    }

    if (req.method === 'GET' && url.pathname === '/health') {
      res.writeHead(200, { 'Content-Type': 'text/plain' });
      return res.end('ok');
    }

    json(res, 404, { error: 'ruta desconocida' });
  } catch (e) {
    json(res, e.status || 500, { error: e.message });
  }
});

server.on('error', (e) => {
  if (e && e.code === 'EADDRINUSE') {
    log(`ERROR: el puerto ${PUERTO} ya está ocupado — ya hay OTRO puente corriendo.`);
    log('  → Ve a esa otra terminal y púlsale Ctrl+C, o mátalo con:');
    log('      pkill -f "node server.js"');
    log('  → Después vuelve a lanzar ./iniciar.sh (no hace falta QR de nuevo).');
    process.exit(1);
  }
  throw e;
});

server.listen(PUERTO, HOST, () => {
  log(`Puente WhatsApp en http://${HOST}:${PUERTO}`);
  log(`Chrome/Chromium: ${CHROME || '(puppeteer usará el suyo)'}`);
  log(TOKEN ? 'Token: configurado ✔' : 'AVISO: sin JARVIS_WA_BRIDGE_TOKEN (acepta cualquier cliente local)');
});
