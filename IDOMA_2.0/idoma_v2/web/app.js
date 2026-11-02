const $ = (id) => document.getElementById(id);
const state = { conversationId: null, busy: false, conversations: [] };
const storage = {
  get url() { return localStorage.getItem('idoma_api_url') || location.origin; },
  get token() { return localStorage.getItem('idoma_api_token') || ''; }
};

function cleanUrl(value) { return value.trim().replace(/\/+$/, ''); }
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
}
function clearMessages() { $('messages').replaceChildren(); $('welcome').classList.remove('hidden'); }
function setBusy(busy) {
  state.busy = busy; $('sendButton').disabled = busy; $('messageInput').disabled = busy;
  $('sendButton').textContent = busy ? '…' : '↑';
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
  if (items.length) for (const item of items) addMessage(item.role, item.content);
  else $('welcome').classList.remove('hidden');
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
  $('messageInput').value = ''; $('messageInput').style.height = 'auto';
  addMessage('user', message); setBusy(true);
  const typing = document.createElement('div'); typing.className = 'typing'; typing.textContent = 'IDOMA sta elaborando…'; $('messages').appendChild(typing);
  try {
    const result = await api('/api/chat', { method: 'POST', body: JSON.stringify({ message, conversation_id: state.conversationId }) });
    state.conversationId = result.conversation_id;
    typing.remove(); addMessage('assistant', result.reply);
    setConnection(true, `Connesso · ${result.provider === 'unavailable' ? 'AI non disponibile' : result.provider}`);
    await loadConversations();
  } catch (error) {
    typing.remove(); addMessage('assistant', `Non riesco a completare la richiesta: ${error.message}\n\nApri Impostazioni e verifica indirizzo server e token.`);
    setConnection(false, 'Errore di connessione');
  } finally { setBusy(false); $('messageInput').focus(); }
}
async function verifyConnection() {
  $('settingsStatus').textContent = 'Verifica in corso…';
  localStorage.setItem('idoma_api_url', cleanUrl($('apiUrl').value) || location.origin);
  localStorage.setItem('idoma_api_token', $('apiToken').value.trim());
  try {
    await api('/api/health'); await api('/api/conversations');
    $('settingsStatus').textContent = 'Connessione verificata. IDOMA è collegato.';
    setConnection(true, 'Server connesso'); await loadConversations();
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
  try { await api('/api/health'); await loadConversations(); setConnection(true, 'Server connesso'); }
  catch { setConnection(false, 'Configurazione richiesta'); showSettings(); }
})();
