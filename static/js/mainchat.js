socket.on('connect', () => {
  socket.emit('join', { room });
});

function renderMessage(data) {
  const messages = document.getElementById('messages');
  const line = document.createElement('div');

  const nameSpan = document.createElement('span');
  nameSpan.className = 'username';
  nameSpan.innerText = data.username;

  if (data.username === username) {
    nameSpan.classList.add('mine-name');
  }

  const msgSpan = document.createElement('span');
  msgSpan.className = 'chat-message';
  msgSpan.innerText = data.message;

  const timeSpan = document.createElement('span');
  timeSpan.className = 'time';

  const sentDate = new Date(data.timestamp);
  timeSpan.innerText = sentDate.toLocaleTimeString();

  line.append(nameSpan, msgSpan, timeSpan);

  messages.appendChild(line);
  messages.scrollTop = messages.scrollHeight;
}

socket.on('message', data => renderMessage(data));

socket.on('status', data => {
  const messages = document.getElementById('messages');
  const status = document.createElement('div');

  status.className = 'status';
  status.innerText = data.msg;

  messages.appendChild(status);
  messages.scrollTop = messages.scrollHeight;
});

socket.on('user_list', data => {
  const list = document.getElementById('users');

  list.innerHTML = '';

  data.users.forEach(u => {
    const li = document.createElement('li');
    li.innerText = u;
    list.appendChild(li);
  });
});

function sendMessage() {
  const input = document.getElementById('input');
  const txt = input.value.trim();

  if (!txt) return;

  socket.emit('text', {
    room,
    message: txt
  });

  input.value = '';
}

document.getElementById('send-btn').addEventListener('click', sendMessage);

document.getElementById('input').addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    e.preventDefault();
    sendMessage();
  }
});

const settingsBtn = document.getElementById('settings-btn');
const settingsMenu = document.getElementById('settings-menu');

settingsBtn.addEventListener('click', e => {
  e.stopPropagation();
  settingsMenu.classList.toggle('show');
});

document.addEventListener('click', e => {
  if (!settingsMenu.contains(e.target) && !settingsBtn.contains(e.target)) {
    settingsMenu.classList.remove('show');
  }
});

const roomChangeBtn = document.getElementById('room-change-btn');
const roomModal = document.getElementById('room-modal');
const roomModalClose = document.getElementById('room-modal-close');
const roomList = document.getElementById('room-list');
const roomTabs = document.getElementById('room-tabs');

const maxCustomTabs = 5;
const roomTabsKey = 'customRoomTabs';

function roomUrl(roomName) {
  return roomUrlTemplate.replace('__ROOM__', encodeURIComponent(roomName));
}

function getSavedTabs() {
  const saved = JSON.parse(localStorage.getItem(roomTabsKey) || 'null');

  if (Array.isArray(saved)) {
    return saved
      .filter(r => allRooms.includes(r))
      .filter(r => r !== mainRoom)
      .slice(0, maxCustomTabs);
  }

  return allRooms
    .filter(r => r !== mainRoom)
    .slice(0, maxCustomTabs);
}

function saveTabs(tabs) {
  localStorage.setItem(roomTabsKey, JSON.stringify(tabs));
}

function renderTabs() {
  const selectedTabs = getSavedTabs();
  const visibleTabs = [mainRoom, ...selectedTabs];

  roomTabs.innerHTML = '';

  visibleTabs.forEach(r => {
    const a = document.createElement('a');
    a.href = roomUrl(r);
    a.className = 'room-tab';

    if (r === room) {
      a.classList.add('active');
    }

    a.innerText = r;
    roomTabs.appendChild(a);
  });
}

function renderRoomList() {
  const selectedTabs = getSavedTabs();

  roomList.innerHTML = '';

  allRooms.forEach(r => {
    const row = document.createElement('div');
    row.className = 'room-choice';

    const name = document.createElement('button');
    name.type = 'button';
    name.className = 'room-choice-name';
    name.innerText = r;

    name.addEventListener('click', () => {
      window.location.href = roomUrl(r);
    });

    const checkbox = document.createElement('button');
    checkbox.type = 'button';
    checkbox.className = 'room-choice-check';

    const selectedIndex = selectedTabs.indexOf(r);

    if (r === mainRoom) {
      checkbox.innerText = '固定';
      checkbox.disabled = true;
      checkbox.classList.add('fixed');
    } else if (selectedIndex !== -1) {
      checkbox.innerText = selectedIndex + 1;
      checkbox.classList.add('checked');
    } else {
      checkbox.innerText = '';
    }

    checkbox.addEventListener('click', e => {
      e.stopPropagation();

      let nextTabs = getSavedTabs();
      const index = nextTabs.indexOf(r);

      if (index !== -1) {
        nextTabs.splice(index, 1);
      } else {
        if (nextTabs.length >= maxCustomTabs) {
          return;
        }

        nextTabs.push(r);
      }

      saveTabs(nextTabs);
      renderTabs();
      renderRoomList();
    });

    row.append(name, checkbox);
    roomList.appendChild(row);
  });
}

function openRoomModal() {
  settingsMenu.classList.remove('show');
  renderRoomList();
  roomModal.classList.add('show');
  roomModal.setAttribute('aria-hidden', 'false');
}

function closeRoomModal() {
  roomModal.classList.remove('show');
  roomModal.setAttribute('aria-hidden', 'true');
}

roomChangeBtn.addEventListener('click', e => {
  e.stopPropagation();
  openRoomModal();
});

roomModalClose.addEventListener('click', closeRoomModal);

roomModal.addEventListener('click', e => {
  if (e.target === roomModal) {
    closeRoomModal();
  }
});

renderTabs();

const usernameChangeBtn = document.getElementById('username-change-btn');
const usernameModal = document.getElementById('username-modal');
const usernameModalClose = document.getElementById('username-modal-close');
const usernameCancelBtn = document.getElementById('username-cancel-btn');
const usernameSaveBtn = document.getElementById('username-save-btn');

const newUsernameInput = document.getElementById('new-username');
const usernamePasswordInput = document.getElementById('username-password');
const usernameError = document.getElementById('username-error');

function openUsernameModal() {
  settingsMenu.classList.remove('show');

  newUsernameInput.value = '';
  usernamePasswordInput.value = '';
  usernameError.innerText = '';

  usernameSaveBtn.disabled = false;
  usernameSaveBtn.innerText = '変更';

  usernameModal.classList.add('show');
  usernameModal.setAttribute('aria-hidden', 'false');

  newUsernameInput.focus();
}

function closeUsernameModal() {
  usernameModal.classList.remove('show');
  usernameModal.setAttribute('aria-hidden', 'true');

  newUsernameInput.value = '';
  usernamePasswordInput.value = '';
  usernameError.innerText = '';

  usernameSaveBtn.disabled = false;
  usernameSaveBtn.innerText = '変更';
}

usernameChangeBtn.addEventListener('click', e => {
  e.stopPropagation();
  openUsernameModal();
});

usernameModalClose.addEventListener('click', closeUsernameModal);
usernameCancelBtn.addEventListener('click', closeUsernameModal);

usernameModal.addEventListener('click', e => {
  if (e.target === usernameModal) {
    closeUsernameModal();
  }
});

usernameSaveBtn.addEventListener('click', async () => {
  const newUsername = newUsernameInput.value.trim();
  const password = usernamePasswordInput.value;

  usernameError.innerText = '';

  if (!newUsername || !password) {
    usernameError.innerText = '新しいユーザー名とパスワードを入力してください。';
    return;
  }

  if (newUsername === username) {
    usernameError.innerText = '現在のユーザー名と同じです。';
    return;
  }

  usernameSaveBtn.disabled = true;
  usernameSaveBtn.innerText = '変更中...';

  try {
    const res = await fetch(`/change_username?room=${encodeURIComponent(room)}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        new_username: newUsername,
        password
      })
    });

    const data = await res.json();

    if (!data.ok) {
      usernameError.innerText = data.message || 'ユーザー名の変更に失敗しました。';

      usernameSaveBtn.disabled = false;
      usernameSaveBtn.innerText = '変更';

      return;
    }

    window.location.href = data.redirect;
  } catch (err) {
    usernameError.innerText = '通信エラーが発生しました。';

    usernameSaveBtn.disabled = false;
    usernameSaveBtn.innerText = '変更';
  }
});

const logoutBtn = document.getElementById('logout-btn');
const logoutModal = document.getElementById('logout-modal');
const logoutConfirmBtn = document.getElementById('logout-confirm-btn');
const logoutCancelBtn = document.getElementById('logout-cancel-btn');

function openLogoutModal() {
  settingsMenu.classList.remove('show');

  logoutModal.classList.add('show');
  logoutModal.setAttribute('aria-hidden', 'false');
}

function closeLogoutModal() {
  logoutModal.classList.remove('show');
  logoutModal.setAttribute('aria-hidden', 'true');

  logoutConfirmBtn.disabled = false;
  logoutConfirmBtn.innerText = 'ログアウト';
}

logoutBtn.addEventListener('click', e => {
  e.stopPropagation();
  openLogoutModal();
});

logoutCancelBtn.addEventListener('click', closeLogoutModal);

logoutModal.addEventListener('click', e => {
  if (e.target === logoutModal) {
    closeLogoutModal();
  }
});

logoutConfirmBtn.addEventListener('click', async () => {
  logoutConfirmBtn.disabled = true;
  logoutConfirmBtn.innerText = 'ログアウト中...';

  try {
    const res = await fetch('/logout', {
      method: 'POST'
    });

    const data = await res.json();

    if (data.ok) {
      window.location.href = data.redirect;
      return;
    }

    closeLogoutModal();
  } catch (err) {
    logoutConfirmBtn.disabled = false;
    logoutConfirmBtn.innerText = 'ログアウト';
    alert('通信エラーが発生しました。');
  }
});

const deleteAccountBtn = document.getElementById('delete-account');

const deleteModal = document.getElementById('delete-modal');
const deleteConfirmModal = document.getElementById('delete-confirm-modal');

const deleteModalClose = document.getElementById('delete-modal-close');
const deleteCancelBtn = document.getElementById('delete-cancel-btn');
const deleteNextBtn = document.getElementById('delete-next-btn');

const deleteFinalBtn = document.getElementById('delete-final-btn');
const deleteBackBtn = document.getElementById('delete-back-btn');

const deleteUsernameInput = document.getElementById('delete-username');
const deletePasswordInput = document.getElementById('delete-password');
const deleteError = document.getElementById('delete-error');

function openDeleteModal() {
  settingsMenu.classList.remove('show');

  deleteUsernameInput.value = '';
  deletePasswordInput.value = '';
  deleteError.innerText = '';

  deleteConfirmModal.classList.remove('show');
  deleteConfirmModal.setAttribute('aria-hidden', 'true');

  deleteModal.classList.add('show');
  deleteModal.setAttribute('aria-hidden', 'false');

  deleteUsernameInput.focus();
}

function closeDeleteModals() {
  deleteModal.classList.remove('show');
  deleteModal.setAttribute('aria-hidden', 'true');

  deleteConfirmModal.classList.remove('show');
  deleteConfirmModal.setAttribute('aria-hidden', 'true');

  deleteUsernameInput.value = '';
  deletePasswordInput.value = '';
  deleteError.innerText = '';

  deleteFinalBtn.disabled = false;
  deleteFinalBtn.innerText = '削除';
}

function openDeleteConfirmModal() {
  deleteError.innerText = '';

  deleteModal.classList.remove('show');
  deleteModal.setAttribute('aria-hidden', 'true');

  deleteConfirmModal.classList.add('show');
  deleteConfirmModal.setAttribute('aria-hidden', 'false');
}

deleteAccountBtn.addEventListener('click', e => {
  e.stopPropagation();
  openDeleteModal();
});

deleteModalClose.addEventListener('click', closeDeleteModals);
deleteCancelBtn.addEventListener('click', closeDeleteModals);
deleteBackBtn.addEventListener('click', closeDeleteModals);

deleteNextBtn.addEventListener('click', () => {
  const inputUsername = deleteUsernameInput.value.trim();
  const inputPassword = deletePasswordInput.value;

  deleteError.innerText = '';

  if (!inputUsername || !inputPassword) {
    deleteError.innerText = 'ユーザー名とパスワードを入力してください。';
    return;
  }

  openDeleteConfirmModal();
});

deleteFinalBtn.addEventListener('click', async () => {
  const inputUsername = deleteUsernameInput.value.trim();
  const inputPassword = deletePasswordInput.value;

  if (!inputUsername || !inputPassword) {
    deleteConfirmModal.classList.remove('show');
    deleteConfirmModal.setAttribute('aria-hidden', 'true');

    deleteModal.classList.add('show');
    deleteModal.setAttribute('aria-hidden', 'false');

    deleteError.innerText = 'ユーザー名とパスワードを入力してください。';
    return;
  }

  deleteFinalBtn.disabled = true;
  deleteFinalBtn.innerText = '削除中...';

  try {
    const res = await fetch('/delete_account', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        username: inputUsername,
        password: inputPassword
      })
    });

    const data = await res.json();

    if (!data.ok) {
      deleteConfirmModal.classList.remove('show');
      deleteConfirmModal.setAttribute('aria-hidden', 'true');

      deleteModal.classList.add('show');
      deleteModal.setAttribute('aria-hidden', 'false');

      deleteError.innerText = data.message || '削除に失敗しました。';

      deleteFinalBtn.disabled = false;
      deleteFinalBtn.innerText = '削除';

      return;
    }

    window.location.href = data.redirect;
  } catch (err) {
    deleteConfirmModal.classList.remove('show');
    deleteConfirmModal.setAttribute('aria-hidden', 'true');

    deleteModal.classList.add('show');
    deleteModal.setAttribute('aria-hidden', 'false');

    deleteError.innerText = '通信エラーが発生しました。';

    deleteFinalBtn.disabled = false;
    deleteFinalBtn.innerText = '削除';
  }
});

deleteModal.addEventListener('click', e => {
  if (e.target === deleteModal) {
    closeDeleteModals();
  }
});

deleteConfirmModal.addEventListener('click', e => {
  if (e.target === deleteConfirmModal) {
    closeDeleteModals();
  }
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    closeRoomModal();
    closeLogoutModal();
    closeUsernameModal();
    closeDeleteModals();
  }
});