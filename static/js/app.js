(() => {
  const $ = id => document.getElementById(id);
  const drop = $('drop'), fileInput = $('file-input'), list = $('list');
  const items = [];
  const CONCURRENCY = 3;
  let inFlight = 0;
  const queue = [];

  function currentSettings() {
    return {
      format: $('format').value,
      quality: $('quality').value,
      mode: $('mode').value,
      long_edge: $('long_edge').value,
      percent: $('percent').value,
      width: $('width').value,
      height: $('height').value,
      sharpen: $('sharpen').value,
      no_enlarge: $('no_enlarge').checked ? '1' : '0',
      reduce_colors: $('reduce_colors').checked ? '1' : '0',
      colors: $('colors').value,
    };
  }

  $('mode').addEventListener('change', () => {
    const m = $('mode').value;
    $('f-long-edge').hidden = m !== 'long_edge';
    $('f-percent').hidden = m !== 'percent';
    $('f-width').hidden = m !== 'fit';
    $('f-height').hidden = m !== 'fit';
  });
  $('format').addEventListener('change', () => {
    const jpeg = $('format').value === 'jpeg';
    $('f-quality').hidden = !jpeg;
    $('f-colors').hidden = jpeg;
  });
  $('reduce_colors').addEventListener('change', () => {
    $('colors').disabled = !$('reduce_colors').checked;
  });

  drop.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => { addFiles(fileInput.files); fileInput.value = ''; });
  ['dragover', 'dragenter'].forEach(ev =>
    drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('hover'); }));
  ['dragleave', 'drop'].forEach(ev =>
    drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('hover'); }));
  drop.addEventListener('drop', e => addFiles(e.dataTransfer.files));

  function addFiles(fileList) {
    for (const file of fileList) {
      if (!/\.(png|jpe?g)$/i.test(file.name) &&
          !['image/png', 'image/jpeg'].includes(file.type)) continue;
      const item = { file, row: buildRow(file), token: null, url: null, done: false, failed: false };
      items.push(item);
      list.appendChild(item.row.el);
      enqueue(item);
    }
    updateToolbar();
  }
  window.addFiles = addFiles;

  function buildRow(file) {
    const el = document.createElement('div');
    el.className = 'row';
    el.innerHTML = `
      <img class="thumb" alt="">
      <div class="info">
        <div class="name"></div>
        <div class="meta"></div>
        <div class="error" hidden></div>
      </div>
      <span class="saved" hidden></span>
      <span class="status">queued</span>
      <span class="spinner" hidden></span>
      <a class="dl" hidden download>Download</a>`;
    el.querySelector('.name').textContent = file.name;
    el.querySelector('.meta').textContent = fmtBytes(file.size);
    el.querySelector('.thumb').src = URL.createObjectURL(file);
    return {
      el,
      meta: el.querySelector('.meta'),
      error: el.querySelector('.error'),
      saved: el.querySelector('.saved'),
      status: el.querySelector('.status'),
      spinner: el.querySelector('.spinner'),
      dl: el.querySelector('.dl'),
    };
  }

  function fmtBytes(n) {
    if (n >= 1048576) return (n / 1048576).toFixed(2) + ' MB';
    if (n >= 1024) return (n / 1024).toFixed(0) + ' KB';
    return n + ' B';
  }

  function enqueue(item) {
    item.done = item.failed = false;
    item.row.status.textContent = 'queued';
    item.row.status.hidden = false;
    item.row.dl.hidden = true;
    item.row.saved.hidden = true;
    item.row.error.hidden = true;
    queue.push(item);
    pump();
  }

  function pump() {
    while (inFlight < CONCURRENCY && queue.length) {
      const item = queue.shift();
      inFlight++;
      processItem(item).finally(() => { inFlight--; pump(); updateToolbar(); });
    }
  }

  async function processItem(item) {
    const { row } = item;
    row.status.textContent = 'processing…';
    row.spinner.hidden = false;
    try {
      const fd = new FormData();
      fd.append('file', item.file, item.file.name);
      for (const [k, v] of Object.entries(currentSettings())) fd.append(k, v);

      const resp = await fetch('/api/process', { method: 'POST', body: fd });
      if (!resp.ok) throw new Error((await resp.text()).replace(/<[^>]*>/g, ' ').trim() || `HTTP ${resp.status}`);

      const blob = await resp.blob();
      if (item.url) URL.revokeObjectURL(item.url);
      item.url = URL.createObjectURL(blob);
      item.token = resp.headers.get('X-Token');
      item.filename = resp.headers.get('X-Filename') || 'exported.png';

      const origB = +resp.headers.get('X-Original-Bytes');
      const newB = +resp.headers.get('X-New-Bytes');
      const savedPct = origB ? Math.round((1 - newB / origB) * 100) : 0;

      row.meta.textContent =
        `${resp.headers.get('X-Original-Dims')} · ${fmtBytes(origB)}  →  ` +
        `${resp.headers.get('X-New-Dims')} · ${fmtBytes(newB)}`;
      row.saved.textContent = savedPct >= 0 ? `−${savedPct}%` : `+${-savedPct}%`;
      row.saved.classList.toggle('grew', savedPct < 0);
      row.saved.hidden = false;
      row.dl.href = item.url;
      row.dl.download = item.filename;
      row.dl.hidden = false;
      row.status.hidden = true;
      item.done = true;
    } catch (err) {
      row.error.textContent = err.message || 'processing failed';
      row.error.hidden = false;
      row.status.hidden = true;
      item.failed = true;
    } finally {
      row.spinner.hidden = true;
    }
  }

  function updateToolbar() {
    const doneTokens = items.filter(i => i.done && i.token);
    $('btn-zip').disabled = doneTokens.length === 0;
    $('btn-reprocess').disabled = items.length === 0;
    $('btn-clear').disabled = items.length === 0;
  }

  $('btn-zip').addEventListener('click', () => {
    const tokens = items.filter(i => i.done && i.token).map(i => i.token);
    if (tokens.length) window.location = '/api/zip?tokens=' + tokens.join(',');
  });

  $('btn-reprocess').addEventListener('click', () => {
    items.forEach(enqueue);
    updateToolbar();
  });

  $('btn-clear').addEventListener('click', () => {
    items.forEach(i => i.url && URL.revokeObjectURL(i.url));
    items.length = 0;
    queue.length = 0;
    list.innerHTML = '';
    updateToolbar();
  });
})();
