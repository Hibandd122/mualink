function showToast(msg, ms = 2000) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), ms);
}

function copyLink(url) {
    navigator.clipboard.writeText(url).then(() => showToast('Đã copy! ✓'));
}

async function doFetch() {
    const btn = document.getElementById('fetch-btn');
    const badge = document.getElementById('status-badge');
    const body = document.getElementById('results-body');
    
    const urlInput = document.getElementById('mualink-url').value.trim();
    if (!urlInput) return showToast("Vui lòng nhập link!");

    btn.classList.add('loading');
    btn.disabled = true;
    badge.className = 'badge idle';
    badge.textContent = 'Đang xử lý...';
    body.className = 'results-body';
    
    // Create log container
    body.innerHTML = `
        <div class="log-container" id="log-container" style="font-family: monospace; font-size: 0.85rem; color: var(--text2); max-height: 200px; overflow-y: auto; padding-bottom: 10px; margin-bottom: 15px; border-bottom: 1px solid var(--border); background: rgba(0,0,0,0.2); padding: 10px; border-radius: 8px;">
            <div>⏳ Đang khởi tạo kết nối...</div>
        </div>
        <div id="final-results"></div>
    `;
    const logContainer = document.getElementById('log-container');
    const finalResults = document.getElementById('final-results');

    try {
        const url = encodeURIComponent(urlInput);
        
        // SSE implementation
        const source = new EventSource('/get-links-stream?url=' + url);
        
        source.onmessage = function(event) {
            const d = JSON.parse(event.data);
            
            if (d.step) {
                let color = "var(--text2)";
                if (d.step === "warn") color = "var(--amber)";
                if (d.step === "success") color = "var(--green)";
                
                const logEntry = document.createElement("div");
                logEntry.style.color = color;
                logEntry.style.marginBottom = "4px";
                logEntry.textContent = `> ${d.msg}`;
                logContainer.appendChild(logEntry);
                logContainer.scrollTop = logContainer.scrollHeight;
            }
            
            if (d.done) {
                source.close();
                btn.classList.remove('loading');
                btn.disabled = false;
                
                badge.className = 'badge success';
                badge.textContent = d.links.length + ' links';
                
                let h = '';
                d.links.forEach((l, i) => {
                    h += `<div class="link-item"><span class="link-num">${i + 1}</span><span class="link-url"><a href="${l}" target="_blank">${l}</a></span><button class="copy-btn" onclick="copyLink('${l}')">Copy</button></div>`;
                });
                if (d.note_id || d.proxy_used || d.elapsed_sec) {
                    h += `<div class="meta">`;
                    if (d.note_id) h += `<span>📝 Note: ${d.note_id}</span>`;
                    if (d.proxy_used) h += `<span>🌐 Proxy: ${d.proxy_used}</span>`;
                    if (d.elapsed_sec) h += `<span>⏱ ${d.elapsed_sec}s</span>`;
                    h += `</div>`;
                }
                finalResults.innerHTML = h;
            }
            
            if (d.error) {
                source.close();
                btn.classList.remove('loading');
                btn.disabled = false;
                badge.className = 'badge error';
                badge.textContent = 'Lỗi';
                finalResults.innerHTML = `<span>❌ ${d.error || 'Không rõ lỗi'}</span>`;
            }
        };
        
        source.onerror = function(e) {
            if (source.readyState === EventSource.CLOSED) return;
            source.close();
            btn.classList.remove('loading');
            btn.disabled = false;
            badge.className = 'badge error';
            badge.textContent = 'Mất kết nối';
            const logEntry = document.createElement("div");
            logEntry.style.color = "var(--red)";
            logEntry.textContent = `> ❌ Mất kết nối tới server (SSE Error)`;
            logContainer.appendChild(logEntry);
        };
        
    } catch (e) {
        btn.classList.remove('loading');
        btn.disabled = false;
        badge.className = 'badge error';
        badge.textContent = 'Network Error';
        body.innerHTML = '<span>❌ Không kết nối được server</span>';
    }
}
