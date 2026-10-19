/* Interacciones de presentación; no envían ni guardan información. */
(() => {
  const toast = document.querySelector('#toast');
  let toastTimer;
  const notify = message => {
    if (!toast) return;
    toast.textContent = message;
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.hidden = true; }, 5000);
  };
  const normalize = value => value.toLocaleLowerCase('es').normalize('NFD').replace(/[\u0300-\u036f]/g, '');

  document.querySelectorAll('[data-demo-pending]').forEach(button => button.addEventListener('click', () => {
    notify('Esta función está pendiente de conectar al sistema.');
  }));

  document.querySelectorAll('[data-filter-input]').forEach(input => input.addEventListener('input', () => {
    const term = normalize(input.value.trim());
    document.querySelectorAll(`[data-filter-item="${input.dataset.filterInput}"]`).forEach(item => {
      item.hidden = !normalize(item.textContent).includes(term);
    });
  }));

  document.querySelectorAll('[data-dialog-open]').forEach(button => button.addEventListener('click', () => {
    document.getElementById(button.dataset.dialogOpen)?.showModal();
  }));
  document.querySelectorAll('[data-dialog-close]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));

  const activityForm = document.querySelector('#activity-form');
  activityForm?.addEventListener('submit', event => {
    event.preventDefault();
    notify('Formulario válido como vista previa. El registro aún no se guarda.');
  });
  const commitmentToggle = document.querySelector('#commitment-toggle');
  const toggleCommitmentFields = () => document.querySelectorAll('.commitment-fields').forEach(row => { row.hidden = !commitmentToggle.checked; });
  commitmentToggle?.addEventListener('change', toggleCommitmentFields);
  activityForm?.addEventListener('reset', () => setTimeout(() => {
    toggleCommitmentFields();
    if (fileName) fileName.textContent = '';
  }, 0));
  const fileInput = document.querySelector('#evidence-file');
  const fileName = document.querySelector('#file-name');
  const checkFile = () => {
    const file = fileInput?.files[0];
    if (!file) return;
    if (!['image/jpeg', 'image/png'].includes(file.type) || file.size > 5 * 1024 * 1024) {
      fileInput.value = '';
      fileName.textContent = '';
      notify('Selecciona una imagen JPG o PNG de hasta 5 MB.');
      return;
    }
    fileName.textContent = `Seleccionado: ${file.name}`;
  };
  fileInput?.addEventListener('change', checkFile);
  const uploadZone = document.querySelector('.upload-zone');
  uploadZone?.addEventListener('dragover', event => event.preventDefault());
  uploadZone?.addEventListener('drop', event => {
    event.preventDefault();
    if (event.dataTransfer.files.length) {
      fileInput.files = event.dataTransfer.files;
      checkFile();
    }
  });

  const board = document.querySelector('.board');
  if (board) {
    const inputs = ['board-search', 'board-territory', 'board-person', 'board-area', 'board-date'].map(id => document.getElementById(id));
    const updateBoard = () => {
      const [search, territory, person, area, date] = inputs.map(input => normalize(input.value));
      board.querySelectorAll('[data-commitment]').forEach(card => {
        card.hidden = !normalize(card.textContent).includes(search)
          || (territory && normalize(card.dataset.territory) !== territory)
          || (person && normalize(card.dataset.responsible) !== person)
          || (area && normalize(card.dataset.area) !== area)
          || (date && !card.dataset.date.startsWith(date));
      });
      board.querySelectorAll('[data-board-column]').forEach(column => {
        column.querySelector('[data-count]').textContent = `(${column.querySelectorAll('[data-commitment]:not([hidden])').length})`;
      });
    };
    inputs.forEach(input => input.addEventListener(input.tagName === 'INPUT' ? 'input' : 'change', updateBoard));
    const drawer = document.getElementById('commitment-drawer');
    let selected;
    board.addEventListener('click', event => {
      const card = event.target.closest('[data-commitment]');
      if (!card) return;
      selected = card;
      const values = { 'detail-code': card.dataset.code, 'detail-requester': card.dataset.requester, 'detail-area': card.dataset.area, 'detail-territory': card.dataset.territory };
      Object.entries(values).forEach(([id, value]) => { document.getElementById(id).textContent = value; });
      document.getElementById('detail-state').value = card.dataset.state;
      document.getElementById('detail-responsible').value = card.dataset.responsible;
      document.getElementById('detail-date').value = card.dataset.date;
      drawer.querySelector('.history-entry').textContent = 'Sin observaciones registradas en esta demostración.';
      document.getElementById('drawer-comment').value = '';
      drawer.hidden = false;
      document.getElementById('drawer-close').focus();
    });
    const closeDrawer = () => { drawer.hidden = true; selected?.focus(); };
    document.getElementById('drawer-close').addEventListener('click', closeDrawer);
    document.addEventListener('keydown', event => { if (event.key === 'Escape' && !drawer.hidden) closeDrawer(); });
    document.getElementById('detail-state').addEventListener('change', event => {
      if (!selected) return;
      selected.dataset.state = event.target.value;
      const destination = [...board.querySelectorAll('[data-board-column]')].find(column => column.dataset.boardColumn === event.target.value);
      destination?.querySelector('.board-cards').appendChild(selected);
      updateBoard();
      notify('Estado actualizado solo en esta vista de demostración.');
    });
    document.getElementById('add-comment').addEventListener('click', () => {
      const input = document.getElementById('drawer-comment');
      if (!input.value.trim()) { input.focus(); return; }
      drawer.querySelector('.history-entry').textContent = `Observación de ejemplo: ${input.value.trim()}`;
      input.value = '';
      notify('Observación visible temporalmente; no se ha guardado.');
    });
    updateBoard();
  }

  document.querySelectorAll('[data-evidence-detail]').forEach(button => button.addEventListener('click', () => {
    const values = { 'evidence-code': button.dataset.code, 'evidence-title': button.dataset.title, 'evidence-status': button.dataset.status, 'evidence-observation': button.dataset.observation };
    Object.entries(values).forEach(([id, value]) => { document.getElementById(id).textContent = value; });
    document.getElementById('evidence-dialog').showModal();
  }));
  document.querySelectorAll('[data-review-item]').forEach(item => item.addEventListener('click', () => {
    document.querySelectorAll('[data-review-item]').forEach(other => other.classList.remove('selected'));
    item.classList.add('selected');
    document.getElementById('review-title').textContent = item.dataset.title;
    document.getElementById('review-date').textContent = item.dataset.date;
    document.getElementById('review-code').textContent = item.dataset.code;
  }));
})();
