const $ = (id) => document.getElementById(id);
const state = { conversationId: null, busy: false, conversations: [], voiceEnabled: false };
const storage = {
  get url() { return localStorage.getItem('idoma_api_url') || location.origin; },
  get token() { return localStorage.getItem('idoma_api_token') || ''; }
};

function cleanUrl(value) { return value.trim().replace(/\/+$/, ''); }
function setPrivacyMode(provider) {
  const pill = $('privacyMode');
  if (!pill) return;
  const cloud = provider === 'cloud';
  pill.textContent = cloud ? '● AI CLOUD' : '● AI LOCALE';
  pill.classList.toggle('cloud', cloud);
}
function setConnection(ok, text) {
  $('statusDot').classList.toggle('online', ok);
  $('connectionText').textContent = text;
}
function escapeText(text) { return String(text ?? ''); }
async function api(path, options = {}) {
  const url = cleanUrl(storage.url) + path;
  const headers = { ...(options.headers || {}) };
  if (storage.token) headers.Authorization = `Bearer ${storage.token}`;
  if (options.body) headers['Content-Type'] = 'application/json';
  const response = await fetch(url, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Errore server ${response.status}`);
  return data;
}
function showSettings() {
  $('apiUrl').value = storage.url;
  $('apiToken').value = storage.token;
  $('settingsStatus').textContent = '';
  $('settingsModal').classList.remove('hidden');
}
function hideSettings() { $('settingsModal').classList.add('hidden'); }
function addMessage(role, content) {
  $('welcome').classList.add('hidden');
  const row = document.createElement('div');
  row.className = `message-row ${role}`;
  if (role === 'assistant') {
    const avatar = document.createElement('div'); avatar.className = 'avatar'; avatar.textContent = 'I'; row.appendChild(avatar);
  }
  const body = document.createElement('div'); body.className = 'message-content'; body.textContent = escapeText(content);
  row.appendChild(body);
  if (role === 'user') row.classList.add('user');
  $('messages').appendChild(row);
  $('chatArea').scrollTop = $('chatArea').scrollHeight;
  return body;
}
function clearMessages() { $('messages').replaceChildren(); $('welcome').classList.remove('hidden'); }
function setBusy(busy) {
  state.busy = busy; $('sendButton').disabled = busy; $('messageInput').disabled = busy;
  $('sendButton').textContent = busy ? '…' : '↑';
}
async function loadReminders() {
  const host = $('reminderList');
  if (!host) return;
  try {
    const items = await api('/api/reminders');
    host.replaceChildren();
    if (!items.length) {
      const empty = document.createElement('div');
      empty.className = 'reminder-empty';
      empty.textContent = 'Nessun promemoria';
      host.appendChild(empty);
      return;
    }
    for (const item of items.slice(0, 8)) {
      const row = document.createElement('div');
      row.className = 'reminder-item';
      const content = document.createElement('div');
      content.className = 'reminder-copy';
      const title = document.createElement('div');
      title.className = 'reminder-title';
      title.textContent = item.title;
      const due = document.createElement('div');
      due.className = 'reminder-due';
      due.textContent = new Date(item.due_at).toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'short' });
      content.append(title, due);
      const done = document.createElement('button');
      done.className = 'reminder-complete';
      done.type = 'button';
      done.textContent = '✓';
      done.title = 'Completa promemoria';
      done.setAttribute('aria-label', `Completa: ${item.title}`);
      done.addEventListener('click', async () => {
        done.disabled = true;
        try {
          await api(`/api/reminders/${encodeURIComponent(item.id)}/complete`, { method: 'POST' });
          await loadReminders();
        } catch (error) {
          done.disabled = false;
          setConnection(false, `Promemoria: ${error.message}`);
        }
      });
      row.append(content, done);
      host.appendChild(row);
    }
  } catch (error) {
    host.replaceChildren();
    const unavailable = document.createElement('div');
    unavailable.className = 'reminder-empty';
    unavailable.textContent = 'Promemoria non disponibili';
    host.appendChild(unavailable);
  }
}

async function loadMemory() {
  const host = $('memoryList');
  if (!host) return;
  host.replaceChildren();
  try {
    const items = await api('/api/memory');
    if (!items.length) {
      const empty = document.createElement('div');
      empty.className = 'memory-empty';
      empty.textContent = 'La memoria è ancora vuota. Puoi dire: "Ricorda che..."';
      host.appendChild(empty);
      return;
    }
    for (const item of items) {
      const row = document.createElement('div');
      row.className = 'memory-item';
      row.textContent = item.content || [item.subject, item.value].filter(Boolean).join(': ');
      host.appendChild(row);
    }
  } catch (error) {
    const empty = document.createElement('div');
    empty.className = 'memory-empty error';
    empty.textContent = 'Non riesco a leggere la memoria: ' + error.message;
    host.appendChild(empty);
  }
}

function showMemory() {
  $('memoryModal').classList.remove('hidden');
  loadMemory();
}
function hideMemory() { $('memoryModal').classList.add('hidden'); }

async function loadRuntimeStatus() {
  try {
    const status = await api('/api/status');
    state.voiceEnabled = Boolean(status.voice_enabled);
    const button = $('voiceButton');
    const label = $('voiceStatus');
    const agent = $('agentStatus');
    if (agent) {
      agent.textContent = status.agent_online ? 'PC pronto per i comandi' : 'Agente PC offline';
      agent.classList.toggle('listening', Boolean(status.agent_online));
      agent.classList.toggle('error', !status.agent_online);
    }
    if (button) {
      button.classList.toggle('active', state.voiceEnabled);
      button.setAttribute('aria-pressed', String(state.voiceEnabled));
      button.title = 'Premi per parlare usando il microfono locale del PC.';
      button.setAttribute('aria-label', button.title);
    }
    if (label) {
      label.textContent = status.voice_status || (state.voiceEnabled ? 'Ascolto vocale attivo' : 'Ascolto vocale disattivato');
      label.classList.toggle('listening', state.voiceEnabled && /ascolto|pronta|ti ascolto/i.test(status.voice_status || ''));
      label.classList.toggle('error', /errore|non disponibile|problema/i.test(status.voice_status || ''));
    }
  } catch (error) {
    const label = $('voiceStatus');
    if (label) {
      label.textContent = 'Servizio vocale desktop non raggiungibile';
      label.classList.add('error');
    }
  }
}

async function requestVoiceInput() {
  const button = $('voiceButton');
  const label = $('voiceStatus');
  if (button) button.disabled = true;
  if (label) {
    label.textContent = 'Attivo il microfono del PC…';
    label.classList.remove('error');
  }
  try {
    await api('/api/voice/listen', { method: 'POST' });
    if (label) label.textContent = 'Ti ascolto: parla adesso nel microfono del Lenovo.';
  } catch (error) {
    if (label) {
      label.textContent = 'Microfono non disponibile: ' + error.message;
      label.classList.add('error');
    }
  } finally {
    if (button) button.disabled = false;
  }
}

async function loadConversations() {
  const items = await api('/api/conversations');
  state.conversations = items;
  const list = $('conversationList'); list.replaceChildren();
  for (const item of items) {
    const button = document.createElement('button');
    button.className = 'conversation-item' + (item.id === state.conversationId ? ' active' : '');
    button.textContent = item.title || 'Nuova conversazione';
    button.title = button.textContent;
    button.addEventListener('click', () => openConversation(item.id));
    list.appendChild(button);
  }
}
async function openConversation(id) {
  state.conversationId = id; clearMessages();
  const items = await api(`/api/conversations/${encodeURIComponent(id)}/messages`);
  if (items.length) {
    for (const item of items) {
      const body = addMessage(item.role, item.content);
      if (item.agent_task_id && ['queued', 'running'].includes(item.agent_task_status)) {
        pollAgentTask(item.agent_task_id, body);
      }
    }
  } else $('welcome').classList.remove('hidden');
  await loadConversations();
  $('sidebar').classList.remove('open');
}
async function createConversation() {
  const item = await api('/api/conversations', { method: 'POST' });
  state.conversationId = item.id; clearMessages(); await loadConversations();
  $('sidebar').classList.remove('open'); $('messageInput').focus();
}
async function sendMessage(text = null) {
  if (state.busy) return;
  const message = (text ?? $('messageInput').value).trim();
  if (!message) return;
  const requestConversationId = state.conversationId;
  $('messageInput').value = ''; $('messageInput').style.height = 'auto';
  addMessage('user', message); setBusy(true);
  const typing = document.createElement('div'); typing.className = 'typing'; typing.textContent = 'IDOMA sta elaborando…'; $('messages').appendChild(typing);
  try {
    const result = await api('/api/chat', { method: 'POST', body: JSON.stringify({ message, conversation_id: requestConversationId }) });
    typing.remove();
    // Do not inject a late reply into a different conversation opened while the request was running.
    if (state.conversationId !== requestConversationId) { await loadConversations(); return; }
    state.conversationId = result.conversation_id;
    const assistantBody = addMessage('assistant', result.reply);
    if (result.pending && result.task_id) pollAgentTask(result.task_id, assistantBody);
    setPrivacyMode(result.provider);
    setConnection(true, `Connesso · ${result.provider === 'unavailable' ? 'AI non disponibile' : result.provider}`);
    await loadConversations();
    await loadReminders();
  } catch (error) {
    typing.remove();
    if (state.conversationId === requestConversationId) {
      addMessage('assistant', `Non riesco a completare la richiesta: ${error.message}\n\nApri Impostazioni e verifica indirizzo server e token.`);
    }
    setConnection(false, 'Errore di connessione');
  } finally { setBusy(false); $('messageInput').focus(); }
}

async function pollAgentTask(taskId, messageBody, attempt = 0) {
  if (!messageBody) return;
  if (attempt >= 180) {
    if (messageBody.isConnected) messageBody.textContent = `L'attività #${taskId} è ancora in corso. Puoi continuare a usare IDOMA; il risultato sarà salvato nella conversazione.`;
    return;
  }
  try {
    const task = await api(`/api/agent/tasks/${encodeURIComponent(taskId)}`);
    if (task.status === 'done') {
      if (messageBody.isConnected) messageBody.textContent = `Fatto: ${task.result || 'operazione completata.'}`;
      return;
    }
    if (task.status === 'failed') {
      if (messageBody.isConnected) messageBody.textContent = `Non sono riuscito a completare l'attività: ${task.result || 'errore non specificato.'}`;
      return;
    }
    if (messageBody.isConnected) messageBody.textContent = `IDOMA sta lavorando sul PC… (attività #${taskId})`;
  } catch (error) {
    if (attempt >= 5) {
      if (messageBody.isConnected) messageBody.textContent = `Non riesco a verificare lo stato dell'attività #${taskId}. Il PC potrebbe comunque completarla; riapri la conversazione per controllare il risultato.`;
      return;
    }
  }
  window.setTimeout(() => pollAgentTask(taskId, messageBody, attempt + 1), 1000);
}

async function verifyConnection() {
  $('settingsStatus').textContent = 'Verifica in corso…';
  localStorage.setItem('idoma_api_url', cleanUrl($('apiUrl').value) || location.origin);
  localStorage.setItem('idoma_api_token', $('apiToken').value.trim());
  try {
    await api('/api/health'); await api('/api/conversations');
    $('settingsStatus').textContent = 'Connessione verificata. IDOMA è collegato.';
    setConnection(true, 'Server connesso'); await loadConversations(); await loadReminders(); await loadRuntimeStatus();
    setTimeout(hideSettings, 700);
  } catch (error) {
    $('settingsStatus').textContent = `Verifica non riuscita: ${error.message}`;
    setConnection(false, 'Non connesso');
  }
}

$('sendButton').addEventListener('click', () => sendMessage());
$('voiceButton').addEventListener('click', requestVoiceInput);
$('messageInput').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendMessage(); }
});
$('messageInput').addEventListener('input', () => { const el = $('messageInput'); el.style.height = 'auto'; el.style.height = `${Math.min(el.scrollHeight, 180)}px`; });
$('newChat').addEventListener('click', () => createConversation().catch(showSettings));
$('openSettings').addEventListener('click', showSettings);
$('openMemory').addEventListener('click', showMemory);
$('closeMemory').addEventListener('click', hideMemory);
$('doneMemory').addEventListener('click', hideMemory);
$('refreshMemory').addEventListener('click', loadMemory);
$('closeSettings').addEventListener('click', hideSettings);
$('cancelSettings').addEventListener('click', hideSettings);
$('saveSettings').addEventListener('click', verifyConnection);
$('mobileMenu').addEventListener('click', () => $('sidebar').classList.toggle('open'));
document.querySelectorAll('.suggestion').forEach(button => button.addEventListener('click', () => sendMessage(button.dataset.prompt)));

(async function init() {
  if ('serviceWorker' in navigator && location.protocol === 'https:') navigator.serviceWorker.register('/static/sw.js').catch(() => {});
  if (!storage.token) { showSettings(); return; }
  try { await api('/api/health'); await loadConversations(); await loadReminders(); await loadRuntimeStatus(); setConnection(true, 'Server connesso'); }
  catch { setConnection(false, 'Configurazione richiesta'); showSettings(); }
})();

window.setInterval(() => {
  if (!storage.token) return;
  loadConversations().catch(() => {});
  loadReminders();
}, 60000);

window.setInterval(() => {
  if (!storage.token) return;
  loadRuntimeStatus();
}, 3000);
