import React, { useState, useEffect, useRef } from 'react';
import io from 'socket.io-client';
import './App.css';

const socket = io('http://127.0.0.1:5000', {
  autoConnect: false,
  reconnectionAttempts: 20,
  reconnectionDelay: 1000,
  transports: ['polling', 'websocket'],
});

const statusLabels = {
  desconectado: 'OFFLINE',
  conectando: 'CONECTANDO…',
  inactivo: 'EN ESPERA',
  escuchando: 'ESCUCHANDO',
  procesando: 'PROCESANDO',
  hablando: 'HABLANDO',
};

function App() {
  const [status, setStatus] = useState('desconectado');
  const [connected, setConnected] = useState(false);
  const [message, setMessage] = useState('Voz pasiva: di "Alexa" o "Jarvis" cerca del micrófono (config. en ui.py).');
  const statusRef = useRef(status);
  const connectedRef = useRef(false);
  const canvasRef = useRef(null);
  const requestRef = useRef(null);
  const tRef = useRef(0);
  const energyRef = useRef(0);
  const [freqLabel, setFreqLabel] = useState('FREQ — — —');
  const [clockStr, setClockStr] = useState('00:00:00');

  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  useEffect(() => {
    connectedRef.current = connected;
  }, [connected]);

  /* FREQ + reloj como jarvis_ai_voice_interface.html (~2 Hz) */
  useEffect(() => {
    const id = setInterval(() => {
      const e = energyRef.current;
      const f = Math.floor(800 + e * 2400);
      setFreqLabel(`FREQ ${f} Hz`);
      const d = new Date();
      setClockStr(d.toTimeString().slice(0, 8));
    }, 333);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    setStatus('conectando');
    console.log('[Socket.IO] Attempting to connect to http://127.0.0.1:5000');
    socket.connect();

    socket.on('connect', () => {
      console.log('[Socket.IO] Connected successfully');
      setConnected(true);
      setStatus('inactivo');
      socket.emit('client_ready');
    });

    socket.on('disconnect', () => {
      console.log('[Socket.IO] Disconnected');
      setConnected(false);
      setStatus('desconectado');
    });

    socket.on('connect_error', (error) => {
      console.error('[Socket.IO] Connection error:', error);
      setConnected(false);
      setStatus('desconectado');
    });

    socket.on('status', (data) => {
      if (data && data.status) {
        console.log('[Socket.IO] Status received:', data.status);
        setStatus(data.status);
      }
    });

    socket.on('message', (data) => {
      if (data.text) {
        console.log('[Socket.IO] Message received:', data.type, data.text);
        setMessage(data.text);
      }
    });

    return () => {
      socket.off('connect');
      socket.off('disconnect');
      socket.off('connect_error');
      socket.off('status');
      socket.off('message');
    };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const ui = canvas.parentElement;
    let W = 0;
    let H = 0;
    let cx = 0;
    let cy = 0;

    // Mismos parámetros base que jarvis_ai_voice_interface.html (referencia)
    const orbits = [
      { a: 88, b: 36, tilt: 0, speed: 0.018, phase: 0, color: '#00c8ff', alpha: 0.9 },
      { a: 78, b: 32, tilt: 1.1, speed: 0.013, phase: 2.1, color: '#40e0ff', alpha: 0.7 },
      { a: 95, b: 28, tilt: -0.6, speed: 0.022, phase: 4.2, color: '#00a0e0', alpha: 0.6 },
    ];

    const particles = Array.from({ length: 40 }, () => ({
      angle: Math.random() * Math.PI * 2,
      r: 115 + Math.random() * 70,
      speed: (Math.random() - 0.5) * 0.004,
      size: Math.random() * 1.5 + 0.3,
      alpha: Math.random() * 0.5 + 0.1,
      drift: Math.random() * 0.001,
    }));

    const resize = () => {
      W = canvas.width = ui.clientWidth;
      H = canvas.height = ui.clientHeight;
      cx = W / 2;
      cy = H / 2;
    };

    /** Energía visual por estado (igual que jarvis_ai_voice_interface.html). Sin servidor: “respiración” demo. */
    const getEnergy = () => {
      const s = statusRef.current;
      if (!connectedRef.current) {
        const tt = tRef.current;
        return 0.35 + 0.45 * (0.5 + 0.5 * Math.sin(tt * 0.8 + Math.sin(tt * 0.3) * 2));
      }
      switch (s) {
        case 'escuchando':
          return 0.98;
        case 'hablando':
          return 0.78;
        case 'procesando':
          return 0.42;
        case 'inactivo':
          return 0.22;
        case 'desconectado':
          return 0.06;
        case 'conectando':
          return 0.15;
        default:
          return 0.18;
      }
    };

    /**
     * Átomo centrado en (cx,cy): el HTML hace translate(cx,cy) y dibuja en (0,0).
     * Antes: rotate() aplicaba al origen de la pantalla → órbitas mal centradas.
     */
    const drawAtom = (e) => {
      const glow = 0.3 + e * 0.7;
      ctx.save();
      ctx.translate(cx, cy);

      for (let ring = 3; ring >= 1; ring -= 1) {
        const r = 18 + ring * 12 + e * 10;
        const grad = ctx.createRadialGradient(0, 0, 0, 0, 0, r);
        grad.addColorStop(0, `rgba(0,200,255,${0.25 * glow * (1 / ring)})`);
        grad.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.beginPath();
        ctx.arc(0, 0, r, 0, Math.PI * 2);
        ctx.fillStyle = grad;
        ctx.fill();
      }

      orbits.forEach((orb) => {
        const dynamicA = orb.a * (1 + e * 0.08);
        const dynamicB = orb.b * (1 + e * 0.05);
        const alpha = orb.alpha * (0.5 + e * 0.5);
        ctx.save();
        ctx.rotate(orb.tilt);
        ctx.strokeStyle = orb.color;
        ctx.lineWidth = 0.8;
        ctx.globalAlpha = alpha * 0.55;
        ctx.beginPath();
        ctx.ellipse(0, 0, dynamicA, dynamicB, 0, 0, Math.PI * 2);
        ctx.stroke();

        ctx.globalAlpha = alpha;
        const angle = tRef.current * orb.speed * (60 * 0.016) + orb.phase;
        const ex = Math.cos(angle) * dynamicA;
        const ey = Math.sin(angle) * dynamicB;
        const eg = ctx.createRadialGradient(ex, ey, 0, ex, ey, 7 + e * 5);
        eg.addColorStop(0, '#fff');
        eg.addColorStop(0.3, orb.color);
        eg.addColorStop(1, 'rgba(0,200,255,0)');
        ctx.beginPath();
        ctx.arc(ex, ey, 7 + e * 5, 0, Math.PI * 2);
        ctx.fillStyle = eg;
        ctx.fill();

        const trailLen = 30;
        for (let j = 1; j <= trailLen; j += 1) {
          const ta = angle - (j / trailLen) * 0.8;
          const tx2 = Math.cos(ta) * dynamicA;
          const ty2 = Math.sin(ta) * dynamicB;
          ctx.beginPath();
          ctx.arc(tx2, ty2, (1 - j / trailLen) * 3, 0, Math.PI * 2);
          ctx.globalAlpha = alpha * (1 - j / trailLen) * 0.6;
          ctx.fillStyle = orb.color;
          ctx.fill();
        }
        ctx.restore();
      });

      const nr = 8 + e * 6;
      const ng = ctx.createRadialGradient(0, 0, 0, 0, 0, nr);
      ng.addColorStop(0, '#ffffff');
      ng.addColorStop(0.3, '#80f0ff');
      ng.addColorStop(0.7, '#00c8ff');
      ng.addColorStop(1, 'rgba(0,180,255,0)');
      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(0, 0, nr, 0, Math.PI * 2);
      ctx.fillStyle = ng;
      ctx.fill();
      ctx.restore();
    };

    const drawParticles = (e) => {
      ctx.save();
      ctx.translate(cx, cy);
      particles.forEach((p) => {
        p.angle += p.speed + p.drift * e * 3;
        const x = Math.cos(p.angle) * p.r;
        const y = Math.sin(p.angle) * p.r * 0.4;
        ctx.globalAlpha = p.alpha * (0.5 + e * 0.5);
        ctx.fillStyle = '#00c8ff';
        ctx.beginPath();
        ctx.arc(x, y, p.size, 0, Math.PI * 2);
        ctx.fill();
      });
      ctx.restore();
    };

    const drawRings = (e) => {
      ctx.save();
      ctx.translate(cx, cy);
      const radii = [130, 160, 195];
      radii.forEach((r, i) => {
        const alpha = (0.05 + e * 0.12) * (1 - i * 0.25);
        ctx.strokeStyle = '#00c8ff';
        ctx.lineWidth = 0.5;
        ctx.globalAlpha = alpha;
        ctx.setLineDash([4, 8]);
        ctx.lineDashOffset = -tRef.current * (i % 2 === 0 ? 0.3 : -0.3);
        ctx.beginPath();
        ctx.arc(0, 0, r, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
      });
      ctx.restore();
    };

    const drawWaveform = (ev) => {
      if (ev < 0.1) return;
      ctx.save();
      ctx.translate(cx, cy + 160);
      ctx.strokeStyle = `rgba(0,200,255,${ev * 0.7})`;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      const ww = 120;
      const tt = tRef.current;
      for (let i = -ww; i <= ww; i += 1) {
        const nx = i / ww;
        const wave =
          Math.sin(nx * Math.PI * 5 + tt * 3) * ev * 12 +
          Math.sin(nx * Math.PI * 11 + tt * 5) * ev * 5;
        if (i === -ww) ctx.moveTo(i, wave);
        else ctx.lineTo(i, wave);
      }
      ctx.stroke();
      ctx.restore();
    };

    const drawGrid = () => {
      ctx.save();
      ctx.strokeStyle = 'rgba(0,100,140,0.07)';
      ctx.lineWidth = 0.5;
      const step = 40;
      for (let x = 0; x < W; x += step) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, H);
        ctx.stroke();
      }
      for (let y = 0; y < H; y += step) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(W, y);
        ctx.stroke();
      }
      ctx.restore();
    };

    const drawScanLine = (e) => {
      const y = cy + Math.sin(tRef.current * 0.3) * 80;
      const grad = ctx.createLinearGradient(0, y - 1, 0, y + 1);
      grad.addColorStop(0, 'rgba(0,200,255,0)');
      grad.addColorStop(0.5, `rgba(0,200,255,${0.04 + e * 0.06})`);
      grad.addColorStop(1, 'rgba(0,200,255,0)');
      ctx.fillStyle = grad;
      ctx.fillRect(0, y - 1, W, 2);
    };

    const render = () => {
      requestRef.current = requestAnimationFrame(render);
      tRef.current += 0.016;
      const e = getEnergy();
      energyRef.current = e;
      ctx.clearRect(0, 0, W, H);
      const overlayMode =
        typeof document !== 'undefined' &&
        document.documentElement.classList.contains('jarvis-overlay');
      /* jarvis_ai_voice_interface.html usa negro sólido; overlay ligeramente translúcido */
      ctx.fillStyle = overlayMode ? 'rgba(0, 0, 0, 0.78)' : '#000000';
      ctx.fillRect(0, 0, W, H);
      drawGrid();
      drawScanLine(e);
      drawRings(e);
      drawParticles(e);
      drawAtom(e);
      drawWaveform(e);
    };

    resize();
    window.addEventListener('resize', resize);
    render();

    return () => {
      window.removeEventListener('resize', resize);
      if (requestRef.current) cancelAnimationFrame(requestRef.current);
    };
  }, []);

  return (
    <div className="app">
      <div id="ui">
        <canvas id="c" ref={canvasRef} />
        <div className="hud">
          <div className="corner tl" />
          <div className="corner tr" />
          <div className="corner bl" />
          <div className="corner br" />

          <div className="label tl">
            {connected ? 'SYS // ONLINE' : 'SYS // OFFLINE'}
          </div>
          <div className="label tr">UI · ELECTRON</div>
          <div className="label bl">{freqLabel}</div>
          <div className="label br">{clockStr}</div>

          <div className="center-label">{statusLabels[status] || 'EN ESPERA'}</div>
          <div className="status-bar">
            <span className="tick" />
            <span className="tick" />
            <span className="tick" />
          </div>
          <div className="status-caption">{message}</div>
          <div className="walkie-btn-wrapper">
            <button className="walkie-btn" id="walkieBtn"
              onMouseDown={handleWalkieStart}
              onMouseUp={handleWalkieStop}
              onMouseLeave={handleWalkieStop}
              onTouchStart={(e) => { e.preventDefault(); handleWalkieStart(e); }}
              onTouchEnd={(e) => { e.preventDefault(); handleWalkieStop(e); }}
              onTouchCancel={(e) => { e.preventDefault(); handleWalkieStop(e); }}
            >
              PULSAR<br />PARA<br />HABLAR
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function handleWalkieStart(e) {
  const btn = document.getElementById('walkieBtn');
  if (btn) {
    btn.classList.add('pressed', 'pulse');
    btn.innerHTML = 'HABLANDO<br>···';
  }
  document.querySelector('.center-label').textContent = 'WALKIE-TALKIE';
  document.querySelector('.status-caption').textContent = 'Mantén presionado para hablar. Suelta para terminar.';
  socket.emit('walkie_talkie_start');
}

function handleWalkieStop(e) {
  const btn = document.getElementById('walkieBtn');
  if (btn) {
    btn.classList.remove('pressed', 'pulse');
    btn.innerHTML = 'PULSAR<br>PARA<br>HABLAR';
  }
  socket.emit('walkie_talkie_stop');
}

export default App;
