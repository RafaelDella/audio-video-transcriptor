const $ = (id) => document.getElementById(id);
let backend;
let files = [];
let folderPath = '';
let selected = '';
let busy = false;
let currentNumber = 0;
let currentTotal = 0;
let hadError = false;
let wasCancelled = false;
let cancelling = false;
let activityMessage = '';
let waitingText = '';
let waitingSince = 0;
let preparingModel = false;
let modelPreparingSince = 0;
let offlineMode = false;
let cachedModels = {};
let modelNames = {};
let modelDetails = {};
let modelDiskBytes = {};
const results = [];

function formatSize(bytes) {
  return bytes < 1048576 ? `${Math.round(bytes / 1024)} KB` : `${(bytes / 1048576).toFixed(1)} MB`;
}
function addLog(message) {
  const item = document.createElement('div');
  item.textContent = message;
  $('log').append(item);
  $('log').scrollTop = $('log').scrollHeight;
}
function setProgress(id, label, value) {
  $(id).style.width = `${Math.max(0, Math.min(100, value))}%`;
  $(label).textContent = `${Math.round(value)}%`;
}
function showWaiting(message) {
  waitingText = message;
  waitingSince = Date.now();
  updateWaiting();
}
function updateWaiting() {
  if (preparingModel && modelPreparingSince) {
    const seconds = Math.floor((Date.now() - modelPreparingSince) / 1000);
    $('model-status').textContent = `Baixando modelo para este computador... (${seconds}s)`;
  }
  if (!waitingText) return;
  const seconds = Math.floor((Date.now() - waitingSince) / 1000);
  const text = seconds >= 5 ? `${waitingText} (${seconds}s)` : waitingText;
  $('work-status').textContent = text;
  $('action-hint').textContent = text;
}
setInterval(updateWaiting, 1000);
function renderFiles() {
  const hasLink = files.some(file => file.kind === 'link');
  $('drop-zone').classList.toggle('hidden', files.length > 0);
  $('files-ready').classList.toggle('hidden', files.length === 0);
  $('clear-files').classList.toggle('hidden', files.length === 0);
  $('file-subtitle').textContent = files.length ? `${files.length} fonte${files.length > 1 ? 's' : ''} selecionada${files.length > 1 ? 's' : ''}` : 'Arquivos do computador ou links de áudio e vídeo.';
  $('file-list').replaceChildren();
  files.forEach(file => {
    const row = document.createElement('div');
    row.className = `file-row${file.kind === 'link' ? ' link' : ''}${file.path === selected ? ' selected' : ''}`;
    row.setAttribute('role', 'listitem');
    const icon = document.createElement('span');
    icon.className = 'file-icon';
    icon.innerHTML = file.kind === 'link' ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.1 0l2-2A5 5 0 0 0 12 4l-1 1M14 11a5 5 0 0 0-7.1 0l-2 2A5 5 0 0 0 12 20l1-1"/></svg>' : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3h6l5 5v13H5V3h3zM14 3v5h5M8 13h8M8 17h6"/></svg>';
    const info = document.createElement('span');
    info.className = 'file-info';
    const name = document.createElement('b'); name.textContent = file.name;
    const size = document.createElement('small'); size.textContent = file.kind === 'link' ? file.origin : formatSize(file.size);
    if (file.kind === 'link') row.title = file.path;
    info.append(name, size);
    const remove = document.createElement('button');
    remove.type = 'button'; remove.className = 'remove'; remove.textContent = '×';
    remove.setAttribute('aria-label', `Remover ${file.name}`);
    remove.disabled = busy;
    remove.addEventListener('click', () => backend.remove_file(file.path));
    row.append(icon, info, remove);
    row.addEventListener('click', (event) => { if (event.target !== remove) { selected = file.path; renderFiles(); } });
    $('file-list').append(row);
  });
  if (!files.some(file => file.path === selected)) selected = files[0]?.path || '';
  $('output-name').value = files.find(file => file.path === selected)?.stem || '';
  $('start').disabled = busy || files.length === 0 || (hasLink && !folderPath);
  $('start').disabled ||= preparingModel || (offlineMode && (hasLink || !cachedModels[$('profile').value]));
  const modelSaved = Boolean(cachedModels[$('profile').value]);
  $('prepare-model').classList.toggle('hidden', modelSaved);
  $('prepare-model').disabled = busy || preparingModel;
  $('prepare-model').textContent = preparingModel ? 'Preparando...' : 'Preparar modelo';
  $('model-saved').classList.toggle('hidden', !modelSaved);
  $('offline-mode').disabled = busy || preparingModel;
  $('cancel').classList.toggle('hidden', !busy);
  $('cancel').disabled = cancelling;
  $('action-hint').classList.toggle('source-warning', hasLink && !folderPath && !busy);
  $('action-hint').textContent = offlineMode && hasLink && !busy ? 'Remova os links para usar o modo offline.' : offlineMode && !cachedModels[$('profile').value] && !busy ? 'Prepare o modelo escolhido para transcrever offline.' : hasLink && !folderPath && !busy ? 'Escolha uma pasta de destino para os links.' : activityMessage || (busy ? 'Transcrição em andamento.' : files.length ? `${files.length} fonte${files.length > 1 ? 's' : ''} pronta${files.length > 1 ? 's' : ''} para transcrever.` : 'Adicione uma fonte para continuar.');
  for (const id of ['pick-files', 'add-files', 'clear-files', 'pick-folder', 'reset-folder', 'output-name', 'format', 'profile', 'source-url', 'add-link']) $(id).disabled = busy;
  $('profile').disabled ||= preparingModel;
  $('source-url').disabled ||= offlineMode;
  $('add-link').disabled ||= offlineMode;
}
function addResult(path) {
  results.push(path);
  $('results').classList.remove('hidden');
  const row = document.createElement('div'); row.className = 'result-row';
  const title = document.createElement('strong'); title.textContent = path.split(/[\\/]/).pop();
  const open = document.createElement('button'); open.textContent = 'Abrir arquivo';
  open.addEventListener('click', () => backend.open_result(path, false));
  const folder = document.createElement('button'); folder.textContent = 'Abrir pasta';
  folder.addEventListener('click', () => backend.open_result(path, true));
  row.append(title, open, folder); $('result-list').append(row);
}
function receive(raw) {
  const data = JSON.parse(raw);
  if (cancelling && !['cancelled', 'finished', 'error', 'state'].includes(data.type)) return;
  switch (data.type) {
    case 'options':
      Object.entries(data.formats).forEach(([value, help]) => {
        const option = new Option(value.toUpperCase(), value); option.dataset.help = help; $('format').add(option);
      });
      data.profiles.forEach(profile => {
        modelNames[profile.value] = profile.model;
        modelDetails[profile.value] = profile.details;
        modelDiskBytes[profile.value] = profile.bytes;
        const option = new Option(profile.label, profile.value); option.dataset.help = profile.help; $('profile').add(option);
        const p = document.createElement('p');
        const strong = document.createElement('strong'); strong.textContent = `${profile.label}: `;
        p.append(strong, document.createTextNode(profile.help)); $('profile-comparison').append(p);
      });
      cachedModels = data.cached_models;
      $('profile').value = 'equilibrado'; updateHelp(); renderFiles(); break;
    case 'state':
      files = data.files; busy = data.busy; preparingModel = data.preparing_model; folderPath = data.folder;
      if (!files.some(file => file.path === selected)) selected = files[0]?.path || '';
      if (files.some(file => file.path === $('source-url').value.trim())) $('source-url').value = '';
      $('folder-name').textContent = data.folder || 'Ao lado de cada arquivo';
      $('reset-folder').classList.toggle('hidden', !data.folder);
      renderFiles(); break;
    case 'model_preparing':
      preparingModel = true;
      modelPreparingSince = Date.now();
      $('model-status').textContent = `Baixando ${data.model} para este computador...`;
      $('model-help').textContent = 'O primeiro download pode demorar. O modelo ficará salvo para as próximas sessões.';
      renderFiles(); break;
    case 'model_prepared':
      modelPreparingSince = 0;
      Object.keys(modelNames).forEach(key => { if (modelNames[key] === data.model) { cachedModels[key] = true; modelDiskBytes[key] = data.bytes; } });
      updateModelDetails();
      $('model-status').textContent = 'Modelo salvo neste computador';
      $('model-help').textContent = 'Pronto para transcrever arquivos locais sem baixar o modelo novamente.';
      renderFiles(); break;
    case 'model_prepare_error':
      modelPreparingSince = 0;
      $('model-status').textContent = 'Não foi possível preparar o modelo';
      $('model-help').textContent = data.message;
      renderFiles(); break;
    case 'input_error':
      $('input-error').textContent = data.message;
      $('input-error').classList.remove('hidden');
      if (data.path) { selected = data.path; renderFiles(); $('output-name').focus(); }
      else if ($('source-url').value) $('source-url').focus();
      break;
    case 'started':
      waitingText = '';
      wasCancelled = false; cancelling = false;
      activityMessage = 'Preparando modelo e áudio...';
      $('action-hint').textContent = activityMessage;
      hadError = false; results.length = 0; $('result-list').replaceChildren();
      $('results').classList.add('hidden'); $('input-error').classList.add('hidden');
      $('activity-empty').classList.add('hidden'); $('activity-work').classList.remove('hidden');
      $('status-pill').textContent = 'Em andamento'; $('status-pill').className = 'status-pill running';
      $('log').replaceChildren(); setProgress('progress', 'percent', 0); break;
    case 'current':
      currentNumber = data.number; currentTotal = data.total;
      $('file-count').textContent = `Fonte ${data.number} de ${data.total}`;
      $('current-file').textContent = data.name;
      showWaiting('Preparando fonte...');
      $('progress-label').textContent = 'Transcrição';
      $('progress-track').classList.remove('download-stage');
      activityMessage = `Preparando ${data.name}...`;
      $('action-hint').textContent = activityMessage;
      $('global-wrap').classList.toggle('hidden', data.total < 2);
      setProgress('progress', 'percent', 0);
      setProgress('global-progress', 'global-percent', (data.number - 1) / data.total * 100);
      addLog(`Preparando: ${data.name}`); break;
    case 'download':
      if (waitingText !== 'Conectando ao site e obtendo mídia...') {
        showWaiting('Conectando ao site e obtendo mídia...');
        addLog('Conectando ao site e obtendo mídia...');
      }
      $('progress-label').textContent = 'Download';
      $('progress-track').classList.add('download-stage');
      activityMessage = waitingText;
      if (data.percent == null) $('percent').textContent = '—';
      else setProgress('progress', 'percent', data.percent);
      break;
    case 'downloaded':
      $('current-file').textContent = data.name;
      showWaiting('Preparando áudio para transcrição...');
      $('progress-label').textContent = 'Transcrição';
      $('progress-track').classList.remove('download-stage');
      setProgress('progress', 'percent', 0);
      activityMessage = 'Mídia obtida. Preparando áudio...';
      $('action-hint').textContent = activityMessage;
      addLog(`Mídia obtida: ${data.name}`);
      break;
    case 'model_loading':
      showWaiting(`Carregando modelo ${data.model}...`);
      $('progress-label').textContent = 'Modelo';
      setProgress('progress', 'percent', 0);
      $('percent').textContent = '—';
      addLog(`Carregando modelo ${data.model}. No primeiro uso, ele pode ser baixado da internet.`);
      if (data.profile === 'maximo') addLog('O perfil Máximo pode levar vários minutos em CPU.');
      break;
    case 'model_ready':
      showWaiting('Modelo pronto. Preparando áudio...');
      $('progress-label').textContent = 'Transcrição';
      addLog('Modelo pronto.');
      break;
    case 'progress':
      if (data.phase === 'started') {
        waitingText = '';
        $('progress-label').textContent = 'Transcrição';
        $('progress-track').classList.remove('download-stage');
        $('work-status').textContent = `Processando bloco ${data.chunk}/${data.total ?? '?'}`;
        activityMessage = $('work-status').textContent;
        $('action-hint').textContent = activityMessage;
        if (data.total == null) $('percent').textContent = '—';
      } else if (data.phase === 'completed') {
        if (data.total) {
          const fraction = Math.min(.99, data.done / data.total);
          setProgress('progress', 'percent', fraction * 100);
          if (currentTotal > 1) setProgress('global-progress', 'global-percent', ((currentNumber - 1 + fraction) / currentTotal) * 100);
        }
        addLog(`${data.skipped ? 'Retomado' : 'Concluído'} bloco ${data.chunk} (${Number(data.seconds).toFixed(1)}s de áudio)`);
      } else if (data.phase === 'finished') setProgress('progress', 'percent', 100);
      break;
    case 'result':
      addResult(data.path); addLog(`Concluído: ${data.path}`);
      if (currentTotal > 1) setProgress('global-progress', 'global-percent', currentNumber / currentTotal * 100);
      break;
    case 'error':
      waitingText = '';
      hadError = true; $('work-status').textContent = 'Falha na transcrição';
      activityMessage = `Falha: ${data.message}`;
      $('action-hint').textContent = activityMessage;
      $('status-pill').textContent = 'Falha'; $('status-pill').className = 'status-pill failed';
      $('result-title').textContent = 'Arquivos concluídos antes da falha';
      addLog(`Erro: ${data.message}`); break;
    case 'cancelling':
      cancelling = true; waitingText = '';
      $('cancel').disabled = true;
      $('work-status').textContent = 'Cancelando transcrição...';
      activityMessage = 'Cancelando a fonte atual e a fila restante...';
      $('action-hint').textContent = activityMessage;
      $('status-pill').textContent = 'Cancelando';
      addLog('Cancelamento solicitado. Aguardando a operação atual parar...');
      break;
    case 'cancelled':
      wasCancelled = true; waitingText = '';
      $('work-status').textContent = 'Transcrição cancelada';
      activityMessage = 'Transcrição cancelada. A fila restante não foi processada.';
      $('action-hint').textContent = activityMessage;
      $('status-pill').textContent = 'Cancelado'; $('status-pill').className = 'status-pill cancelled';
      $('result-title').textContent = 'Arquivos concluídos antes do cancelamento';
      addLog('Transcrição cancelada.');
      break;
    case 'finished':
      waitingText = '';
      if (!hadError && !wasCancelled) { $('work-status').textContent = 'Transcrição concluída'; $('status-pill').textContent = 'Concluído'; $('status-pill').className = 'status-pill running'; $('result-title').textContent = 'Arquivos concluídos'; activityMessage = 'Transcrição concluída.'; $('action-hint').textContent = activityMessage; }
      break;
  }
}
function updateModelDetails() {
  const key = $('profile').value;
  const details = modelDetails[key];
  if (!details) return;
  $('selected-model').textContent = modelNames[key];
  $('model-description').textContent = details.description;
  $('model-parameters').textContent = `${details.parameters_millions.toLocaleString('pt-BR')} milhões de parâmetros`;
  const bytes = modelDiskBytes[key];
  $('model-disk').textContent = bytes == null ? 'Ainda não salvo' : `${(bytes / 1048576).toLocaleString('pt-BR', {maximumFractionDigits: 0})} MB neste computador`;
}
function updateHelp() {
  $('format-help').textContent = $('format').selectedOptions[0]?.dataset.help || '';
  $('profile-help').textContent = $('profile').selectedOptions[0]?.dataset.help || '';
  updateModelDetails();
  if (!preparingModel) {
    $('model-status').textContent = cachedModels[$('profile').value] ? 'Modelo salvo neste computador' : 'Modelo ainda não foi baixado';
    $('model-help').textContent = cachedModels[$('profile').value] ? 'Disponível para arquivos locais sem internet.' : 'Prepare este perfil uma vez para usá-lo offline.';
  }
  renderFiles();
}
new QWebChannel(qt.webChannelTransport, channel => {
  backend = channel.objects.backend;
  backend.ready();
  const poll = () => backend.take_events(raw => {
    JSON.parse(raw).forEach(event => receive(JSON.stringify(event)));
    setTimeout(poll, 100);
  });
  poll();
});
$('format').addEventListener('change', updateHelp);
$('profile').addEventListener('change', updateHelp);
$('prepare-model').addEventListener('click', () => backend.prepare_selected_model($('profile').value));
$('offline-mode').addEventListener('change', event => { offlineMode = event.target.checked; renderFiles(); });
$('pick-files').addEventListener('click', () => backend.pick_files());
$('add-files').addEventListener('click', () => backend.pick_files());
$('clear-files').addEventListener('click', () => backend.clear_files());
$('link-form').addEventListener('submit', event => {
  event.preventDefault();
  $('input-error').classList.add('hidden');
  backend.add_url($('source-url').value);
});
$('pick-folder').addEventListener('click', () => backend.pick_folder());
$('reset-folder').addEventListener('click', () => backend.reset_folder());
$('output-name').addEventListener('input', event => {
  const file = files.find(file => file.path === selected);
  if (file) { file.stem = event.target.value; backend.rename_file(file.path, file.stem); }
});
$('start').addEventListener('click', () => backend.start($('format').value, $('profile').value, offlineMode));
$('cancel').addEventListener('click', () => backend.cancel());
