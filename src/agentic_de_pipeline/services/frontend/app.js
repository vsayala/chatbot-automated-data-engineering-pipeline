async function apiGet(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function apiPost(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function appendChat(role, text) {
  const log = document.getElementById('chat-log');
  const box = document.createElement('div');
  box.className = 'chat-msg';

  const roleDiv = document.createElement('div');
  roleDiv.className = 'role';
  roleDiv.textContent = role;

  const textDiv = document.createElement('div');
  textDiv.textContent = text;

  box.appendChild(roleDiv);
  box.appendChild(textDiv);
  log.appendChild(box);
  log.scrollTop = log.scrollHeight;
}

function renderActive(items) {
  const node = document.getElementById('active-items');
  node.innerHTML = '';
  items.forEach((item) => {
    const div = document.createElement('div');
    div.className = 'item';
    const questions = (item.clarification_questions || []).map((q) => `<li>${q}</li>`).join('');
    div.innerHTML = `
      <strong>#${item.id} ${item.title}</strong>
      <div class="meta">type=${item.type} | priority=${item.priority} | repo=${item.repo_name || 'N/A'} | state=${item.state}</div>
      <div class="small">clarification_required=${item.needs_clarification}</div>
      ${questions ? `<ul class="small">${questions}</ul>` : ''}
    `;
    node.appendChild(div);
  });
}

function renderApprovals(rows) {
  const node = document.getElementById('approvals');
  node.innerHTML = '';
  rows.forEach((row) => {
    const div = document.createElement('div');
    div.className = 'item';
    div.innerHTML = `
      <strong>${row.stage}</strong>
      <div>${row.summary}</div>
      <div class="small">request_id=${row.request_id}</div>
      <input id="comment-${row.request_id}" placeholder="comment" />
      <div class="approval-actions">
        <button data-id="${row.request_id}" data-approve="true">Approve</button>
        <button class="danger" data-id="${row.request_id}" data-approve="false">Reject</button>
      </div>
    `;
    node.appendChild(div);
  });

  node.querySelectorAll('button[data-id]').forEach((btn) => {
    btn.onclick = async () => {
      const requestId = btn.getAttribute('data-id');
      const approved = btn.getAttribute('data-approve') === 'true';
      const comment = document.getElementById(`comment-${requestId}`).value || '';
      await apiPost(`/approvals/${requestId}/decision`, {
        approved,
        approver: 'hil-ui',
        comment,
      });
      appendChat('system', `Approval decision submitted for ${requestId}: approved=${approved}`);
      await refreshAll();
    };
  });
}

function renderClarifications(rows) {
  const node = document.getElementById('clarifications');
  node.innerHTML = '';
  rows.forEach((row) => {
    const div = document.createElement('div');
    div.className = 'item';

    const titleEl = document.createElement('strong');
    titleEl.textContent = `#${row.work_item_id} ${row.work_item_title}`;
    div.appendChild(titleEl);

    const requestInfoEl = document.createElement('div');
    requestInfoEl.className = 'small';
    requestInfoEl.textContent = `request_id=${row.request_id}`;
    div.appendChild(requestInfoEl);

    row.questions.forEach((q, idx) => {
      const questionWrapper = document.createElement('div');
      const questionLabel = document.createElement('div');
      questionLabel.className = 'small';
      questionLabel.textContent = `Q${idx + 1}: ${q}`;
      questionWrapper.appendChild(questionLabel);

      const textarea = document.createElement('textarea');
      textarea.id = `clr-${row.request_id}-${idx}`;
      textarea.rows = 2;
      questionWrapper.appendChild(textarea);

      div.appendChild(questionWrapper);
    });

    const button = document.createElement('button');
    button.id = `btn-clr-${row.request_id}`;
    button.className = 'secondary';
    button.textContent = 'Submit Clarification';
    div.appendChild(button);

    node.appendChild(div);

    button.onclick = async () => {
      const answers = {};
      row.questions.forEach((q, idx) => {
        const value = div.querySelector(`#clr-${row.request_id}-${idx}`).value || '';
        answers[q] = value;
      });
      await apiPost(`/clarifications/${row.request_id}/response`, {
        responder: 'hil-ui',
        answers,
      });
      appendChat('system', `Clarification submitted for ${row.request_id}`);
      await refreshAll();
    };
  });
}

async function refreshAll() {
  const [active, approvals, clarifications] = await Promise.all([
    apiGet('/work-items/active?limit=50'),
    apiGet('/approvals/pending-with-suggestions'),
    apiGet('/clarifications/pending'),
  ]);
  renderActive(active.items || []);
  renderApprovals(approvals.pending || []);
  renderClarifications(clarifications.pending || []);
}

async function runPreflight() {
  const data = await apiGet('/preflight/run');
  appendChat('agent', `Preflight: ${JSON.stringify(data.checks, null, 2)}`);
}

async function processNext() {
  const data = await apiPost('/workflow/process-next', {});
  appendChat('agent', `Workflow response: ${JSON.stringify(data, null, 2)}`);
  await refreshAll();
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  appendChat('you', text);
  const response = await apiPost('/chat/message', { message: text, context: {} });
  appendChat('agent', response.response);
}

document.getElementById('btn-preflight').onclick = runPreflight;
document.getElementById('btn-process').onclick = processNext;
document.getElementById('btn-refresh-all').onclick = refreshAll;
document.getElementById('btn-chat-send').onclick = sendChat;

document.getElementById('chat-input').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    event.preventDefault();
    sendChat();
  }
});

refreshAll().catch((error) => {
  appendChat('system', `Initial load failed: ${error.message}`);
});
