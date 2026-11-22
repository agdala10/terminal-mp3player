/* Terminal Mp3 Player — interacciones y partículas reactivas
   Power by Agdala 2026 */
(() => {
  'use strict';

  /* ---------- Menú móvil ---------- */
  const menuBtn = document.getElementById('menuBtn');
  const nav = document.querySelector('.nav');
  menuBtn?.addEventListener('click', () => nav.classList.toggle('open'));
  nav?.querySelectorAll('a').forEach(a => a.addEventListener('click', () => nav.classList.remove('open')));

  /* ---------- Reveal al hacer scroll ---------- */
  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('visible'); revealObserver.unobserve(e.target); } });
  }, { threshold: 0.12 });
  document.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el));

  /* ---------- Galería ---------- */
  const shots = [
    ['1.png', 'Interfaz completa: reproductor, ecualizador y playlist'],
    ['2.png', 'LCD verde con reloj y osciloscopo'],
    ['4.png', 'Ecualizador con faders multicolor'],
    ['5.png', 'Playlist numerada con duraciones'],
    ['6.png', 'Botones de transporte y volumen'],
    ['8.png', 'Menú de presets: ROCK, HIP-HOP, METAL...'],
    ['9.png', 'Agregando una URL de YouTube Music'],
    ['10.png', 'Icono ↓ para descargar la canción'],
    ['11.png', 'Ventana de créditos y licencia']
  ];
  const gallery = document.getElementById('gallery');
  shots.forEach(([file, caption], i) => {
    const fig = document.createElement('figure');
    fig.innerHTML = `<img src="assets/img/${file}" alt="${caption}" loading="lazy"><figcaption>${String(i + 1).padStart(2, '0')} · ${caption}</figcaption>`;
    fig.addEventListener('click', () => openLightbox(file, caption));
    gallery.appendChild(fig);
  });

  const lightbox = document.getElementById('lightbox');
  const lbImg = document.getElementById('lbImg');
  const lbCaption = document.getElementById('lbCaption');
  function openLightbox(file, caption) {
    lbImg.src = `assets/img/${file}`;
    lbImg.alt = caption;
    lbCaption.textContent = caption;
    lightbox.classList.add('open');
    lightbox.setAttribute('aria-hidden', 'false');
  }
  function closeLightbox() {
    lightbox.classList.remove('open');
    lightbox.setAttribute('aria-hidden', 'true');
  }
  document.getElementById('lbClose').addEventListener('click', closeLightbox);
  lightbox.addEventListener('click', e => { if (e.target === lightbox) closeLightbox(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeLightbox(); });

  /* ---------- Preview de faders ---------- */
  const faderBox = document.getElementById('faderPreview');
  const faders = [];
  for (let i = 0; i < 11; i++) {
    const bar = document.createElement('i');
    bar.style.height = `${25 + Math.random() * 60}%`;
    faderBox.appendChild(bar);
    faders.push(bar);
  }
  setInterval(() => {
    faders.forEach((bar, i) => {
      bar.style.height = `${20 + Math.abs(Math.sin(Date.now() / 900 + i * 0.7)) * 70}%`;
    });
  }, 120);

  /* ---------- Audio + partículas reactivas ---------- */
  const audio = document.getElementById('themeAudio');
  const toggle = document.getElementById('audioToggle');
  const wave = document.querySelector('.audio-wave');
  let audioCtx = null, analyser = null, data = null, playing = false;

  function setupAudio() {
    if (audioCtx) return;
    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const src = audioCtx.createMediaElementSource(audio);
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.78;
      src.connect(analyser);
      analyser.connect(audioCtx.destination);
      data = new Uint8Array(analyser.frequencyBinCount);
    } catch (err) {
      console.warn('Audio no disponible:', err);
    }
  }

  async function startAudio() {
    setupAudio();
    if (audioCtx?.state === 'suspended') await audioCtx.resume();
    try { await audio.play(); } catch (err) { console.warn('Autoplay bloqueado:', err); }
  }

  toggle?.addEventListener('click', async () => {
    setupAudio();
    if (audio.paused) {
      await startAudio();
    } else {
      audio.pause();
    }
  });

  audio.addEventListener('play', () => {
    playing = true;
    toggle.textContent = '❚❚';
    wave?.classList.add('playing');
  });
  audio.addEventListener('pause', () => {
    playing = false;
    toggle.textContent = '▶';
    wave?.classList.remove('playing');
  });

  // Intenta cargar y reproducir al abrir; si el navegador lo bloquea,
  // arranca con el primer clic del usuario.
  window.addEventListener('load', () => {
    setupAudio();
    audio.volume = 0.55;
    audio.play().catch(() => {});
  });
  document.addEventListener('pointerdown', () => {
    if (!playing && audio.paused) startAudio();
  }, { once: true });

  /* ---------- Canvas de partículas ---------- */
  const canvas = document.getElementById('particles');
  const ctx = canvas.getContext('2d');
  let w = 0, h = 0, particles = [];
  const COLORS = ['#46e0ff', '#7c8bff', '#ff5fd2', '#4dff9f', '#ffd166'];

  function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  }
  window.addEventListener('resize', resize);
  resize();

  for (let i = 0; i < 110; i++) {
    particles.push({
      x: Math.random() * w,
      y: Math.random() * h,
      r: Math.random() * 2.2 + 0.6,
      vx: (Math.random() - 0.5) * 0.35,
      vy: (Math.random() - 0.5) * 0.35,
      c: COLORS[i % COLORS.length],
      a: Math.random() * 0.6 + 0.2
    });
  }

  function levels() {
    if (!playing || !analyser || !data) return { bass: 0, mid: 0, high: 0 };
    analyser.getByteFrequencyData(data);
    const avg = (a, b) => {
      let s = 0, n = 0;
      for (let i = a; i < b && i < data.length; i++) { s += data[i]; n++; }
      return n ? s / n / 255 : 0;
    };
    return { bass: avg(0, 8), mid: avg(8, 40), high: avg(40, 90) };
  }

  function draw() {
    ctx.clearRect(0, 0, w, h);
    const lv = levels();
    const boost = 1 + lv.bass * 5 + lv.mid * 2;
    particles.forEach(p => {
      p.x += p.vx * boost;
      p.y += p.vy * boost;
      if (p.x < -20) p.x = w + 20;
      if (p.x > w + 20) p.x = -20;
      if (p.y < -20) p.y = h + 20;
      if (p.y > h + 20) p.y = -20;
      const radius = p.r * (1 + lv.high * 2.5);
      ctx.beginPath();
      ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
      ctx.fillStyle = p.c;
      ctx.globalAlpha = Math.min(1, p.a + lv.mid * 0.5);
      ctx.shadowBlur = 12 + lv.bass * 30;
      ctx.shadowColor = p.c;
      ctx.fill();
    });
    ctx.globalAlpha = 1;
    ctx.shadowBlur = 0;
    requestAnimationFrame(draw);
  }
  draw();
})();
