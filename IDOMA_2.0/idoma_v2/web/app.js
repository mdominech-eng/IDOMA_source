const $ = (id) => document.getElementById(id);
const state = { conversationId: null, busy: false, conversations: [] };
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
    setConnection(true, 'Server connesso'); await loadConversations(); await loadReminders();
    setTimeout(hideSettings, 700);
  } catch (error) {
    $('settingsStatus').textContent = `Verifica non riuscita: ${error.message}`;
    setConnection(false, 'Non connesso');
  }
}

$('sendButton').addEventListener('click', () => sendMessage());
$('messageInput').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendMessage(); }
});
$('messageInput').addEventListener('input', () => { const el = $('messageInput'); el.style.height = 'auto'; el.style.height = `${Math.min(el.scrollHeight, 180)}px`; });
$('newChat').addEventListener('click', () => createConversation().catch(showSettings));
$('openSettings').addEventListener('click', showSettings);
$('closeSettings').addEventListener('click', hideSettings);
$('cancelSettings').addEventListener('click', hideSettings);
$('saveSettings').addEventListener('click', verifyConnection);
$('mobileMenu').addEventListener('click', () => $('sidebar').classList.toggle('open'));
document.querySelectorAll('.suggestion').forEach(button => button.addEventListener('click', () => sendMessage(button.dataset.prompt)));

(async function init() {
  if ('serviceWorker' in navigator && location.protocol === 'https:') navigator.serviceWorker.register('/static/sw.js').catch(() => {});
  if (!storage.token) { showSettings(); return; }
  try { await api('/api/health'); await loadConversations(); await loadReminders(); setConnection(true, 'Server connesso'); }
  catch { setConnection(false, 'Configurazione richiesta'); showSettings(); }
})();

window.setInterval(() => {
  if (storage.token) loadReminders();
}, 60000);
