'use strict';

// ── Utilitários ───────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

/** Escapa caracteres HTML — previne XSS em interpolações de innerHTML */
const _esc = s => String(s)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

// ── Captura global de erros JS (PyWebView não tem console visível) ────────────
window.addEventListener('error', e => {
  try {
    const where = e.filename ? e.filename.split('/').pop() + ':' + e.lineno : '?';
    appendLog(`Erro JS: ${e.message} [${where}]`);
  } catch (_) {}
});
window.addEventListener('unhandledrejection', e => {
  try { appendLog(`Erro assíncrono: ${e.reason}`); } catch (_) {}
});

// ── Estado ───────────────────────────────────────────────────────────────────
let executando       = false;
let autenticado      = false;
let _updUrlDownload  = null;   // URL direta do asset público (sem asset_id)
let _updVersao       = null;
let logEntries       = [];
let currentFilter    = 'all';
let logIdCounter     = 0;
let sidebarCollapsed = false;
let darkMode         = false;
let activeEgg        = null;
let currentAccent    = 'amber';

// ── Acento de cor ─────────────────────────────────────────────────────────────

/** Aplica acento visualmente (CSS + botões) sem salvar no backend. */
function _aplicarAccentVisual(accent) {
  if (accent === 'indigo') {
    document.documentElement.removeAttribute('data-accent');
  } else {
    document.documentElement.setAttribute('data-accent', accent);
  }
  document.querySelectorAll('.btn-accent-opt').forEach(btn => {
    const active = btn.dataset.accent === accent;
    btn.style.borderColor = active ? 'currentColor' : 'transparent';
    btn.style.fontWeight  = active ? '700' : '600';
    btn.style.opacity     = active ? '1' : '0.65';
  });
}

/** Aplica acento e persiste no backend (usado apenas ao mudar via UI). */
function setAccent(accent) {
  try {
    currentAccent = accent;
    _aplicarAccentVisual(accent);
    setTimeout(() => pywebview.api.set_accent && pywebview.api.set_accent(accent), 0);
  } catch (e) {
    appendLog('Erro ao mudar acento: ' + e.message);
  }
}

// ── Easter Egg ────────────────────────────────────────────────────────────────
let _eggClicks = 0;
let _eggTimer  = null;

function _initEasterEgg() {
  const el = $('user-card');
  if (!el) return;
  el.addEventListener('click', _handleEggClick);
  el.addEventListener('keydown', e => { if (e.key === 'Enter') _handleEggClick(); });
}

function _handleEggClick() {
  const nome = $('user-nome').textContent.trim().toUpperCase();
  _eggClicks++;
  clearTimeout(_eggTimer);
  _eggTimer = setTimeout(() => { _eggClicks = 0; }, 1200);
  if (_eggClicks >= 5) {
    _eggClicks = 0;
    clearTimeout(_eggTimer);
    if (nome === 'JOLIVEI') _ativarEgg('pink');
    else if (nome === 'MSILVA7') _ativarEgg('purple');
  }
}

function _ativarEgg(egg) {
  document.documentElement.setAttribute('data-egg', egg);
  activeEgg = egg;
  const isDark = egg === 'purple';
  darkMode = isDark;
  document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  _atualizarIconeTema();
  $('btn-theme').classList.add('hidden');
  document.querySelectorAll('.btn-accent-opt').forEach(b => b.style.display = 'none');
  setTimeout(() => pywebview.api.set_tema(egg), 0);
  appendLog(egg === 'pink' ? '🌸 Modo especial ativado' : '✨ Modo especial ativado');
}

function _resetarEgg() {
  document.documentElement.removeAttribute('data-egg');
  activeEgg = null;
  darkMode  = false;
  document.documentElement.setAttribute('data-theme', 'light');
  _atualizarIconeTema();
  $('btn-theme').classList.remove('hidden');
  document.querySelectorAll('.btn-accent-opt').forEach(b => b.style.display = '');
  setAccent(currentAccent);
}

// ── Tema claro / escuro ───────────────────────────────────────────────────────
function _atualizarIconeTema() {
  $('icon-moon').classList.toggle('hidden', darkMode);
  $('icon-sun').classList.toggle('hidden', !darkMode);
  $('btn-theme').title = darkMode ? 'Tema claro' : 'Tema escuro';
  $('btn-theme').setAttribute('aria-label', darkMode ? 'Mudar para tema claro' : 'Mudar para tema escuro');
}

function toggleTema() {
  try {
    if (activeEgg) return;
    darkMode = !darkMode;
    document.documentElement.setAttribute('data-theme', darkMode ? 'dark' : 'light');
    _atualizarIconeTema();
    setTimeout(() => pywebview.api.set_tema(darkMode ? 'dark' : 'light'), 0);
  } catch (e) {
    appendLog('Erro ao mudar tema: ' + e.message);
  }
}

// ── Sidebar ───────────────────────────────────────────────────────────────────
function toggleSidebar() {
  sidebarCollapsed = !sidebarCollapsed;
  $('sidebar').classList.toggle('collapsed', sidebarCollapsed);
  $('icon-chev-left').classList.toggle('hidden', sidebarCollapsed);
  $('icon-chev-right').classList.toggle('hidden', !sidebarCollapsed);
  $('btn-collapse').title = sidebarCollapsed ? 'Expandir sidebar' : 'Recolher sidebar';
  $('btn-collapse').setAttribute('aria-label', sidebarCollapsed ? 'Expandir sidebar' : 'Recolher sidebar');
}

// ── Navegação ─────────────────────────────────────────────────────────────────
function setNav(id) {
  document.querySelectorAll('.nav-item').forEach(btn => {
    const active = btn.dataset.nav === id;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-current', active ? 'page' : 'false');
  });
  $('section-extract').classList.toggle('hidden', id !== 'extract');
  $('section-log').classList.toggle('hidden',     id !== 'log');
  $('section-history').classList.toggle('hidden', id !== 'history');
}

// ── Log ───────────────────────────────────────────────────────────────────────
function getTime() {
  return new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

let stepperStep    = 0;
let _extractStart  = null;
let _extractParams = null;

function appendLog(msg) {
  let level = 'info';
  if (/erro|falha/i.test(msg))                                         level = 'error';
  else if (/aviso|duplicata|ignorad|cancelad/i.test(msg))              level = 'warning';
  else if (/OK|sucesso|autenticado|concluido|registros/i.test(msg))    level = 'ok';

  logEntries.push({ id: ++logIdCounter, ts: getTime(), level, msg });

  if (executando && stepperStep < STEPS.length - 1) {
    stepperStep++;
    renderStepper(stepperStep, false);
    setProgress((stepperStep + 0.5) / STEPS.length);
  }

  renderLog();
}

function renderLog() {
  const body     = $('log-body');
  const empty    = $('log-empty');
  const count    = $('log-count');
  const filtered = currentFilter === 'all'
    ? logEntries
    : logEntries.filter(e => e.level === currentFilter);

  count.textContent = `(${filtered.length})`;
  body.querySelectorAll('.log-entry').forEach(e => e.remove());

  if (filtered.length === 0) { empty.style.display = 'flex'; return; }
  empty.style.display = 'none';

  filtered.forEach(entry => {
    const div = document.createElement('div');
    div.className = `log-entry ${entry.level}`;
    div.innerHTML =
      `<span class="log-time">${_esc(entry.ts)}</span>` +
      `<span class="log-badge">${_esc(entry.level.toUpperCase())}</span>` +
      `<span class="log-msg">${_esc(entry.msg)}</span>`;
    body.appendChild(div);
  });
  body.scrollTop = body.scrollHeight;
}

function copyLog() {
  const texto = logEntries.map(e => `[${e.ts}] [${e.level.toUpperCase()}] ${e.msg}`).join('\n');
  if (!texto) return;
  navigator.clipboard.writeText(texto).then(() => {
    const btn = $('btn-log-copy');
    const orig = btn.title;
    btn.title = 'Copiado!';
    btn.style.color = 'var(--primary)';
    setTimeout(() => { btn.title = orig; btn.style.color = ''; }, 1500);
  }).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = texto;
    ta.style.cssText = 'position:fixed;opacity:0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  });
}

function clearLog() {
  logEntries   = [];
  logIdCounter = 0;
  renderLog();
}

function setLogFilter(filter, btn) {
  currentFilter = filter;
  document.querySelectorAll('.log-ftab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  renderLog();
}

// ── Status ────────────────────────────────────────────────────────────────────
function setStatus(msg, tipo = 'idle') {
  const dot = $('status-dot');
  const txt = $('status-text');
  dot.className    = 'status-dot';
  txt.className    = 'status-txt';
  dot.style.background = '';
  if      (tipo === 'running') { dot.classList.add('spin-dot'); txt.classList.add('running'); }
  else if (tipo === 'ok')      { dot.style.background = 'var(--success)'; txt.classList.add('ok'); }
  else if (tipo === 'erro')    { dot.style.background = 'var(--err)'; txt.classList.add('err'); }
  else                         { dot.classList.add('pulse'); }
  txt.textContent = msg;
}

function setProgress(valor) {
  const el = $('progress-bar');
  if (el) el.style.width = `${Math.round(valor * 100)}%`;
}

// ── Stepper de progresso ──────────────────────────────────────────────────────
const STEPS = ['Conectando', 'Autenticando', 'Consultando NF-e', 'Processando', 'Exportando Excel'];

function renderStepper(currentStep, done) {
  const container = $('stepper');
  container.innerHTML = '';

  STEPS.forEach((label, i) => {
    const isDone = i < currentStep || done;
    const isCurr = i === currentStep && !done;

    const item = document.createElement('div');
    item.className = `step-item${isDone ? ' done' : ''}${isCurr ? ' current' : ''}`;
    item.setAttribute('role', 'listitem');

    const circle = document.createElement('div');
    circle.className = 'step-circle';
    circle.setAttribute('aria-label', isDone ? 'Concluído' : isCurr ? 'Em andamento' : 'Pendente');

    if (isDone) {
      circle.innerHTML = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
    } else if (isCurr) {
      circle.innerHTML = '<svg class="spin-anim" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>';
    } else {
      circle.textContent = i + 1;
    }

    const lbl = document.createElement('div');
    lbl.className   = 'step-label';
    lbl.textContent = label;

    item.appendChild(circle);
    item.appendChild(lbl);
    container.appendChild(item);
  });

  const pct = done ? 100 : Math.round(((currentStep + 0.5) / STEPS.length) * 100);
  $('step-progress-bar').style.width = `${pct}%`;
}

function mostrarStepper(mostrar) {
  $('stepper-card').classList.toggle('visible', mostrar);
}

function mostrarErroExtract(msg) {
  const box = $('extract-error-box');
  if (msg) {
    $('extract-error-msg').textContent = msg;
    box.classList.remove('hidden');
  } else {
    box.classList.add('hidden');
  }
}

// ── Histórico ─────────────────────────────────────────────────────────────────
let historicoEntries = [];

function addHistorico(entry) {
  historicoEntries.unshift(entry);
  renderHistorico();
}

function renderHistorico() {
  const el = $('history-content');
  if (historicoEntries.length === 0) {
    el.innerHTML = '<div style="color:var(--txt-faint);font-size:12px;text-align:center;padding:40px 0">Nenhuma extração registrada nesta sessão.</div>';
    return;
  }

  // Estrutura da tabela via innerHTML (strings estáticas, sem input do usuário)
  el.innerHTML = `
    <table style="width:100%;border-collapse:collapse">
      <thead>
        <tr style="border-bottom:1px solid var(--border)">
          ${['Data/Hora','Período','Registros','Duração','Status'].map(h =>
            `<th style="text-align:left;padding:6px 10px;font-size:10px;font-weight:700;color:var(--txt-faint);text-transform:uppercase;letter-spacing:.08em">${h}</th>`
          ).join('')}
        </tr>
      </thead>
      <tbody id="history-tbody"></tbody>
    </table>`;

  // Linhas de dados preenchidas com textContent (seguro contra XSS)
  const tbody = document.getElementById('history-tbody');
  historicoEntries.forEach(r => {
    const tr = document.createElement('tr');
    tr.style.borderBottom = '1px solid rgba(0,0,0,0.04)';

    const cellStyle = 'padding:10px;font-size:12px;';
    const cells = [
      { text: r.dataHora,  style: cellStyle + 'color:var(--txt)' },
      { text: r.periodo,   style: cellStyle + 'color:var(--txt-dim)' },
      { text: Number(r.registros).toLocaleString('pt-BR'), style: cellStyle + 'font-weight:600;color:var(--txt)' },
      { text: r.duracao,   style: cellStyle + 'color:var(--txt-dim)' },
    ];

    cells.forEach(({ text, style }) => {
      const td = document.createElement('td');
      td.style.cssText = style;
      td.textContent   = text;
      tr.appendChild(td);
    });

    // Coluna de status (conteúdo estático, sem input do usuário)
    const tdStatus = document.createElement('td');
    tdStatus.style.padding = '10px';
    const span = document.createElement('span');
    span.style.cssText = `display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:20px;font-size:10px;font-weight:600;background:${r.ok ? 'rgba(16,185,129,.1)' : 'rgba(239,68,68,.09)'};color:${r.ok ? 'var(--success)' : 'var(--err)'}`;
    span.textContent = r.ok ? '✓ Sucesso' : '✗ Erro';
    tdStatus.appendChild(span);
    tr.appendChild(tdStatus);

    tbody.appendChild(tr);
  });
}

// ── Executar ──────────────────────────────────────────────────────────────────
function setExecutando(val) {
  executando = val;
  $('btn-run').disabled = val;
  $('btn-cancel').classList.toggle('hidden', !val);
  $('btn-run-text').textContent = val ? 'EXECUTANDO...' : 'EXECUTAR';
  $('icon-play').classList.toggle('hidden', val);
  $('icon-spinner').classList.toggle('hidden', !val);
}

async function executar() {
  if (executando) return;
  if (!autenticado) { abrirModal(); return; }
  if (!validarData($('data-ini')) || !validarData($('data-fim'))) {
    setStatus('Formato de data inválido (DD/MM/AAAA)', 'erro');
    return;
  }
  setExecutando(true);
  setProgress(0.05);
  setStatus('Iniciando…', 'running');
  mostrarStepper(true);
  mostrarErroExtract(null);
  stepperStep    = 0;
  _extractStart  = Date.now();
  _extractParams = { dataIni: $('data-ini').value, dataFim: $('data-fim').value };
  renderStepper(0, false);

  const params = {
    data_ini:        $('data-ini').value,
    data_fim:        $('data-fim').value,
    estab_de:        $('estab-de').value,
    estab_ate:       $('estab-ate').value,
    serie_de:        $('serie-de').value,
    serie_ate:       $('serie-ate').value,
    nf_de:           $('nf-de').value,
    nf_ate:          $('nf-ate').value,
    sit_confirmadas: $('sit-confirmadas').checked,
    sit_canceladas:  $('sit-canceladas').checked,
    abrir_arquivo:   $('opt-abrir').checked,
  };
  const res = await pywebview.api.executar(params);
  if (!res.ok) {
    setExecutando(false);
    setStatus(res.erro, 'erro');
    mostrarErroExtract(res.erro);
    renderStepper(-1, false);
  }
}

async function cancelarExtracao() {
  if (!executando) return;
  // Sinaliza visualmente — o estado real é atualizado via onExtracaoCancelada() do backend
  setStatus('Cancelando…', 'atencao');
  appendLog('Cancelamento solicitado pelo usuário');
  await pywebview.api.cancelar_extracao();
}

// ── Callbacks do backend ──────────────────────────────────────────────────────

/** Chamado pelo backend ao concluir extração com sucesso ou erro. */
function onExtracao({ ok, n, segundos, arquivo, abrir, erro }) {
  setExecutando(false);
  setProgress(1);
  stepperStep = 0;
  const durSec   = segundos || ((Date.now() - (_extractStart || Date.now())) / 1000).toFixed(1);
  const agora    = new Date();
  const p        = d => String(d).padStart(2, '0');
  const dataHora = `${p(agora.getDate())}/${p(agora.getMonth() + 1)}/${agora.getFullYear()} ${p(agora.getHours())}:${p(agora.getMinutes())}`;
  const periodo  = _extractParams ? `${_extractParams.dataIni} – ${_extractParams.dataFim}` : '-';

  if (ok) {
    renderStepper(STEPS.length, true);
    setStatus(`Concluído — ${n} registros exportados`, 'ok');
    appendLog(`Extração concluída: ${n} registros exportados em ${durSec}s`);
    addHistorico({ dataHora, periodo, registros: n, duracao: `${durSec}s`, ok: true });
    $('btn-limpar').disabled = false;
    if (abrir) pywebview.api.abrir_arquivo();
  } else {
    mostrarErroExtract(erro);
    setStatus('Falha na extração', 'erro');
    appendLog(`Erro na extração: ${erro}`);
    addHistorico({ dataHora, periodo, registros: 0, duracao: `${durSec}s`, ok: false });
  }
}

/** Chamado pelo backend quando a extração foi cancelada intencionalmente. */
function onExtracaoCancelada() {
  // setExecutando(false) e setProgress(0) já são chamados pelo finally do backend
  renderStepper(-1, false);
  appendLog('Extração cancelada');
  const agora    = new Date();
  const p        = d => String(d).padStart(2, '0');
  const dataHora = `${p(agora.getDate())}/${p(agora.getMonth() + 1)}/${agora.getFullYear()} ${p(agora.getHours())}:${p(agora.getMinutes())}`;
  const periodo  = _extractParams ? `${_extractParams.dataIni} – ${_extractParams.dataFim}` : '-';
  const durSec   = (Date.now() - (_extractStart || Date.now())) / 1000;
  addHistorico({ dataHora, periodo, registros: 0, duracao: `${durSec.toFixed(1)}s`, ok: false });
}

function onStepUpdate(step) {
  renderStepper(step, false);
  setProgress((step + 0.5) / STEPS.length);
  if (step < STEPS.length) {
    setStatus(STEPS[step], 'running');
    appendLog(STEPS[step]);
  }
}

// ── Validação de datas ────────────────────────────────────────────────────────
function validarData(el) {
  const val = el.value;
  const ok  = /^\d{2}\/\d{2}\/\d{4}$/.test(val) && !isNaN(new Date(val.split('/').reverse().join('-')));
  el.classList.toggle('invalid', !ok);
  return ok;
}

function setupDateInput(id) {
  const el = $(id);
  if (!el) return;
  el.addEventListener('input', () => {
    let v = el.value.replace(/\D/g, '');
    if (v.length > 2) v = v.slice(0, 2) + '/' + v.slice(2);
    if (v.length > 5) v = v.slice(0, 5) + '/' + v.slice(5);
    el.value = v.slice(0, 10);
    if (el.value.length === 10) validarData(el);
    else el.classList.remove('invalid');
  });
}

// ── Modal de login ────────────────────────────────────────────────────────────
function abrirModal() {
  $('overlay').classList.add('visible');
  $('auth-error').classList.remove('visible');
  try { $('input-usuario').focus(); } catch (_) {}
}

function fecharModal() {
  $('overlay').classList.remove('visible');
}

function toggleSenha() {
  const inp = $('input-senha');
  inp.type = inp.type === 'password' ? 'text' : 'password';
}

async function fazerLogin() {
  const usuario = $('input-usuario').value.trim();
  const senha   = $('input-senha').value.trim();
  const salvar  = $('check-salvar').checked;

  if (!usuario || !senha) {
    mostrarErroAuth('Preencha usuário e senha.');
    return;
  }

  $('btn-entrar').disabled = true;
  $('btn-entrar-text').textContent = 'Autenticando…';
  $('btn-entrar-spin').classList.remove('hidden');
  $('auth-error').classList.remove('visible');

  const res = await pywebview.api.fazer_login(usuario, senha, salvar);

  $('btn-entrar').disabled = false;
  $('btn-entrar-text').textContent = 'Entrar';
  $('btn-entrar-spin').classList.add('hidden');

  if (res.ok) {
    autenticado = true;
    const iniciais = usuario.substring(0, 2).toUpperCase();
    $('user-avatar').textContent = iniciais;
    $('user-nome').textContent   = usuario;
    $('user-card').classList.remove('hidden');
    $('btn-usuario-login').classList.add('hidden');
    $('btn-logout').classList.remove('hidden');
    $('btn-limpar').disabled = false;
    _initEasterEgg();
    fecharModal();
    setStatus('Autenticado com sucesso', 'ok');
    appendLog(`Login: ${usuario}`);
  } else {
    mostrarErroAuth(res.erro || 'Credenciais inválidas. Verifique e tente novamente.');
  }
}

function mostrarErroAuth(msg) {
  $('auth-error-msg').textContent = msg;
  $('auth-error').classList.add('visible');
  setStatus(msg, 'erro');
}

async function fazerLogout() {
  if (!confirm('Deseja sair e limpar as credenciais salvas?')) return;
  await pywebview.api.fazer_logout();
  autenticado = false;
  _resetarEgg();
  clearLog();
  $('user-card').classList.add('hidden');
  $('btn-usuario-login').classList.remove('hidden');
  $('btn-logout').classList.add('hidden');
  $('btn-limpar').disabled = true;
  mostrarStepper(false);
  setStatus('Pronto para extrair', 'idle');
  abrirModal();
}

// ── Arquivo ───────────────────────────────────────────────────────────────────
async function escolherArquivo() {
  const res = await pywebview.api.escolher_arquivo();
  if (res.ok) { $('file-path').textContent = res.arquivo; appendLog('Arquivo: ' + res.arquivo); }
}

async function limparArquivo() {
  if (!autenticado) return;
  if (!confirm('Remover o arquivo Excel acumulativo?')) return;
  const res = await pywebview.api.limpar_arquivo();
  if (res.ok) {
    setStatus('Arquivo removido', 'ok');
    appendLog('Arquivo removido');
    $('btn-limpar').disabled = true;
    mostrarStepper(false);
    setProgress(0);
    setStatus('Pronto para extrair', 'idle');
  } else {
    setStatus(res.erro, 'erro');
  }
}

// ── Config Dropdown ───────────────────────────────────────────────────────────
function initConfigDropdown() {
  const btn = $('btn-config');
  const dd  = $('config-dropdown');
  if (!btn || !dd) return;
  const abrir  = () => { dd.classList.add('open');    btn.setAttribute('aria-expanded', 'true'); };
  const fechar = () => { dd.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); };
  btn.addEventListener('click', e => { e.stopPropagation(); dd.classList.contains('open') ? fechar() : abrir(); });
  document.addEventListener('click',   e => { if (!dd.contains(e.target) && e.target !== btn) fechar(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') fechar(); });
}

// ── Auto-update ───────────────────────────────────────────────────────────────
function _updMostrarEstado(id) {
  ['upd-disponivel', 'upd-baixando', 'upd-pronto', 'upd-erro'].forEach(s => {
    const el = $(s);
    if (el) el.classList.toggle('hidden', s !== id);
  });
}

function _updMostrarBanner(mostrar) {
  const b = $('update-banner');
  if (b) b.classList.toggle('visible', mostrar);
}

function onAtualizacaoDisponivel(versao, urlDownload, tamanho, notas) {
  _updUrlDownload = urlDownload;
  _updVersao      = versao;
  const mb  = (tamanho / 1048576).toFixed(1);
  const lbl = $('upd-versao-label');
  const tam = $('upd-tamanho-label');
  if (lbl) lbl.textContent = `Nova versão ${versao} disponível`;
  if (tam) tam.textContent = `${mb} MB`;
  _updMostrarEstado('upd-disponivel');
  _updMostrarBanner(true);
  appendLog('Atualização disponível: v' + versao);
}

function onDownloadProgresso(pct) {
  const bar = $('upd-progress-bar');
  const lbl = $('upd-pct-label');
  if (bar) bar.style.width = `${Math.round(pct * 100)}%`;
  if (lbl) lbl.textContent = `${Math.round(pct * 100)}%`;
}

function onDownloadConcluido() {
  _updMostrarEstado('upd-pronto');
  appendLog('Download concluído — pronto para instalar');
}

function onDownloadErro(msg) {
  const lbl = $('upd-erro-label');
  if (lbl) lbl.textContent = msg;
  _updMostrarEstado('upd-erro');
  appendLog('Erro no download: ' + msg);
}

async function iniciarDownloadUpdate() {
  if (!_updUrlDownload || !_updVersao) return;
  _updMostrarEstado('upd-baixando');
  appendLog('Iniciando download da atualização…');
  await pywebview.api.baixar_atualizacao(_updUrlDownload, _updVersao);
}

async function fecharEInstalar() {
  appendLog('Fechando app e iniciando instalação…');
  await pywebview.api.fechar_e_instalar();
}

function ignorarUpdate() {
  _updMostrarBanner(false);
  appendLog('Atualização ignorada');
}

// ── Init UI (DOMContentLoaded) — apenas configuração, sem aplicar tema ────────
window.addEventListener('DOMContentLoaded', () => {

  initConfigDropdown();
  setupDateInput('data-ini');
  setupDateInput('data-fim');

  // Datas padrão: hoje
  const hoje = new Date();
  const fmt  = d => String(d).padStart(2, '0');
  const hojeStr = `${fmt(hoje.getDate())}/${fmt(hoje.getMonth() + 1)}/${hoje.getFullYear()}`;
  $('data-ini').value = hojeStr;
  $('data-fim').value = hojeStr;

  // Login / Logout
  $('btn-usuario-login').addEventListener('click', abrirModal);
  $('btn-logout').addEventListener('click', fazerLogout);
  $('btn-entrar').addEventListener('click', fazerLogin);
  $('btn-cancelar').addEventListener('click', fecharModal);
  $('btn-toggle-pw').addEventListener('click', toggleSenha);
  $('input-senha').addEventListener('keydown', e => { if (e.key === 'Enter') fazerLogin(); });
  $('input-usuario').addEventListener('keydown', e => { if (e.key === 'Enter') $('input-senha').focus(); });
  $('overlay').addEventListener('click', e => { if (e.target === $('overlay') && autenticado) fecharModal(); });

  // Caps Lock
  $('input-senha').addEventListener('keydown', e => {
    $('caps-aviso').style.display = (e.getModifierState && e.getModifierState('CapsLock')) ? 'block' : 'none';
  });
  $('input-senha').addEventListener('keyup', e => {
    $('caps-aviso').style.display = (e.getModifierState && e.getModifierState('CapsLock')) ? 'block' : 'none';
  });

  // Tema
  $('btn-theme').addEventListener('click', toggleTema);

  // Sidebar
  $('btn-collapse').addEventListener('click', toggleSidebar);

  // Navegação
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => setNav(btn.dataset.nav));
  });

  // Executar / Limpar
  $('btn-run').addEventListener('click', executar);
  $('btn-cancel').addEventListener('click', cancelarExtracao);
  $('btn-limpar').addEventListener('click', limparArquivo);
  $('btn-retry-extract').addEventListener('click', executar);

  // Log
  $('btn-log-copy').addEventListener('click', copyLog);
  $('btn-log-clear').addEventListener('click', clearLog);
  document.querySelectorAll('.log-ftab').forEach(tab => {
    tab.addEventListener('click', () => setLogFilter(tab.dataset.filter, tab));
  });

  // Seletor de acento (salva no backend via setAccent)
  document.querySelectorAll('.btn-accent-opt').forEach(btn => {
    btn.addEventListener('click', () => setAccent(btn.dataset.accent));
  });

  // Arquivo
  $('btn-escolher').addEventListener('click', escolherArquivo);

  // Update banner
  const btnBaixar   = $('btn-upd-baixar');
  const btnIgnorar  = $('btn-upd-ignorar');
  const btnInstalar = $('btn-upd-instalar');
  const btnRetry    = $('btn-upd-retry');
  if (btnBaixar)   btnBaixar.addEventListener('click', iniciarDownloadUpdate);
  if (btnIgnorar)  btnIgnorar.addEventListener('click', ignorarUpdate);
  if (btnInstalar) btnInstalar.addEventListener('click', fecharEInstalar);
  if (btnRetry)    btnRetry.addEventListener('click', iniciarDownloadUpdate);
});

// ── Init API (pywebviewready) — aplica tema+acento em lote, sem flash ─────────
window.addEventListener('pywebviewready', async () => {
  const estado = await pywebview.api.get_estado_inicial();

  // ── Aplicar tema e acento em lote (antes de qualquer outro repaint) ──────
  // O HTML já carrega com data-theme="light" data-accent="amber" — esta etapa
  // confirma ou corrige para o tema real salvo pelo usuário, minimizando flash.
  const accent = estado.accent || 'amber';
  const tema   = estado.tema   || 'light';

  if (tema === 'pink' || tema === 'purple') {
    _ativarEgg(tema);
  } else {
    darkMode = tema === 'dark';
    document.documentElement.setAttribute('data-theme', tema);
    _atualizarIconeTema();
    // Aplicar acento sem persistir (já está salvo no backend)
    currentAccent = accent;
    _aplicarAccentVisual(accent);
  }

  // ── Restaurar estado da UI ────────────────────────────────────────────────
  if (estado.arquivo) $('file-path').textContent = estado.arquivo;
  $('input-usuario').value = estado.usuario || estado.usuario_windows || '';

  if (estado.filtros) {
    const f = estado.filtros;
    // data_ini e data_fim NÃO são restauradas — sempre iniciam com hoje
    if (f.estab_de)  $('estab-de').value  = f.estab_de;
    if (f.estab_ate) $('estab-ate').value = f.estab_ate;
    if (f.serie_de)  $('serie-de').value  = f.serie_de;
    if (f.serie_ate) $('serie-ate').value = f.serie_ate;
    if (f.nf_de)     $('nf-de').value     = f.nf_de;
    if (f.nf_ate)    $('nf-ate').value    = f.nf_ate;
    if (f.sit_confirmadas !== undefined) $('sit-confirmadas').checked = f.sit_confirmadas;
    if (f.sit_canceladas  !== undefined) $('sit-canceladas').checked  = f.sit_canceladas;
  }

  if (estado.autenticado) {
    autenticado = true;
    const iniciais = (estado.usuario || '??').substring(0, 2).toUpperCase();
    $('user-avatar').textContent = iniciais;
    $('user-nome').textContent   = estado.usuario;
    $('user-card').classList.remove('hidden');
    $('btn-usuario-login').classList.add('hidden');
    $('btn-logout').classList.remove('hidden');
    $('btn-limpar').disabled = false;
    _initEasterEgg();
  } else {
    $('btn-limpar').disabled = true;
    abrirModal();
  }

  appendLog('Extrator DataSul NF-e iniciado');
  pywebview.api.verificar_atualizacao();
});
