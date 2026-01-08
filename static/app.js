// NovaRAG Flask - Frontend JavaScript

const API_BASE = '/api';
let currentQuestion = '';
let currentAnswer = '';

// Security: HTML escaping function to prevent XSS attacks
function escapeHtml(unsafe) {
    if (typeof unsafe !== 'string') {
        unsafe = String(unsafe);
    }
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function getSafetyPrefs() {
    const rawAudit = localStorage.getItem('nova_safety_audit');
    const rawStrict = localStorage.getItem('nova_safety_strict');
    const rawMetadata = localStorage.getItem('nova_show_metadata');
    return {
        citation_audit_enabled: rawAudit === null ? true : rawAudit === '1',
        citation_strict_enabled: rawStrict === null ? true : rawStrict === '1',
        show_metadata: rawMetadata === null ? true : rawMetadata === '1'
    };
}

function setSafetyPrefs(prefs) {
    localStorage.setItem('nova_safety_audit', prefs.citation_audit_enabled ? '1' : '0');
    localStorage.setItem('nova_safety_strict', prefs.citation_strict_enabled ? '1' : '0');
    localStorage.setItem('nova_show_metadata', prefs.show_metadata ? '1' : '0');
}

async function syncSafetyPrefsToServer(prefs) {
    try {
        await fetch(`${API_BASE}/safety`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(prefs)
        });
    } catch (e) {
        console.error('Failed to sync safety prefs:', e);
    }
}

function applySafetyPrefsToUI(prefs) {
    const auditEl = document.getElementById('toggle-audit');
    const strictEl = document.getElementById('toggle-strict');
    const metadataEl = document.getElementById('toggle-metadata');
    if (auditEl) auditEl.checked = !!prefs.citation_audit_enabled;
    if (strictEl) strictEl.checked = !!prefs.citation_strict_enabled;
    if (metadataEl) metadataEl.checked = prefs.show_metadata !== false;
}

function readSafetyPrefsFromUI() {
    const auditEl = document.getElementById('toggle-audit');
    const strictEl = document.getElementById('toggle-strict');
    const metadataEl = document.getElementById('toggle-metadata');
    return {
        citation_audit_enabled: auditEl ? !!auditEl.checked : true,
        citation_strict_enabled: strictEl ? !!strictEl.checked : true,
        show_metadata: metadataEl ? !!metadataEl.checked : true
    };
}

function isMetadataVisible() {
    const metadataEl = document.getElementById('toggle-metadata');
    return metadataEl ? metadataEl.checked : true;
}

function initSafetyToggles() {
    const auditEl = document.getElementById('toggle-audit');
    const strictEl = document.getElementById('toggle-strict');
    const metadataEl = document.getElementById('toggle-metadata');

    const prefs = getSafetyPrefs();
    applySafetyPrefsToUI(prefs);
    syncSafetyPrefsToServer(prefs);

    const onChange = async () => {
        const next = readSafetyPrefsFromUI();
        setSafetyPrefs(next);
        await syncSafetyPrefsToServer(next);
        updateStatus();
    };

    if (auditEl) auditEl.addEventListener('change', onChange);
    if (strictEl) strictEl.addEventListener('change', onChange);
    
    // Metadata toggle - show/hide traced sources in existing messages
    if (metadataEl) {
        metadataEl.addEventListener('change', () => {
            const prefs = readSafetyPrefsFromUI();
            setSafetyPrefs(prefs);
            // Toggle visibility of traced-sources in all messages
            document.querySelectorAll('.traced-sources, .retrieval-score, .response-metadata').forEach(el => {
                el.style.display = prefs.show_metadata ? '' : 'none';
            });
        });
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initSafetyToggles();
    updateStatus();
    loadFavorites();
    setInterval(updateStatus, 5000);
    const metrics = document.getElementById('metrics-btn');
    if (metrics) metrics.addEventListener('click', showMetrics);
});

// Update system status
async function updateStatus() {
    try {
        const res = await fetch(`${API_BASE}/status`);
        const data = await res.json();
        
        // Update connection status
        const statusEl = document.getElementById('connection-status');
        // Handle lm_studio as array [boolean, message] or boolean
        let lmStatus = data.lm_studio;
        if (Array.isArray(lmStatus)) {
            const [connected, msg] = lmStatus;
            statusEl.innerHTML = connected 
                ? `<span class="status-ok">✅ Advisory system · Human decision required</span>`
                : `<span class="status-err">❌ Disconnected</span>`;
        } else if (typeof lmStatus === 'boolean') {
            statusEl.innerHTML = lmStatus 
                ? '<span class="status-ok">✅ Advisory system · Human decision required</span>'
                : '<span class="status-err">❌ Disconnected</span>';
        } else if (lmStatus === undefined || lmStatus === null) {
            statusEl.innerHTML = '<span class="status-ok">✅ Advisory system · Human decision required</span>';
        } else {
            statusEl.innerHTML = '<span class="status-ok">✅ Advisory system · Human decision required</span>';
        }
        
        // Update current model display (hidden - not needed for user)
        const modelEl = document.getElementById('current-model');
        if (modelEl) {
            modelEl.style.display = 'none';
        }

        // Update safety flags (citation audit / strict mode)
        const safetyEl = document.getElementById('safety-flags');
        if (safetyEl) {
            const safety = data.safety || {};
            const auditOn = (safety.citation_audit_enabled === true) ? 'ON'
                : (safety.citation_audit_enabled === false) ? 'OFF'
                : '--';
            const strictOn = (safety.citation_strict_enabled === true) ? 'ON'
                : (safety.citation_strict_enabled === false) ? 'OFF'
                : '--';
            const anyOff = (auditOn === 'OFF' || strictOn === 'OFF');
            const hint = anyOff
                ? `<span class="safety-hint safety-hint-warn">(UI toggles • exploratory)</span>`
                : `<span class="safety-hint">(UI toggles)</span>`;
            safetyEl.innerHTML = `<strong>Safety:</strong> Audit ${auditOn} | Strict ${strictOn} ${hint}`;
        }
        
        // Update session info
        if (data.session_active) {
            document.getElementById('session-info').style.display = 'block';
            document.getElementById('session-topic').textContent = `Topic: ${data.current_session}`;
            document.getElementById('session-turns').textContent = `Turns: ${data.session_turns}`;
            document.getElementById('reset-session-btn').style.display = 'block';
            document.getElementById('favorite-btn').style.display = 'block';
        } else {
            document.getElementById('session-info').style.display = 'none';
            document.getElementById('reset-session-btn').style.display = 'none';
        }
        
        // Update recent sessions
        updateRecentSessions(data.recent_sessions);
        
        // Update recent searches
        updateRecentSearches(data.recent_searches);
    } catch (e) {
        console.error('Failed to update status:', e);
    }
}

// Update recent sessions display
function updateRecentSessions(sessions) {
    const container = document.getElementById('recent-sessions');
    if (!sessions || sessions.length === 0) {
        container.innerHTML = '<p class="empty">No sessions yet</p>';
        return;
    }
    
    container.innerHTML = sessions.map(s => 
        `<div class="list-item" onclick="loadSession('${s.id}')">${s.label}</div>`
    ).join('');
}

// Update recent searches display
function updateRecentSearches(searches) {
    const container = document.getElementById('recent-searches');
    if (!searches || searches.length === 0) {
        container.innerHTML = '<p class="empty">No searches yet</p>';
        return;
    }
    
    container.innerHTML = searches.map(s => 
        `<div class="list-item" onclick="setQuery('${s.replace(/'/g, "\\'")}')">${s.substring(0, 30)}...</div>`
    ).join('');
}

// Set query from button click
function setQuery(query) {
    document.getElementById('question-input').value = query;
    document.getElementById('question-input').focus();
}

// Submit question
async function submitQuestion() {
    const question = document.getElementById('question-input').value.trim();
    const mode = document.getElementById('mode-select').value;
    
    if (!question) return;
    
    currentQuestion = question;
    
    // Add user message to chat
    addMessageToChat(question, 'user');
    document.getElementById('question-input').value = '';
    
    // Show loading
    const loadingMsg = addMessageToChat('Thinking...', 'assistant');
    
    try {
        const safetyPrefs = readSafetyPrefsFromUI();
        const res = await fetch(`${API_BASE}/ask`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question, mode, ...safetyPrefs })
        });
        
        const data = await res.json();
        
        if (res.ok) {
            currentAnswer = data.answer;
            loadingMsg.remove();
            addMessageToChat(data.answer, 'assistant', data.model_used, data.confidence, data.audit_status, data.effective_safety, data);
            document.getElementById('confidence-display').style.display = 'block';
            document.getElementById('confidence-value').textContent = data.confidence;
            
            // Show favorite button and quick feedback bar
            document.getElementById('favorite-btn').style.display = 'block';
            document.getElementById('quick-feedback-bar').style.display = 'block';
        } else {
            loadingMsg.remove();
            addMessageToChat(`❌ Error: ${data.error}`, 'assistant');
        }
    } catch (e) {
        loadingMsg.remove();
        addMessageToChat(`❌ Connection error: ${e.message}`, 'assistant');
    }
    
    updateStatus();
}

// Format answer - handles both string and dict (refusal schema)
function formatAnswer(answer) {
    if (typeof answer === 'string') {
        // Clean up inline JSON/dict sources that appear in the text
        let cleaned = answer;
        // Remove [Sources: {...}] patterns
        cleaned = cleaned.replace(/\s*\|\s*\[Sources:.*?\]\]?/gi, '');
        cleaned = cleaned.replace(/\[Sources:.*?\]\]?/gi, '');
        // Remove {'source': ...} dict patterns
        cleaned = cleaned.replace(/\{'source':\s*'[^']*',\s*'page':\s*\d+\}/g, '');
        // Remove trailing pipes and clean up
        cleaned = cleaned.replace(/\s*\|\s*$/g, '');
        cleaned = cleaned.replace(/\s*\|\s*\|/g, ' |');
        return escapeHtml(cleaned.trim());
    }
    if (typeof answer === 'object' && answer !== null) {
        // Handle refusal schema
        if (answer.response_type === 'refusal') {
            return `⚠️ <strong>${escapeHtml(answer.reason || 'Request Declined')}</strong><br><br>${escapeHtml(answer.message || 'Unable to process this request.')}`;
        }
        
        // Handle full diagnostic response with query/context/response structure
        if (answer.response && answer.response.analysis) {
            const analysis = answer.response.analysis;
            let html = '<div class="diagnostic-response">';
            
            // Probable causes section
            if (analysis.probable_causes && analysis.probable_causes.length > 0) {
                html += '<div class="probable-causes"><strong>🔍 Probable Causes:</strong><ol>';
                for (const cause of analysis.probable_causes) {
                    html += `<li>`;
                    html += `<strong>${escapeHtml(cause.cause_type)}</strong> (${escapeHtml(String(cause.probability))}% probability)`;
                    if (cause.description) {
                        html += `<br><span class="cause-description">${escapeHtml(cause.description)}</span>`;
                    }
                    html += `</li>`;
                }
                html += '</ol></div>';
            }
            
            // Diagnostic steps section
            if (analysis.diagnostic_steps && analysis.diagnostic_steps.length > 0) {
                html += '<div class="diagnostic-steps"><strong>🔧 Diagnostic Steps:</strong><ol>';
                for (const step of analysis.diagnostic_steps) {
                    html += `<li>${escapeHtml(step.description)}</li>`;
                }
                html += '</ol></div>';
            }
            
            html += '</div>';
            return html;
        }
        
        // Handle troubleshooting/procedure response (steps, risks, verification, why)
        if (answer.steps && Array.isArray(answer.steps)) {
            let html = '<div class="troubleshoot-response">';
            
            // Risks/Warnings first (safety)
            if (answer.risks && answer.risks.length > 0) {
                html += '<div class="caution-box"><strong>⚠️ Safety Warnings:</strong><ul>';
                for (const r of answer.risks) {
                    html += `<li>${escapeHtml(r)}</li>`;
                }
                html += '</ul></div>';
            }
            
            // Steps
            html += '<div class="steps-section"><strong>🔧 Diagnostic Steps:</strong><ol>';
            for (let i = 0; i < answer.steps.length; i++) {
                const step = answer.steps[i];
                const why = answer.why && answer.why[i] ? answer.why[i] : '';
                const verify = answer.verification && answer.verification[i] ? answer.verification[i] : '';
                
                html += `<li><strong>${escapeHtml(step)}</strong>`;
                if (why) {
                    html += `<br><em class="step-why">Why: ${escapeHtml(why)}</em>`;
                }
                if (verify) {
                    html += `<br><span class="step-verify">✓ Verify: ${escapeHtml(verify)}</span>`;
                }
                html += '</li>';
            }
            html += '</ol></div>';
            
            // Sources (if present in answer, not traced_sources)
            if (answer.sources && answer.sources.length > 0) {
                html += '<div class="inline-sources"><strong>📖 References:</strong> ';
                html += answer.sources.map(s => `${escapeHtml(s.source)} p.${escapeHtml(String(s.page))}`).join(', ');
                html += '</div>';
            }
            
            html += '</div>';
            return html;
        }
        
        // Handle structured analysis response (type: "analysis")
        if (answer.type === 'analysis' && answer.steps) {
            let html = '<div class="analysis-response">';
            html += '<strong>🔍 Diagnostic Steps:</strong><ol>';
            for (const step of answer.steps) {
                html += `<li>`;
                if (step.description) {
                    html += `<strong>${escapeHtml(step.description)}</strong>`;
                }
                if (step.action) {
                    html += `<br><span class="step-action">➜ ${escapeHtml(step.action)}</span>`;
                }
                if (step.expected_result) {
                    html += `<br><em class="step-expected">Expected: ${escapeHtml(step.expected_result)}</em>`;
                }
                html += '</li>';
            }
            html += '</ol>';
            
            if (answer.conclusion) {
                html += `<div class="analysis-conclusion"><strong>✓ Conclusion:</strong> ${escapeHtml(answer.conclusion)}</div>`;
            }
            
            if (answer.caution && answer.caution.length > 0) {
                html += '<div class="caution-box"><strong>⚠️ Caution:</strong><ul>';
                for (const c of answer.caution) {
                    html += `<li>${escapeHtml(c)}</li>`;
                }
                html += '</ul></div>';
            }
            html += '</div>';
            return html;
        }
        
        // Handle retrieval-only fallback response
        if (answer.notes && answer.summary) {
            let html = '<div class="retrieval-fallback-response">';
            html += `<div class="fallback-notice"><strong>⚠️ ${escapeHtml(answer.notes)}</strong></div>`;
            html += '<div class="fallback-summary">';
            
            if (Array.isArray(answer.summary)) {
                for (const excerpt of answer.summary) {
                    html += `<div class="fallback-excerpt"><blockquote>${escapeHtml(excerpt)}</blockquote></div>`;
                }
            }
            
            html += '</div>';
            
            if (answer.sources && answer.sources.length > 0) {
                html += '<div class="fallback-sources"><strong>📖 Source References:</strong><ul>';
                for (const src of answer.sources) {
                    html += `<li><strong>${src.source}</strong> (p.${src.page})</li>`;
                }
                html += '</ul></div>';
            }
            
            html += '</div>';
            return html;
        }
        
        // Fallback: format JSON object as readable key-value pairs
        return formatJsonAsHtml(answer);
    }
    return String(answer);
}

// Format JSON object as readable HTML key-value pairs
function formatJsonAsHtml(obj, depth = 0) {
    if (typeof obj !== 'object' || obj === null) {
        return escapeHtml(String(obj));
    }
    
    let html = '<div class="json-formatted" style="margin-left: ' + (depth * 16) + 'px;">';
    for (const [key, value] of Object.entries(obj)) {
        const displayKey = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        
        if (typeof value === 'object' && value !== null) {
            html += `<div class="json-key"><strong>${escapeHtml(displayKey)}:</strong></div>`;
            html += formatJsonAsHtml(value, depth + 1);
        } else {
            html += `<div class="json-pair"><strong>${escapeHtml(displayKey)}:</strong> ${escapeHtml(String(value))}</div>`;
        }
    }
    html += '</div>';
    return html;
}

// Format traced sources for display
function formatTracedSources(sources, visible = true) {
    if (!sources || sources.length === 0) return '';
    const displayStyle = visible ? '' : 'display: none;';
    let html = `<div class="traced-sources" style="${displayStyle}"><strong>📚 Sources Used:</strong><ul>`;
    for (const src of sources) {
        const conf = (src.confidence * 100).toFixed(1);
        const page = src.page ? ` (p.${src.page})` : '';
        html += `<li><strong>${src.source}${page}</strong> - ${conf}% match`;
        if (src.snippet) {
            html += `<br><small class="snippet">${src.snippet}...</small>`;
        }
        html += '</li>';
    }
    html += '</ul></div>';
    return html;
}

// Add message to chat
function addMessageToChat(text, sender, model = '', confidence = '', auditStatus = '', effectiveSafety = null, fullData = null) {
    const messagesEl = document.getElementById('chat-messages');
    const showMeta = isMetadataVisible();
    
    // Remove welcome message if it exists
    const welcome = messagesEl.querySelector('.welcome-message');
    if (welcome) welcome.remove();
    
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${sender}`;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    // Add citation audit badge if available
    let auditBadge = '';
    if (auditStatus) {
        const badges = {
            'fully_cited': '<span class="audit-badge audit-full" title="All claims verified with source citations">✓ Fully cited</span>',
            'partially_cited': '<span class="audit-badge audit-partial" title="Some claims lack citations">⚠ Partial citations</span>',
            'uncited': '<span class="audit-badge audit-none" title="Citations missing or invalid">✗ Uncited</span>'
        };
        auditBadge = badges[auditStatus] || '';
    }
    
    // Format the answer (handle string or dict)
    let content = formatAnswer(text);
    if (sender === 'assistant') {
        // Add traced sources if available
        if (fullData && fullData.traced_sources && fullData.traced_sources.length > 0) {
            content += formatTracedSources(fullData.traced_sources, showMeta);
        }
        // Add retrieval score if available
        if (fullData && fullData.retrieval_score) {
            const scoreStyle = showMeta ? '' : 'display: none;';
            content += `<div class="retrieval-score" style="${scoreStyle}">📊 <strong>Retrieval Score:</strong> ${(fullData.retrieval_score * 100).toFixed(1)}%</div>`;
        }
        content += `<div class="response-disclaimer">
            💡 <strong>AI Transparency:</strong> Always verify critical information with official vehicle service manuals before performing repairs.
        </div>`;
        if (auditBadge) {
            content = auditBadge + '<br>' + content;
        }
    }
    
    contentDiv.innerHTML = content.replace(/\n/g, '<br>');
    msgDiv.appendChild(contentDiv);
    
    if (model) {
        const infoDiv = document.createElement('div');
        infoDiv.className = 'message-info';

        let safetyText = '';
        if (effectiveSafety && typeof effectiveSafety === 'object') {
            const auditOn = effectiveSafety.citation_audit_enabled === true ? 'ON'
                : effectiveSafety.citation_audit_enabled === false ? 'OFF'
                : '--';
            const strictOn = effectiveSafety.citation_strict_enabled === true ? 'ON'
                : effectiveSafety.citation_strict_enabled === false ? 'OFF'
                : '--';
            safetyText = `| Safety: Audit ${auditOn} | Strict ${strictOn}`;
        }

        infoDiv.textContent = `${model} ${confidence ? `| Confidence: ${confidence}` : ''} ${safetyText}`.trim();
        msgDiv.appendChild(infoDiv);
    }
    
    // JSON metadata viewer removed for cleaner UI - data still available in browser console
    // Developers can access fullData via: console.log(fullData)
    if (sender === 'assistant' && fullData) {
        console.log('[NIC Response Data]', fullData);
    }
    
    messagesEl.appendChild(msgDiv);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    
    return msgDiv;
}

// Save favorite
async function saveFavorite() {
    if (!currentQuestion || !currentAnswer) return;
    
    try {
        const res = await fetch(`${API_BASE}/favorite`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: currentQuestion, answer: currentAnswer })
        });
        
        if (res.ok) {
            alert('⭐ Added to favorites!');
            loadFavorites();
        }
    } catch (e) {
        console.error('Failed to save favorite:', e);
    }
}

// Load favorites
async function loadFavorites() {
    try {
        const res = await fetch(`${API_BASE}/favorites`);
        const data = await res.json();
        
        const preview = document.getElementById('favorites-preview');
        if (!data.favorites || data.favorites.length === 0) {
            preview.innerHTML = '<p class="empty">No favorites yet</p>';
            return;
        }
        
        preview.innerHTML = data.favorites.slice(0, 3).map(f => 
            `<div class="list-item">⭐ ${f.query.substring(0, 25)}...</div>`
        ).join('');
    } catch (e) {
        console.error('Failed to load favorites:', e);
    }
}

// Toggle feedback form
function toggleFeedback() {
    const form = document.getElementById('feedback-form');
    form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

// Submit quick feedback (helpful/resolved buttons)
async function submitQuickFeedback(helpful, resolved) {
    try {
        const payload = {
            question: currentQuestion,
            answer: currentAnswer.substring(0, 200),
            helpful: helpful,
            resolved: resolved,
            confidence_score: getCurrentConfidence()
        };
        
        const res = await fetch(`${API_BASE}/feedback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const data = await res.json();
        if (res.ok) {
            // Hide quick feedback bar and show confirmation
            document.getElementById('quick-feedback-bar').style.display = 'none';
            addMessageToChat('✅ Thank you for your feedback!', 'system');
        } else {
            alert(`Error: ${data.error}`);
        }
    } catch (e) {
        console.error('Failed to submit quick feedback:', e);
    }
}

// Submit detailed feedback form
async function submitDetailedFeedback() {
    const helpful = document.getElementById('feedback-helpful').checked;
    const resolved = document.getElementById('feedback-resolved').checked;
    const notes = document.getElementById('feedback-input').value.trim();
    
    if (!helpful && !resolved && !notes) {
        alert('Please provide at least some feedback.');
        return;
    }
    
    try {
        const payload = {
            question: currentQuestion,
            answer: currentAnswer.substring(0, 200),
            helpful: helpful,
            resolved: resolved,
            confidence_score: getCurrentConfidence(),
            notes: notes
        };
        
        const res = await fetch(`${API_BASE}/feedback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const data = await res.json();
        if (res.ok) {
            // Reset form
            document.getElementById('feedback-helpful').checked = false;
            document.getElementById('feedback-resolved').checked = false;
            document.getElementById('feedback-input').value = '';
            document.getElementById('feedback-form').style.display = 'none';
            addMessageToChat('✅ Thank you! Your feedback helps us improve.', 'system');
        } else {
            alert(`Error: ${data.error}`);
        }
    } catch (e) {
        console.error('Failed to submit detailed feedback:', e);
    }
}

// OLD submitFeedback (kept for backwards compatibility if needed)
async function submitFeedback() {
    const feedback = document.getElementById('feedback-input').value.trim();
    if (!feedback) return;
    
    try {
        const res = await fetch(`${API_BASE}/feedback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ feedback })
        });
        
        const data = await res.json();
        if (res.ok) {
            alert(data.message);
            document.getElementById('feedback-input').value = '';
            document.getElementById('feedback-form').style.display = 'none';
        } else {
            alert(`Error: ${data.error}`);
        }
    } catch (e) {
        console.error('Failed to submit feedback:', e);
    }
}

// Get current confidence score from display
function getCurrentConfidence() {
    const confEl = document.getElementById('confidence-value');
    if (!confEl || confEl.textContent === '--') return 0.0;
    const match = confEl.textContent.match(/[\d.]+/);
    return match ? parseFloat(match[0]) / 100 : 0.0;
}

// Rebuild index
async function rebuildIndex() {
    if (!confirm('Rebuild FAISS index? This may take a few minutes...')) return;
    
    try {
        addMessageToChat('🔄 Rebuilding index...', 'assistant');
        const res = await fetch(`${API_BASE}/rebuild-index`, { method: 'POST' });
        const data = await res.json();
        
        if (res.ok) {
            addMessageToChat(data.message, 'assistant');
        } else {
            addMessageToChat(`❌ ${data.error}`, 'assistant');
        }
    } catch (e) {
        addMessageToChat(`❌ Error: ${e.message}`, 'assistant');
    }
}

// Export session
async function exportSession() {
    try {
        addMessageToChat('📥 Exporting session...', 'assistant');
        const res = await fetch(`${API_BASE}/export-session`, { method: 'POST' });
        const data = await res.json();
        
        if (res.ok) {
            addMessageToChat(data.message, 'assistant');
        } else {
            addMessageToChat(`❌ ${data.error}`, 'assistant');
        }
    } catch (e) {
        addMessageToChat(`❌ Error: ${e.message}`, 'assistant');
    }
}

// Reset session
async function resetSession() {
    if (!confirm('End current troubleshooting session?')) return;
    
    try {
        const res = await fetch(`${API_BASE}/reset-session`, { method: 'POST' });
        if (res.ok) {
            addMessageToChat('✅ Session reset. Ready for new case.', 'assistant');
            updateStatus();
        }
    } catch (e) {
        console.error('Failed to reset session:', e);
    }
}

// Favorites modal
function closeFavoritesModal() {
    document.getElementById('favorites-modal').style.display = 'none';
}

// Pre-load GPT-OSS model with high token config
async function preloadGPTOSS() {
    const btn = document.getElementById('load-gptoss-btn');
    if (!btn) return; // Button not present in UI
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span> Loading GPT-OSS...';
    
    try {
        const res = await fetch(`${API_BASE}/load-model`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: 'qwen/qwen2.5-coder-14b',
                max_tokens: 45000  // High token limit for extended deep analysis conversations
            })
        });
        
        const data = await res.json();
        
        if (res.ok) {
            addMessageToChat(`✅ ${data.message}`, 'assistant');
            updateStatus();
        } else {
            addMessageToChat(`❌ ${data.error}`, 'assistant');
        }
    } catch (e) {
        addMessageToChat(`❌ Failed to load model: ${e.message}`, 'assistant');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span>🧠</span> Load GPT-OSS (4096 tokens)';
    }
}

// Pre-load LLAMA model (fast)
async function preloadLLAMA() {
    const btn = document.getElementById('load-llama-btn');
    if (!btn) return; // Button not present in UI
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span> Loading LLAMA...';
    
    try {
        const res = await fetch(`${API_BASE}/load-model`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                // Default to smaller, GPU-friendly model unless overridden server-side
                model: 'mistralai/mistral-7b-instruct-v0.3',
                max_tokens: 2048  // Safer default to avoid OOM in LM Studio
            })
        });
        
        const data = await res.json();
        
        if (res.ok) {
            addMessageToChat(`✅ ${data.message}`, 'assistant');
            updateStatus();
        } else {
            addMessageToChat(`❌ ${data.error}`, 'assistant');
        }
    } catch (e) {
        addMessageToChat(`❌ Failed to load model: ${e.message}`, 'assistant');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span>⚡</span> Load LLAMA (2048 tokens)';
    }
}

// Wire up buttons
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('rebuild-btn').addEventListener('click', rebuildIndex);
    document.getElementById('export-btn').addEventListener('click', exportSession);
});

// Show basic metrics
async function showMetrics() {
    try {
        const res = await fetch(`${API_BASE}/metrics`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to fetch metrics');
        const lat = data.latency || {};
        const lines = [
            `Uptime: ${data.uptime_seconds}s`,
            `Calls: ${data.ask_calls} | Errors: ${data.ask_errors}`,
            lat.count ? `Latency (ms) — p50: ${lat.p50_ms}, p95: ${lat.p95_ms}, avg: ${lat.avg_ms}` : 'Latency: no samples yet'
        ];
        addMessageToChat(`📊 Metrics\n${lines.join('\n')}`, 'assistant');
    } catch (e) {
        addMessageToChat(`❌ Metrics error: ${e.message}`, 'assistant');
    }
}
