/* 笔驭 BiYu — 前端逻辑 */

const API = '';
let currentBook = null;
let currentChapter = null;

// ── 初始化 ──────────────────────────────────────────────────────────────────

async function init() {
    await loadBooks();
    document.getElementById('book-list').addEventListener('change', onBookChange);
}

async function loadBooks() {
    const res = await fetch(`${API}/api/books`);
    const books = await res.json();
    const sel = document.getElementById('book-list');
    sel.innerHTML = '<option value="">选择一本书...</option>';
    books.forEach(b => {
        const opt = document.createElement('option');
        opt.value = b.name;
        opt.textContent = b.title || b.name;
        sel.appendChild(opt);
    });
}

async function onBookChange() {
    const sel = document.getElementById('book-list');
    currentBook = sel.value;
    currentChapter = null;
    if (!currentBook) return;
    await loadChapters();
    showWelcome();
}

async function loadChapters() {
    if (!currentBook) return;
    const res = await fetch(`${API}/api/books/${encodeURIComponent(currentBook)}/chapters`);
    const chapters = await res.json();
    const list = document.getElementById('chapter-list');
    list.innerHTML = '';

    chapters.forEach(ch => {
        const div = document.createElement('div');
        div.className = 'ch-item';
        div.dataset.chapter = ch.chapter;
        let badges = '';
        if (ch.has_content) badges += '<span class="badge ok">已生成</span>';
        else if (ch.has_outline) badges += '<span class="badge">待生成</span>';
        div.innerHTML = `<span>第${ch.chapter}章</span>${badges}`;
        div.onclick = () => selectChapter(ch.chapter);
        list.appendChild(div);
    });
}

// ── 章节选择 ────────────────────────────────────────────────────────────────

async function selectChapter(n) {
    currentChapter = n;

    // 高亮
    document.querySelectorAll('.ch-item').forEach(el => {
        el.classList.toggle('active', parseInt(el.dataset.chapter) === n);
    });

    document.getElementById('welcome').style.display = 'none';
    document.getElementById('editor').style.display = '';
    document.getElementById('editor-title').textContent = `第 ${n} 章`;

    // 加载大纲
    const outlineRes = await fetch(`${API}/api/books/${encodeURIComponent(currentBook)}/chapters/${n}/outline`);
    if (outlineRes.ok) {
        const data = await outlineRes.json();
        document.getElementById('outline-text').value = data.content || '';
    } else {
        document.getElementById('outline-text').value = '';
    }

    // 加载正文
    const contentRes = await fetch(`${API}/api/books/${encodeURIComponent(currentBook)}/chapters/${n}/content`);
    if (contentRes.ok) {
        const data = await contentRes.json();
        document.getElementById('content-display').textContent = data.content || '';
    } else {
        document.getElementById('content-display').textContent = '（未生成）';
    }

    // 加载元数据
    const metaRes = await fetch(`${API}/api/books/${encodeURIComponent(currentBook)}/chapters/${n}/outline`);
    try {
        const bk = currentBook;
        const metaPath = `${API}/api/books/${encodeURIComponent(bk)}/chapters`;
        // 元数据从 chapters 列表获取
        const chList = await (await fetch(metaPath)).json();
        const chInfo = chList.find(c => c.chapter === n);
        document.getElementById('meta-display').textContent = chInfo ? JSON.stringify(chInfo, null, 2) : '（无）';
    } catch {
        document.getElementById('meta-display').textContent = '（无）';
    }

    switchTab('outline');
}

// ── Tab 切换 ────────────────────────────────────────────────────────────────

function switchTab(tab) {
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    document.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'));
    document.getElementById(`tab-${tab}`).classList.add('active');
}

// ── 大纲保存 ────────────────────────────────────────────────────────────────

async function saveOutline() {
    if (!currentBook || !currentChapter) return;
    const content = document.getElementById('outline-text').value;
    await fetch(`${API}/api/books/${encodeURIComponent(currentBook)}/chapters/${currentChapter}/outline`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({content}),
    });
    alert('大纲已保存');
    await loadChapters();
}

// ── 生成章节 ────────────────────────────────────────────────────────────────

async function generateChapter() {
    if (!currentBook || !currentChapter) return;

    const progressPanel = document.getElementById('progress-panel');
    const progressLog = document.getElementById('progress-log');
    progressPanel.style.display = '';
    progressLog.innerHTML = '';

    const evtSource = new EventSource(
        `${API}/api/books/${encodeURIComponent(currentBook)}/chapters/${currentChapter}/generate`
    );

    evtSource.onmessage = (e) => {
        if (e.data === '[DONE]') {
            evtSource.close();
            addProgress(progressLog, '生成完成', 'done');
            loadChapters();
            selectChapter(currentChapter);
            return;
        }
        try {
            const data = JSON.parse(e.data);
            if (data.type === 'progress') {
                addProgress(progressLog, `[${data.stage}] ${data.message}`);
            } else if (data.type === 'done') {
                addProgress(progressLog, `完成: ${data.word_count}字, ¥${data.cost_cny?.toFixed(4)}`, 'done');
            } else if (data.type === 'error') {
                addProgress(progressLog, `错误: ${data.error}`, 'error');
            }
        } catch {}
    };

    evtSource.onerror = () => {
        evtSource.close();
        addProgress(progressLog, '连接断开', 'error');
    };
}

// ── 一致性检查 ──────────────────────────────────────────────────────────────

async function checkChapter() {
    if (!currentBook || !currentChapter) return;
    const res = await fetch(`${API}/api/books/${encodeURIComponent(currentBook)}/chapters/${currentChapter}/check`, {
        method: 'POST',
    });
    const data = await res.json();
    if (data.issues && data.issues.length > 0) {
        alert(`发现 ${data.issues.length} 个问题:\n` + data.issues.map(i => `- [${i.severity}] ${i.character}: ${i.rule}`).join('\n'));
    } else {
        alert('一致性检查通过');
    }
}

// ── 刷新设定 ────────────────────────────────────────────────────────────────

async function refreshChapter() {
    if (!currentBook || !currentChapter) return;
    const res = await fetch(`${API}/api/books/${encodeURIComponent(currentBook)}/chapters/${currentChapter}/refresh`, {
        method: 'POST',
    });
    const data = await res.json();
    alert(data.success ? '设定刷新成功' : '设定刷新失败');
}

// ── 批量生成 ────────────────────────────────────────────────────────────────

function startAutoGenerate() {
    if (!currentBook) { alert('请先选择一本书'); return; }

    const fromVal = prompt('起始章节号:');
    const toVal = prompt('结束章节号:');
    if (!fromVal || !toVal) return;

    const progressPanel = document.getElementById('progress-panel');
    const progressLog = document.getElementById('progress-log');
    progressPanel.style.display = '';
    progressLog.innerHTML = '';

    fetch(`${API}/api/books/${encodeURIComponent(currentBook)}/auto`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({from: parseInt(fromVal), to: parseInt(toVal)}),
    }).then(res => {
        const reader = res.body.getReader();
        const decoder = new TextDecoder();

        function read() {
            reader.read().then(({done, value}) => {
                if (done) {
                    addProgress(progressLog, '批量生成结束', 'done');
                    loadChapters();
                    return;
                }
                const text = decoder.decode(value);
                text.split('\n').forEach(line => {
                    if (line.startsWith('data: ') && line !== 'data: [DONE]') {
                        try {
                            const data = JSON.parse(line.slice(6));
                            if (data.type === 'chapter_done') {
                                addProgress(progressLog, `ch${data.chapter} 完成: ${data.word_count}字, ¥${data.cost_cny?.toFixed(4)}`, 'done');
                            } else if (data.type === 'all_done') {
                                addProgress(progressLog, `全部完成: ${data.total}章, 总成本 ¥${data.total_cost?.toFixed(4)}`, 'done');
                            } else if (data.type === 'error') {
                                addProgress(progressLog, `错误: ${data.error}`, 'error');
                            }
                        } catch {}
                    }
                });
                read();
            });
        }
        read();
    });
}

// ── 刷新列表 ────────────────────────────────────────────────────────────────

async function refreshAll() {
    await loadBooks();
    if (currentBook) await loadChapters();
}

// ── 辅助函数 ────────────────────────────────────────────────────────────────

function addProgress(container, text, cls = '') {
    const div = document.createElement('div');
    div.className = 'progress-line' + (cls ? ' ' + cls : '');
    div.textContent = text;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function showWelcome() {
    document.getElementById('welcome').style.display = '';
    document.getElementById('editor').style.display = 'none';
}

// ── 启动 ────────────────────────────────────────────────────────────────────

init();
