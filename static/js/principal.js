
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

  const normalize = value => value
    .toLocaleLowerCase('es')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');

  // =========================================================
  // 1. BUSCADOR DINÁMICO DE TABLAS (INSTRUCCIÓN 1C)
  // =========================================================

  document.querySelectorAll('[data-filtro-tabla]').forEach(input => {
    const tableId = input.dataset.filtroTabla;
    const table = document.getElementById(tableId);

    if (!table) {
      console.warn(`No se encontró la tabla con id="${tableId}".`);
      return;
    }

    const rows = table.querySelectorAll('tbody tr');

    const filterTable = () => {
      const term = normalize(input.value.trim());

      rows.forEach(row => {
        const rowText = normalize(row.textContent);
        row.hidden = !rowText.includes(term);
      });
    };

    input.addEventListener('input', filterTable);
  });

  // =========================================================
  // 2. FORMATEADOR AUTOMÁTICO DE RUT CHILENO (INSTRUCCIÓN 1C)
  // =========================================================

  const cleanRut = value => {
    return value
      .toUpperCase()
      .replace(/[^0-9K]/g, '');
  };

  const formatRut = value => {
    const clean = cleanRut(value);

    if (!clean) return '';

    // Mientras exista un solo carácter, no se agrega guion.
    if (clean.length === 1) return clean;

    // El último carácter corresponde al dígito verificador.
    const body = clean.slice(0, -1).replace(/K/g, '');
    const verifier = clean.slice(-1);

    if (!body) return verifier;

    // Separación de miles mediante puntos.
    const formattedBody = body.replace(/\B(?=(\d{3})+(?!\d))/g, '.');

    return `${formattedBody}-${verifier}`;
  };

  const getFormattedCaretPosition = (formatted, characterCount) => {
    if (characterCount <= 0) return 0;

    let count = 0;

    for (let i = 0; i < formatted.length; i++) {
      if (/[0-9K]/.test(formatted[i])) {
        count++;
      }

      if (count === characterCount) {
        return i + 1;
      }
    }

    return formatted.length;
  };

  document.querySelectorAll('.input-rut').forEach(input => {
    // Formatea también los valores que Django carga inicialmente.
    input.value = formatRut(input.value);

    input.addEventListener('input', () => {
      const cursorPosition = input.selectionStart ?? input.value.length;

      // Cuenta los caracteres válidos situados antes del cursor.
      const charactersBeforeCursor = cleanRut(
        input.value.slice(0, cursorPosition)
      ).length;

      const formatted = formatRut(input.value);

      input.value = formatted;

      // Conserva la posición aproximada del cursor.
      const newCursorPosition = getFormattedCaretPosition(
        formatted,
        charactersBeforeCursor
      );

      input.setSelectionRange(newCursorPosition, newCursorPosition);
    });

    // Asegura el formato definitivo al abandonar el campo.
    input.addEventListener('blur', () => {
      input.value = formatRut(input.value);
    });
  });

  // =========================================================
  // 3. FUNCIONALIDADES EXISTENTES
  // =========================================================

  document.querySelectorAll('[data-demo-pending]').forEach(button =>
    button.addEventListener('click', () => {
      notify('Esta función está pendiente de conectar al sistema.');
    })
  );

  // Buscador anterior: se conserva para las vistas que lo utilizan.
  document.querySelectorAll('[data-filter-input]').forEach(input =>
    input.addEventListener('input', () => {
      const term = normalize(input.value.trim());

      document.querySelectorAll(
        `[data-filter-item="${input.dataset.filterInput}"]`
      ).forEach(item => {
        item.hidden = !normalize(item.textContent).includes(term);
      });
    })
  );

  document.querySelectorAll('[data-dialog-open]').forEach(button =>
    button.addEventListener('click', () => {
      document.getElementById(button.dataset.dialogOpen)?.showModal();
    })
  );

  document.querySelectorAll('[data-dialog-close]').forEach(button =>
    button.addEventListener('click', () => {
      button.closest('dialog').close();
    })
  );

  const activityForm = document.querySelector('#activity-form');
  const commitmentToggle = document.querySelector('#commitment-toggle');

  const toggleCommitmentFields = () => {
    document.querySelectorAll('.commitment-fields').forEach(row => {
      row.hidden = !commitmentToggle.checked;
    });
  };

  commitmentToggle?.addEventListener('change', toggleCommitmentFields);

  const fileInput = document.querySelector('#evidence-file');
  const fileName = document.querySelector('#file-name');

  activityForm?.addEventListener('reset', () => setTimeout(() => {
    toggleCommitmentFields();

    if (fileName) fileName.textContent = '';
  }, 0));

  const checkFile = () => {
    const file = fileInput?.files[0];

    if (!file) return;

    if (
      !['image/jpeg', 'image/png'].includes(file.type) ||
      file.size > 5 * 1024 * 1024
    ) {
      fileInput.value = '';

      if (fileName) fileName.textContent = '';

      notify('Selecciona una imagen JPG o PNG de hasta 5 MB.');
      return;
    }

    if (fileName) {
      fileName.textContent = `Seleccionado: ${file.name}`;
    }
  };

  fileInput?.addEventListener('change', checkFile);

  const uploadZone = document.querySelector('.upload-zone');

  uploadZone?.addEventListener('dragover', event => {
    event.preventDefault();
  });

  uploadZone?.addEventListener('drop', event => {
    event.preventDefault();

    if (event.dataTransfer.files.length) {
      fileInput.files = event.dataTransfer.files;
      checkFile();
    }
  });

  // =========================================================
  // 4. TABLERO DE COMPROMISOS
  // =========================================================

  const board = document.querySelector('.board');

  if (board) {
    const inputs = [
      'board-search',
      'board-territory',
      'board-person',
      'board-area',
      'board-date'
    ].map(id => document.getElementById(id));

    const updateBoard = () => {
      const [search, territory, person, area, date] =
        inputs.map(input => normalize(input.value));

      board.querySelectorAll('[data-commitment]').forEach(card => {
        card.hidden =
          !normalize(card.textContent).includes(search)
          || (territory && normalize(card.dataset.territory) !== territory)
          || (person && normalize(card.dataset.responsible) !== person)
          || (area && normalize(card.dataset.area) !== area)
          || (date && !card.dataset.date.startsWith(date));
      });

      board.querySelectorAll('[data-board-column]').forEach(column => {
        column.querySelector('[data-count]').textContent =
          `(${column.querySelectorAll('[data-commitment]:not([hidden])').length})`;
      });
    };

    inputs.forEach(input => {
      input.addEventListener(
        input.tagName === 'INPUT' ? 'input' : 'change',
        updateBoard
      );
    });

    const drawer = document.getElementById('commitment-drawer');
    let selected;

    board.addEventListener('click', event => {
      const card = event.target.closest('[data-commitment]');

      if (!card) return;

      selected = card;

      const values = {
        'detail-code': card.dataset.code,
        'detail-requester': card.dataset.requester,
        'detail-area': card.dataset.area,
        'detail-territory': card.dataset.territory
      };

      Object.entries(values).forEach(([id, value]) => {
        document.getElementById(id).textContent = value;
      });

      document.getElementById('detail-state').value = card.dataset.state;
      document.getElementById('detail-responsible').value = card.dataset.responsible;
      document.getElementById('detail-date').value = card.dataset.date;

      drawer.querySelector('.history-entry').textContent =
        'Sin observaciones registradas en esta demostración.';

      document.getElementById('drawer-comment').value = '';
      drawer.hidden = false;
      document.getElementById('drawer-close').focus();
    });

    const closeDrawer = () => {
      drawer.hidden = true;
      selected?.focus();
    };

    document.getElementById('drawer-close').addEventListener(
      'click',
      closeDrawer
    );

    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !drawer.hidden) {
        closeDrawer();
      }
    });

    document.getElementById('detail-state').addEventListener(
      'change',
      event => {
        if (!selected) return;

        selected.dataset.state = event.target.value;

        const destination = [...board.querySelectorAll('[data-board-column]')]
          .find(column => column.dataset.boardColumn === event.target.value);

        destination?.querySelector('.board-cards').appendChild(selected);

        updateBoard();
        notify('Estado actualizado solo en esta vista de demostración.');
      }
    );

    document.getElementById('add-comment').addEventListener('click', () => {
      const input = document.getElementById('drawer-comment');

      if (!input.value.trim()) {
        input.focus();
        return;
      }

      drawer.querySelector('.history-entry').textContent =
        `Observación de ejemplo: ${input.value.trim()}`;

      input.value = '';
      notify('Observación visible temporalmente; no se ha guardado.');
    });

    updateBoard();
  }

  // =========================================================
  // 5. DETALLE DE EVIDENCIAS
  // =========================================================

  document.querySelectorAll('[data-evidence-detail]').forEach(button => {
    button.addEventListener('click', () => {
      const values = {
        'evidence-code': button.dataset.code,
        'evidence-title': button.dataset.title,
        'evidence-status': button.dataset.status,
        'evidence-observation': button.dataset.observation
      };

      Object.entries(values).forEach(([id, value]) => {
        document.getElementById(id).textContent = value;
      });

      document.getElementById('evidence-dialog').showModal();
    });
  });

  // =========================================================
  // 6. ELEMENTOS DE REVISIÓN
  // =========================================================

  document.querySelectorAll('[data-review-item]').forEach(item => {
    item.addEventListener('click', () => {
      document.querySelectorAll('[data-review-item]').forEach(other => {
        other.classList.remove('selected');
      });

      item.classList.add('selected');

      document.getElementById('review-title').textContent = item.dataset.title;
      document.getElementById('review-date').textContent = item.dataset.date;
      document.getElementById('review-code').textContent = item.dataset.code;
    });
  });
})();
