// Nyaya-Dwarpal web app. Plain JavaScript, no build step except the Tailwind stylesheet.
(function () {
    'use strict';

    const API_ENDPOINT = 'https://ked0qedvxi.execute-api.ap-south-2.amazonaws.com/prod';
    const MAX_RECORDING_SECONDS = 30;          // Sarvam's real-time speech-to-text limit
    const MAX_TEXT_LENGTH = 5000;              // matches the voice triage Lambda
    const MAX_FILE_BYTES = 5 * 1024 * 1024;    // Textract's limit for images
    const CASE_LIMIT = 50;

    const UI_LANGUAGES = ['en', 'hi', 'te', 'ta', 'bn', 'mr'];
    // Languages the AI answers in (typed or spoken)
    const ISSUE_LANGUAGES = [
        ['hi', 'हिंदी (Hindi)'], ['en', 'English'], ['te', 'తెలుగు (Telugu)'], ['ta', 'தமிழ் (Tamil)'],
        ['bn', 'বাংলা (Bengali)'], ['mr', 'मराठी (Marathi)'], ['gu', 'ગુજરાતી (Gujarati)'],
        ['kn', 'ಕನ್ನಡ (Kannada)'], ['ml', 'മലയാളം (Malayalam)'], ['pa', 'ਪੰਜਾਬੀ (Punjabi)']
    ];
    const TRANSLATE_LANGUAGES = ISSUE_LANGUAGES.concat([['od', 'ଓଡ଼ିଆ (Odia)']]);
    const LOCALES = { en: 'en-IN', hi: 'hi-IN', te: 'te-IN', ta: 'ta-IN', bn: 'bn-IN', mr: 'mr-IN' };
    const PAGES = ['home', 'ask', 'verify', 'translate', 'cases', 'library'];
    const PAGE_TITLES = { home: 'navHome', ask: 'navAsk', verify: 'navVerify', translate: 'navTranslate', cases: 'navCases', library: 'navLibrary' };

    // ---------- small helpers ----------

    const $ = (id) => document.getElementById(id);

    function storageGet(key) {
        try { return localStorage.getItem(key); } catch (e) { return null; }
    }
    function storageSet(key, value) {
        try { localStorage.setItem(key, value); } catch (e) { /* private mode: keep going without it */ }
    }

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    // Escaped text with **bold** and line breaks (the AI writes simple markdown)
    function richText(value) {
        return esc(value).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>');
    }

    function asList(value) {
        if (Array.isArray(value)) return value.filter((v) => v != null && String(v).trim() !== '');
        if (typeof value === 'string' && value.trim()) return [value.trim()];
        return [];
    }

    let uiLang = 'en';

    function t(key, vars) {
        const table = window.I18N[uiLang] || window.I18N.en;
        let text = table[key] != null ? table[key] : (window.I18N.en[key] != null ? window.I18N.en[key] : key);
        if (vars) Object.keys(vars).forEach((k) => { text = text.replace('{' + k + '}', vars[k]); });
        return text;
    }

    function formatDate(iso) {
        const date = new Date(iso);
        if (isNaN(date)) return '';
        return date.toLocaleDateString(LOCALES[uiLang] || 'en-IN', { day: 'numeric', month: 'long', year: 'numeric' });
    }

    function getUserId() {
        let id = storageGet('nyaya_userId');
        if (!id || !/^user-[A-Za-z0-9-]{6,64}$/.test(id)) {
            const random = (window.crypto && crypto.randomUUID)
                ? crypto.randomUUID()
                : Date.now() + '-' + Math.random().toString(36).slice(2, 12);
            id = 'user-' + random;
            storageSet('nyaya_userId', id);
        }
        return id;
    }
    const userId = getUserId();

    function bumpCounter(key) {
        const next = (parseInt(storageGet(key), 10) || 0) + 1;
        storageSet(key, String(next));
        return next;
    }

    function scrollToEl(el) {
        if (!el) return;
        const header = document.querySelector('header');
        const offset = (header ? header.offsetHeight : 0) + 12;
        window.scrollTo({ top: el.getBoundingClientRect().top + window.pageYOffset - offset, behavior: 'smooth' });
    }

    // ---------- API ----------

    class ApiError extends Error {
        constructor(key, status) { super(key); this.key = key; this.status = status; }
    }

    // Maps a failed response to a translated message key
    function errorKeyFor(status, body, fallback) {
        const code = body && body.errorCode;
        if (code === 'service_unavailable') return fallback === 'errTranslateUnavailable' ? fallback : 'errVoiceUnavailable';
        if (code === 'busy' || status === 429) return 'errBusy';
        if (code === 'audio_invalid') return 'errAudio';
        if (code === 'no_speech') return 'errNoSpeech';
        if (code === 'no_text') return 'errDocUnreadable';
        if (status === 413) return 'errFileSize';
        return fallback || 'errGeneric';
    }

    async function api(path, options, fallbackKey) {
        let response;
        try {
            response = await fetch(API_ENDPOINT + path, options);
        } catch (e) {
            throw new ApiError(navigator.onLine === false ? 'errNetwork' : 'errNetwork', 0);
        }
        let body = null;
        try { body = await response.json(); } catch (e) { /* not JSON */ }
        if (!response.ok || !body || body.success === false) {
            throw new ApiError(errorKeyFor(response.status, body, fallbackKey), response.status);
        }
        return body;
    }

    function postJson(path, payload, fallbackKey) {
        return api(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }, fallbackKey);
    }

    function readAsBase64(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
    }

    // ---------- shared UI pieces ----------

    function showError(boxId, key, retry) {
        const box = $(boxId);
        box.innerHTML = `
            <div class="flex items-start gap-3 p-4 rounded-lg bg-red-50 border border-red-200 text-red-800" role="alert">
                <span aria-hidden="true">⚠️</span>
                <div class="flex-1">
                    <p class="text-sm font-medium">${esc(t(key))}</p>
                    ${retry ? `<button type="button" class="mt-2 text-sm font-semibold underline" data-retry>${esc(t('retry'))}</button>` : ''}
                </div>
            </div>`;
        box.classList.remove('hidden');
        if (retry) box.querySelector('[data-retry]').addEventListener('click', retry);
        scrollToEl(box);
    }

    function hideError(boxId) {
        const box = $(boxId);
        box.classList.add('hidden');
        box.innerHTML = '';
    }

    function setBusy(el, busy) {
        if (!el) return;
        el.disabled = busy;
        el.classList.toggle('opacity-60', busy);
        el.classList.toggle('cursor-not-allowed', busy);
    }

    const LEVEL_STYLE = {
        high: 'bg-red-100 text-red-800', medium: 'bg-yellow-100 text-yellow-800', low: 'bg-green-100 text-green-800'
    };
    const LEVEL_KEY = { high: 'levelHigh', medium: 'levelMedium', low: 'levelLow' };
    const EMOTION_KEY = {
        distressed: 'emoDistressed', angry: 'emoAngry', confused: 'emoConfused', frustrated: 'emoFrustrated', calm: 'emoCalm'
    };
    const EMOTION_STYLE = {
        distressed: 'bg-orange-100 text-orange-800', angry: 'bg-red-100 text-red-800', confused: 'bg-purple-100 text-purple-800',
        frustrated: 'bg-amber-100 text-amber-800', calm: 'bg-green-100 text-green-800'
    };

    function levelBadge(level) {
        const key = String(level || '').toLowerCase();
        const style = LEVEL_STYLE[key] || 'bg-gray-100 text-gray-800';
        const label = LEVEL_KEY[key] ? t(LEVEL_KEY[key]) : level;
        return `<span class="inline-block px-3 py-1 rounded-full text-xs font-bold ${style}">${esc(label)}</span>`;
    }

    function emotionBadge(emotion) {
        const key = String(emotion || '').toLowerCase();
        const style = EMOTION_STYLE[key] || 'bg-gray-100 text-gray-800';
        const label = EMOTION_KEY[key] ? t(EMOTION_KEY[key]) : emotion;
        return `<span class="inline-block px-3 py-1 rounded-full text-xs font-bold ${style}">${esc(label)}</span>`;
    }

    function card(title, inner, extraClass) {
        return `<div class="rounded-lg p-4 border ${extraClass || 'bg-white border-gray-200'}">
                    <p class="text-sm font-semibold text-gray-600 mb-2">${esc(title)}</p>${inner}</div>`;
    }

    function sectionsHtml(sections) {
        return asList(sections).map((s) => {
            const section = typeof s === 'string' ? { section: s } : s;
            return `<div class="bg-gradient-to-r from-nyaya-blue/5 to-justice-gold/5 rounded-lg p-3 border border-gray-100">
                <p class="text-sm font-bold text-nyaya-blue">${esc(section.section || '')}</p>
                ${section.act ? `<p class="text-xs text-gray-600 mb-1">${esc(section.act)}</p>` : ''}
                ${section.description ? `<p class="text-sm text-gray-700">${esc(section.description)}</p>` : ''}
                ${section.penalty ? `<p class="text-xs text-gray-600 mt-1"><span class="font-semibold">${esc(t('penalty'))}:</span> ${esc(section.penalty)}</p>` : ''}
                ${section.remedy ? `<p class="text-xs text-gray-600 mt-1"><span class="font-semibold">${esc(t('remedy'))}:</span> ${esc(section.remedy)}</p>` : ''}
            </div>`;
        }).join('');
    }

    function listHtml(items, ordered) {
        const tag = ordered ? 'ol' : 'ul';
        const cls = ordered ? 'list-decimal' : 'list-disc';
        return `<${tag} class="${cls} pl-5 space-y-1.5 text-sm text-gray-800">${asList(items).map((i) => `<li>${esc(typeof i === 'string' ? i : JSON.stringify(i))}</li>`).join('')}</${tag}>`;
    }

    function factsHtml(facts) {
        if (!facts || typeof facts !== 'object') return '';
        const rows = [['who', 'factWho'], ['what', 'factWhat'], ['when', 'factWhen'], ['where', 'factWhere'], ['amount', 'factAmount']]
            .filter(([k]) => facts[k] && String(facts[k]).trim())
            .map(([k, label]) => {
                const value = Array.isArray(facts[k]) ? facts[k].join(', ') : facts[k];
                return `<p class="text-sm text-gray-800"><span class="font-semibold">${esc(t(label))}:</span> ${esc(value)}</p>`;
            });
        return rows.length ? `<div class="space-y-1">${rows.join('')}</div>` : '';
    }

    // ---------- language ----------

    function fillSelect(select, options, selected) {
        select.innerHTML = options.map(([value, label]) =>
            `<option value="${esc(value)}"${value === selected ? ' selected' : ''}>${esc(label)}</option>`).join('');
    }

    function applyLanguage(lang) {
        uiLang = UI_LANGUAGES.includes(lang) ? lang : 'en';
        storageSet('ui-language', uiLang);
        document.documentElement.lang = uiLang;
        $('ui-language').value = uiLang;
        document.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
        document.querySelectorAll('[data-i18n-placeholder]').forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
        document.querySelectorAll('[data-i18n-aria]').forEach((el) => { el.setAttribute('aria-label', t(el.dataset.i18nAria)); });

        // Default the issue/translation language to the interface language until the person picks one
        if (!issueLangChosen) $('issue-language').value = uiLang;
        if (!translateLangChosen) $('translate-language').value = uiLang === 'en' ? 'hi' : uiLang;
        updateVoiceLanguageOption();
        updateScriptToggle();
        $('page-title').textContent = t(PAGE_TITLES[currentPage]);
        document.title = t(PAGE_TITLES[currentPage]) + ' · Nyaya-Dwarpal';

        // Re-render what is on screen in the new language
        renderLibrary();
        if (lastTriage) renderTriage(lastTriage);
        if (lastVerification) renderVerification(lastVerification);
        if (lastTranslation) renderTranslation(lastTranslation);
        if (currentPage === 'cases' && casesCache) renderCases(casesCache);
        if (currentPage === 'home') loadHome();
    }

    // ---------- navigation ----------

    let currentPage = 'home';

    function openSidebar(open) {
        const sidebar = $('sidebar');
        sidebar.classList.toggle('-translate-x-full', !open);
        $('sidebar-backdrop').classList.toggle('hidden', !open);
        $('menu-button').setAttribute('aria-expanded', String(open));
        if (open) $('sidebar-close').focus();
    }

    function showPage(page) {
        if (!PAGES.includes(page)) page = 'home';
        currentPage = page;
        PAGES.forEach((p) => { $('page-' + p).classList.toggle('hidden', p !== page); });
        document.querySelectorAll('[data-nav]').forEach((link) => {
            const active = link.dataset.nav === page;
            link.classList.toggle('bg-justice-gold', active);
            link.classList.toggle('text-nyaya-blue', active);
            link.classList.toggle('shadow-lg', active);
            link.classList.toggle('text-gray-300', !active);
            if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
        });
        $('page-title').textContent = t(PAGE_TITLES[page]);
        document.title = t(PAGE_TITLES[page]) + ' · Nyaya-Dwarpal';
        openSidebar(false);
        window.scrollTo(0, 0);
        if (page === 'home') loadHome();
        if (page === 'cases') loadCases();
    }

    function go(page) {
        if (location.hash === '#' + page) showPage(page);
        else location.hash = page;
    }

    // ---------- home ----------

    async function fetchCases() {
        const body = await api(`/cases?userId=${encodeURIComponent(userId)}&limit=${CASE_LIMIT}`, {}, 'errCasesLoad');
        return (body.data && body.data.cases) || [];
    }

    let casesCache = null;

    async function loadHome() {
        $('stat-docs').textContent = storageGet('nyaya_docsTranslated') || '0';
        $('stat-checked').textContent = storageGet('nyaya_docsChecked') || '0';
        const container = $('recent-list');
        $('recent-loading').classList.remove('hidden');
        $('recent-empty').classList.add('hidden');
        container.classList.add('hidden');
        try {
            casesCache = await fetchCases();
            $('stat-cases').textContent = casesCache.length >= CASE_LIMIT ? CASE_LIMIT + '+' : String(casesCache.length);
            if (!casesCache.length) {
                $('recent-empty').classList.remove('hidden');
            } else {
                container.innerHTML = casesCache.slice(0, 3).map(caseCard).join('');
                container.classList.remove('hidden');
            }
        } catch (e) {
            $('stat-cases').textContent = '–';
            $('recent-empty').classList.remove('hidden');
        } finally {
            $('recent-loading').classList.add('hidden');
        }
    }

    // ---------- get legal help (voice + text) ----------

    let inputMode = 'voice';
    let useNativeScript = true;
    let issueLangChosen = false;
    let lastTriage = null;
    let lastTriageInput = null;

    function updateVoiceLanguageOption() {
        const select = $('issue-language');
        const auto = select.querySelector('option[value="auto"]');
        if (inputMode === 'voice' && !auto) {
            select.insertAdjacentHTML('beforeend', `<option value="auto">${esc(t('autoDetect'))}</option>`);
        } else if (inputMode !== 'voice' && auto) {
            if (select.value === 'auto') select.value = uiLang;
            auto.remove();
        } else if (auto) {
            auto.textContent = t('autoDetect');
        }
        $('issue-language-label').textContent = t(inputMode === 'voice' ? 'speakLang' : 'writeLang');
    }

    function updateScriptToggle() {
        $('script-row').classList.toggle('hidden', $('issue-language').value === 'en');
        $('script-native').setAttribute('aria-pressed', String(useNativeScript));
        $('script-roman').setAttribute('aria-pressed', String(!useNativeScript));
        [['script-native', useNativeScript], ['script-roman', !useNativeScript]].forEach(([id, on]) => {
            $(id).classList.toggle('bg-nyaya-blue', on);
            $(id).classList.toggle('text-white', on);
            $(id).classList.toggle('text-gray-700', !on);
        });
    }

    function switchInputTab(mode) {
        inputMode = mode;
        $('voice-section').classList.toggle('hidden', mode !== 'voice');
        $('text-section').classList.toggle('hidden', mode !== 'text');
        [['tab-voice', 'voice'], ['tab-text', 'text']].forEach(([id, m]) => {
            const on = m === mode;
            $(id).setAttribute('aria-selected', String(on));
            $(id).classList.toggle('border-nyaya-blue', on);
            $(id).classList.toggle('text-nyaya-blue', on);
            $(id).classList.toggle('border-transparent', !on);
            $(id).classList.toggle('text-gray-500', !on);
        });
        updateVoiceLanguageOption();
        updateScriptToggle();
    }

    function setAskLoading(on, messageKey) {
        $('ask-loading').classList.toggle('hidden', !on);
        $('ask-loading-text').textContent = t(messageKey || 'analysing');
        setBusy($('analyse-button'), on);
        setBusy($('mic-button'), on);
        if (on) scrollToEl($('ask-loading'));
    }

    async function analyseIssue(text, language) {
        hideError('ask-error');
        $('ask-results').classList.add('hidden');
        lastTriageInput = { text, language };
        setAskLoading(true, 'analysing');
        try {
            const body = await postJson('/voice/triage', {
                userId, transcribedText: text, language, useNativeScript
            });
            lastTriage = body.data;
            casesCache = null;
            renderTriage(lastTriage);
        } catch (e) {
            showError('ask-error', e.key || 'errGeneric', () => analyseIssue(text, language));
        } finally {
            setAskLoading(false);
        }
    }

    function renderTriage(data) {
        const classification = data.classification || {};
        const emotion = data.emotion || {};
        const parts = [];

        parts.push(card(t('youSaid'), `<p class="text-gray-800 whitespace-pre-wrap">${esc(data.transcription)}</p>`));

        parts.push(`<div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
            ${card(t('category'), `<p class="font-bold text-nyaya-blue">${esc(classification.category || '')}</p>
                ${classification.subCategory ? `<p class="text-sm text-gray-600 mt-1">${esc(classification.subCategory)}</p>` : ''}`)}
            ${card(t('urgency'), levelBadge(emotion.urgency) + (emotion.urgencyReason ? `<p class="text-xs text-gray-600 mt-2">${esc(emotion.urgencyReason)}</p>` : ''))}
            ${card(t('emotion'), emotionBadge(emotion.primary))}
        </div>`);

        if (asList(classification.relevantSections).length) {
            parts.push(card(t('sections'), `<div class="space-y-2">${sectionsHtml(classification.relevantSections)}</div>`));
        }
        if (data.recommendation) {
            parts.push(card(t('recommendation'), `<p class="text-gray-800 leading-relaxed">${richText(data.recommendation)}</p>`,
                'bg-justice-gold/10 border-justice-gold/30'));
        }
        if (asList(data.nextSteps).length) parts.push(card(t('nextSteps'), listHtml(data.nextSteps, true)));
        if (asList(data.requiredDocuments).length) {
            parts.push(card(t('documents'), listHtml(data.requiredDocuments), 'bg-blue-50 border-blue-200'));
        }
        if (data.estimatedCost || data.timeline) {
            parts.push(`<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                ${data.estimatedCost ? card(t('cost'), `<p class="text-sm text-gray-800">${esc(data.estimatedCost)}</p>`) : ''}
                ${data.timeline ? card(t('timeline'), `<p class="text-sm text-gray-800">${esc(data.timeline)}</p>`) : ''}
            </div>`);
        }
        const resources = asList(data.resources).filter((r) => r && typeof r === 'object');
        if (resources.length) {
            parts.push(card(t('resources'), `<div class="space-y-2">${resources.map((r) => `
                <div class="bg-white rounded-lg p-3 border border-gray-100">
                    <p class="text-sm font-bold text-green-700">${esc(r.name)}</p>
                    ${r.action ? `<p class="text-sm text-gray-700">${esc(r.action)}</p>` : ''}
                    <p class="text-xs text-gray-500 mt-1">${esc([r.cost, r.timeline].filter(Boolean).join(' · '))}</p>
                </div>`).join('')}</div>`, 'bg-gradient-to-r from-green-50 to-blue-50 border-green-200'));
        }
        parts.push(`<div class="rounded-lg p-4 border-2 border-amber-400 bg-amber-50">
            <p class="text-sm font-bold text-amber-900">⚠️ ${esc(t('disclaimerTitle'))}</p>
            <p class="text-sm text-amber-900 mt-1">${esc(t('disclaimer'))}</p></div>`);

        $('ask-results-content').innerHTML = parts.join('');
        $('ask-results').classList.remove('hidden');
        scrollToEl($('ask-results'));
    }

    // Voice recording

    let mediaRecorder = null;
    let recordingStream = null;
    let recordingTimer = null;
    let recordingStartedAt = 0;
    let audioChunks = [];

    function pickMimeType() {
        if (!window.MediaRecorder || !MediaRecorder.isTypeSupported) return '';
        return ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus', 'audio/ogg']
            .find((type) => MediaRecorder.isTypeSupported(type)) || '';
    }

    function setMicState(state) {
        const recording = state === 'recording';
        $('mic-button').classList.toggle('from-red-600', recording);
        $('mic-button').classList.toggle('to-red-500', recording);
        $('mic-button').classList.toggle('from-nyaya-blue', !recording);
        $('mic-button').classList.toggle('to-nyaya-blue-light', !recording);
        $('mic-button').setAttribute('aria-pressed', String(recording));
        $('pulse-ring').classList.toggle('hidden', recording);
        $('waveform').classList.toggle('hidden', !recording);
        $('mic-status').textContent = t(recording ? 'micRecording' : state === 'processing' ? 'micProcessing' : 'micStart');
        $('mic-timer').textContent = recording ? t('secondsLeft', { n: MAX_RECORDING_SECONDS }) : t('micHint');
    }

    async function startRecording() {
        hideError('ask-error');
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
            showError('ask-error', 'errMicUnsupported');
            return;
        }
        try {
            recordingStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (e) {
            showError('ask-error', e && (e.name === 'NotAllowedError' || e.name === 'SecurityError') ? 'errMicDenied' : 'errMicUnsupported');
            return;
        }
        const mimeType = pickMimeType();
        try {
            mediaRecorder = mimeType ? new MediaRecorder(recordingStream, { mimeType }) : new MediaRecorder(recordingStream);
        } catch (e) {
            stopStream();
            showError('ask-error', 'errMicUnsupported');
            return;
        }
        audioChunks = [];
        mediaRecorder.ondataavailable = (event) => { if (event.data && event.data.size) audioChunks.push(event.data); };
        mediaRecorder.onstop = () => {
            stopStream();
            const type = mediaRecorder.mimeType || mimeType || 'audio/webm';
            transcribeAndAnalyse(new Blob(audioChunks, { type }), type);
        };
        mediaRecorder.start();
        recordingStartedAt = Date.now();
        setMicState('recording');
        recordingTimer = setInterval(() => {
            const left = MAX_RECORDING_SECONDS - Math.floor((Date.now() - recordingStartedAt) / 1000);
            $('mic-timer').textContent = t('secondsLeft', { n: Math.max(left, 0) });
            if (left <= 0) stopRecording();
        }, 250);
    }

    function stopStream() {
        if (recordingStream) recordingStream.getTracks().forEach((track) => track.stop());
        recordingStream = null;
    }

    function stopRecording() {
        clearInterval(recordingTimer);
        if (mediaRecorder && mediaRecorder.state === 'recording') {
            setMicState('processing');
            mediaRecorder.stop();
        }
    }

    function toggleRecording() {
        if (mediaRecorder && mediaRecorder.state === 'recording') stopRecording();
        else startRecording();
    }

    async function transcribeAndAnalyse(blob, mimeType) {
        if (!blob.size || Date.now() - recordingStartedAt < 800) {
            setMicState('idle');
            showError('ask-error', 'errNoSpeech');
            return;
        }
        $('ask-results').classList.add('hidden');
        setAskLoading(true, 'micProcessing');
        const chosen = $('issue-language').value;
        let transcript;
        let language;
        try {
            const body = await postJson('/transcribe', {
                audio: await readAsBase64(blob),
                mime_type: mimeType,
                language_code: chosen === 'auto' ? 'unknown' : chosen + '-IN'
            }, 'errAudio');
            transcript = (body.data && body.data.transcript || '').trim();
            const detected = String(body.data && body.data.language_code || '').split('-')[0];
            language = chosen === 'auto'
                ? (ISSUE_LANGUAGES.some(([code]) => code === detected) ? detected : 'en')
                : chosen;
        } catch (e) {
            setAskLoading(false);
            setMicState('idle');
            showError('ask-error', e.key || 'errAudio');
            return;
        }
        setMicState('idle');
        if (!transcript) {
            setAskLoading(false);
            showError('ask-error', 'errNoSpeech');
            return;
        }
        analyseIssue(transcript, language);
    }

    // ---------- petition draft ----------

    async function draftPetition(source) {
        openModal(t('petitionTitle'), `<div class="text-center py-8">
            <div class="inline-block w-10 h-10 border-4 border-gray-200 border-t-justice-gold rounded-full animate-spin"></div>
            <p class="mt-3 text-gray-600">${esc(t('drafting'))}</p></div>`);
        const sections = asList(source.sections).map((s) => typeof s === 'string' ? s : [s.act, s.section].filter(Boolean).join(' '));
        try {
            const body = await postJson('/petition/draft', {
                facts: source.facts || {},
                category: source.category || '',
                sections,
                language: source.language || uiLang,
                issueText: source.text || ''
            });
            const draft = body.data || {};
            const fullText = [
                t('petitionFacts').toUpperCase(), draft.facts_section || '',
                '', t('petitionGrounds').toUpperCase(), draft.grounds_section || '',
                '', t('petitionPrayer').toUpperCase(), draft.prayer_section || ''
            ].join('\n');
            setModalBody(`
                <p class="text-sm text-amber-900 bg-amber-50 border border-amber-300 rounded-lg p-3 mb-4">${esc(t('petitionHint'))}</p>
                ${[['petitionFacts', draft.facts_section], ['petitionGrounds', draft.grounds_section], ['petitionPrayer', draft.prayer_section]]
                    .filter(([, text]) => text)
                    .map(([label, text]) => `<h4 class="font-bold text-nyaya-blue mt-4 mb-1">${esc(t(label))}</h4>
                        <p class="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">${esc(text)}</p>`).join('')}
                <div class="flex flex-wrap gap-3 mt-6">
                    <button type="button" data-copy class="px-4 py-2 rounded-lg bg-nyaya-blue text-white font-semibold">${esc(t('copy'))}</button>
                    <button type="button" data-download class="px-4 py-2 rounded-lg border-2 border-nyaya-blue text-nyaya-blue font-semibold">${esc(t('download'))}</button>
                </div>`);
            const modal = $('modal-body');
            modal.querySelector('[data-copy]').addEventListener('click', (e) => copyText(fullText, e.currentTarget));
            modal.querySelector('[data-download]').addEventListener('click', () => downloadText(fullText, 'petition-draft.txt'));
        } catch (e) {
            setModalBody(`<p class="text-red-700">${esc(t(e.key || 'errGeneric'))}</p>`);
        }
    }

    function copyText(text, button) {
        const done = () => {
            const label = button.textContent;
            button.textContent = t('copied');
            setTimeout(() => { button.textContent = label; }, 1500);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
        } else {
            fallbackCopy(text, done);
        }
    }

    function fallbackCopy(text, done) {
        const area = document.createElement('textarea');
        area.value = text;
        area.setAttribute('readonly', '');
        area.style.position = 'fixed';
        area.style.opacity = '0';
        document.body.appendChild(area);
        area.select();
        try { document.execCommand('copy'); done(); } catch (e) { /* ignore */ }
        area.remove();
    }

    function downloadText(text, filename) {
        const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    // ---------- modal ----------

    let modalReturnFocus = null;

    function openModal(title, html) {
        modalReturnFocus = document.activeElement;
        $('modal-title').textContent = title;
        setModalBody(html);
        $('modal').classList.remove('hidden');
        document.body.classList.add('overflow-hidden');
        $('modal-close').focus();
    }

    function setModalBody(html) {
        $('modal-body').innerHTML = html;
    }

    function closeModal() {
        $('modal').classList.add('hidden');
        document.body.classList.remove('overflow-hidden');
        if (modalReturnFocus && modalReturnFocus.focus) modalReturnFocus.focus();
    }

    // ---------- file drop zones ----------

    function extensionOf(name) {
        const match = /\.([a-z0-9]+)$/i.exec(name || '');
        return match ? match[1].toLowerCase() : '';
    }

    function setupDropZone(zoneId, inputId, onFile) {
        const zone = $(zoneId);
        const input = $(inputId);
        zone.addEventListener('click', () => input.click());
        zone.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); }
        });
        zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('drag-over'); });
        zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
        zone.addEventListener('drop', (e) => {
            e.preventDefault();
            zone.classList.remove('drag-over');
            if (e.dataTransfer.files.length) onFile(e.dataTransfer.files[0]);
        });
        input.addEventListener('change', () => {
            if (input.files.length) onFile(input.files[0]);
            input.value = '';
        });
    }

    function checkFile(file, allowed, errorBox) {
        if (!allowed.includes(extensionOf(file.name))) {
            showError(errorBox, 'errFileType');
            return false;
        }
        if (file.size > MAX_FILE_BYTES) {
            showError(errorBox, 'errFileSize');
            return false;
        }
        return true;
    }

    // ---------- check a document ----------

    const VERIFY_TYPES = ['pdf', 'docx', 'jpg', 'jpeg', 'png', 'txt'];
    let lastVerification = null;

    async function verifyDocument(file) {
        hideError('verify-error');
        if (!checkFile(file, VERIFY_TYPES, 'verify-error')) return;
        $('verify-results').classList.add('hidden');
        $('verify-loading').classList.remove('hidden');
        scrollToEl($('verify-loading'));
        try {
            const body = await postJson('/validate/document', {
                document: await readAsBase64(file),
                fileType: extensionOf(file.name),
                fileName: file.name
            }, 'errGeneric');
            lastVerification = body.data;
            bumpCounter('nyaya_docsChecked');
            renderVerification(lastVerification);
        } catch (e) {
            const key = e.status === 400 ? 'errDocUnreadable' : (e.key || 'errGeneric');
            showError('verify-error', key, e.status === 400 ? null : () => verifyDocument(file));
        } finally {
            $('verify-loading').classList.add('hidden');
        }
    }

    const SEVERITY_ORDER = { HIGH: 0, MEDIUM: 1, LOW: 2 };
    const SEVERITY_STYLE = {
        HIGH: 'border-red-300 bg-red-50', MEDIUM: 'border-yellow-300 bg-yellow-50', LOW: 'border-blue-200 bg-blue-50'
    };
    const SEVERITY_BADGE = {
        HIGH: 'bg-red-600 text-white', MEDIUM: 'bg-yellow-500 text-white', LOW: 'bg-blue-500 text-white'
    };
    const SEVERITY_KEY = { HIGH: 'severityHigh', MEDIUM: 'severityMedium', LOW: 'severityLow' };

    function renderVerification(data) {
        const issues = asList(data.issues).filter((i) => i && typeof i === 'object')
            .sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 1) - (SEVERITY_ORDER[b.severity] ?? 1));
        $('verify-filename').textContent = data.fileName || '';
        $('verify-summary').innerHTML = `
            <p class="font-bold ${issues.length ? 'text-gray-900' : 'text-green-700'}">${esc(issues.length ? t('issuesFound', { n: issues.length }) : t('noIssues'))}</p>
            ${data.truncated ? `<p class="text-xs text-amber-800 mt-2">${esc(t('truncatedNote'))}</p>` : ''}`;
        $('verify-issues').innerHTML = issues.map((issue) => {
            const severity = SEVERITY_KEY[issue.severity] ? issue.severity : 'MEDIUM';
            return `<div class="rounded-lg border p-4 ${SEVERITY_STYLE[severity]}">
                <div class="flex items-start justify-between gap-3 mb-1">
                    <p class="font-semibold text-gray-900">${esc(issue.description)}</p>
                    <span class="shrink-0 px-2 py-0.5 rounded-full text-xs font-bold ${SEVERITY_BADGE[severity]}">${esc(t(SEVERITY_KEY[severity]))}</span>
                </div>
                ${issue.location ? `<p class="text-xs text-gray-600"><span class="font-semibold">${esc(t('location'))}:</span> ${esc(issue.location)}</p>` : ''}
                ${issue.suggestion ? `<p class="text-sm text-gray-800 mt-2"><span class="font-semibold">${esc(t('suggestion'))}:</span> ${esc(issue.suggestion)}</p>` : ''}
            </div>`;
        }).join('');
        $('verify-results').classList.remove('hidden');
        scrollToEl($('verify-results'));
    }

    // ---------- translate a document ----------

    const TRANSLATE_TYPES = ['txt', 'pdf'];
    let translateLangChosen = false;
    let lastTranslation = null;

    async function translateDocument(file) {
        hideError('translate-error');
        if (!checkFile(file, TRANSLATE_TYPES, 'translate-error')) return;
        $('translate-results').classList.add('hidden');
        $('translate-loading').classList.remove('hidden');
        scrollToEl($('translate-loading'));
        try {
            const body = await postJson('/translate/document', {
                userId,
                fileContent: await readAsBase64(file),
                filename: file.name,
                sourceLanguage: 'auto',
                targetLanguage: $('translate-language').value
            }, 'errGeneric');
            lastTranslation = Object.assign({ fileName: file.name }, body.data);
            bumpCounter('nyaya_docsTranslated');
            renderTranslation(lastTranslation);
        } catch (e) {
            let key = e.key || 'errGeneric';
            if (key === 'errVoiceUnavailable') key = 'errTranslateUnavailable';
            if (e.status === 400 && key === 'errGeneric') key = 'errDocUnreadable';
            showError('translate-error', key, e.status === 400 ? null : () => translateDocument(file));
        } finally {
            $('translate-loading').classList.add('hidden');
        }
    }

    function renderTranslation(data) {
        $('translate-filename').textContent = data.fileName || '';
        $('translate-original').textContent = data.originalText || '';
        $('translate-output').textContent = data.translatedText || '';
        $('translate-truncated').classList.toggle('hidden', !data.truncated);
        $('translate-results').classList.remove('hidden');
        scrollToEl($('translate-results'));
    }

    // ---------- my cases ----------

    function caseCard(c) {
        const emotion = c.emotion || {};
        return `<div class="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex flex-col">
            <div class="flex items-start justify-between gap-3 mb-3">
                <p class="text-xs text-gray-500">${esc(formatDate(c.date))}</p>
                ${levelBadge(emotion.urgency)}
            </div>
            <p class="font-bold text-nyaya-blue mb-2">${esc(c.category)}</p>
            <p class="text-sm text-gray-700 mb-4 flex-1">${esc(c.issueSummary)}</p>
            <button type="button" data-case="${esc(c.caseId)}" class="w-full px-4 py-2 bg-justice-gold text-nyaya-blue rounded-lg font-semibold hover:bg-justice-gold/90 transition-colors">${esc(t('viewDetails'))}</button>
        </div>`;
    }

    async function loadCases() {
        hideError('cases-error');
        $('cases-loading').classList.remove('hidden');
        $('cases-empty').classList.add('hidden');
        $('cases-list').innerHTML = '';
        try {
            casesCache = await fetchCases();
            renderCases(casesCache);
        } catch (e) {
            showError('cases-error', 'errCasesLoad', loadCases);
        } finally {
            $('cases-loading').classList.add('hidden');
        }
    }

    function renderCases(cases) {
        $('cases-empty').classList.toggle('hidden', cases.length > 0);
        $('cases-list').innerHTML = cases.map(caseCard).join('');
    }

    function showCase(caseId) {
        const c = (casesCache || []).find((x) => x.caseId === caseId);
        if (!c) return;
        const emotion = c.emotion || {};
        const parts = [
            `<div class="grid grid-cols-2 gap-4 mb-4">
                <div><p class="text-xs text-gray-500">${esc(t('date'))}</p><p class="font-semibold">${esc(formatDate(c.date))}</p></div>
                <div><p class="text-xs text-gray-500">${esc(t('category'))}</p><p class="font-semibold text-nyaya-blue">${esc(c.category)}</p></div>
                <div><p class="text-xs text-gray-500">${esc(t('urgency'))}</p>${levelBadge(emotion.urgency)}</div>
                <div><p class="text-xs text-gray-500">${esc(t('emotion'))}</p>${emotionBadge(emotion.primary)}</div>
            </div>`,
            card(t('fullText'), `<p class="text-sm text-gray-800 whitespace-pre-wrap">${esc(c.fullTranscription)}</p>`, 'bg-gray-50 border-gray-200')
        ];
        const facts = factsHtml(c.extractedFacts);
        if (facts) parts.push(card(t('facts'), facts, 'bg-blue-50 border-blue-200'));
        if (asList(c.relevantSections).length) parts.push(card(t('sections'), `<div class="space-y-2">${sectionsHtml(c.relevantSections)}</div>`));
        if (c.recommendation) parts.push(card(t('recommendation'), `<p class="text-sm text-gray-800 leading-relaxed">${richText(c.recommendation)}</p>`, 'bg-justice-gold/10 border-justice-gold/30'));
        if (asList(c.nextSteps).length) parts.push(card(t('nextSteps'), listHtml(c.nextSteps, true)));
        if (asList(c.requiredDocuments).length) parts.push(card(t('documents'), listHtml(c.requiredDocuments)));
        parts.push(`<button type="button" data-draft-case class="w-full mt-2 px-4 py-3 bg-justice-gold text-nyaya-blue rounded-lg font-semibold">${esc(t('draftPetition'))}</button>`);
        openModal(t('caseDetails'), `<div class="space-y-3">${parts.join('')}</div>`);
        $('modal-body').querySelector('[data-draft-case]').addEventListener('click', () => draftPetition({
            facts: c.extractedFacts, category: c.category, sections: c.relevantSections,
            language: c.language || uiLang, text: c.fullTranscription
        }));
    }

    // ---------- legal library ----------

    let libraryCategory = 'all';
    const LIBRARY_CATEGORIES = [
        ['all', 'catAll'], ['crime', 'catCrime'], ['women', 'catWomen'], ['police', 'catPolice'],
        ['money', 'catMoney'], ['work', 'catWork'], ['property', 'catProperty'], ['rights', 'catRights']
    ];

    function renderLibrary() {
        $('library-filters').innerHTML = LIBRARY_CATEGORIES.map(([cat, key]) => {
            const on = cat === libraryCategory;
            return `<button type="button" data-cat="${cat}" aria-pressed="${on}"
                class="px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${on ? 'bg-nyaya-blue text-white border-nyaya-blue' : 'bg-white text-gray-700 border-gray-300 hover:border-nyaya-blue'}">${esc(t(key))}</button>`;
        }).join('');

        const query = $('library-search').value.trim().toLowerCase();
        const entries = window.LEGAL_LIBRARY.filter((e) => {
            if (libraryCategory !== 'all' && e.cat !== libraryCategory) return false;
            if (!query) return true;
            return [e.act, e.section, e.old, e.title, e.text].join(' ').toLowerCase().includes(query);
        });
        $('library-list').innerHTML = entries.length ? entries.map((e) => `
            <div class="bg-white rounded-xl border border-gray-200 p-5">
                <div class="flex flex-wrap items-center gap-2 mb-2">
                    <span class="px-2 py-0.5 rounded bg-nyaya-blue text-white text-xs font-bold">${esc(e.act)} ${esc(/^\d/.test(e.section) ? 's. ' + e.section : e.section)}</span>
                    ${e.old ? `<span class="text-xs text-gray-500">${esc(t('oldLaw'))}: ${esc(e.old)}</span>` : ''}
                </div>
                <h4 class="font-bold text-gray-900 mb-1">${esc(e.title)}</h4>
                <p class="text-sm text-gray-700 leading-relaxed">${esc(e.text)}</p>
            </div>`).join('') : `<p class="text-gray-600 text-center py-8 col-span-full">${esc(t('noResults'))}</p>`;

        $('helpline-list').innerHTML = window.HELPLINES.map((h) => `
            <a href="tel:${esc(h.number)}" class="flex items-center justify-between gap-3 bg-white rounded-lg border border-gray-200 px-4 py-3 hover:border-justice-gold">
                <span class="text-sm text-gray-700">${esc(h.label)}</span>
                <span class="font-bold text-nyaya-blue">${esc(h.number)}</span>
            </a>`).join('');
    }

    // ---------- wiring ----------

    function init() {
        fillSelect($('issue-language'), ISSUE_LANGUAGES, 'en');
        fillSelect($('translate-language'), TRANSLATE_LANGUAGES, 'hi');

        // Navigation
        document.querySelectorAll('[data-go]').forEach((el) => el.addEventListener('click', (e) => {
            e.preventDefault();
            go(el.dataset.go);
        }));
        $('menu-button').addEventListener('click', () => openSidebar(true));
        $('sidebar-close').addEventListener('click', () => openSidebar(false));
        $('sidebar-backdrop').addEventListener('click', () => openSidebar(false));
        window.addEventListener('hashchange', () => showPage(location.hash.slice(1)));
        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape') return;
            if (!$('modal').classList.contains('hidden')) closeModal();
            else openSidebar(false);
        });

        // Language
        $('ui-language').addEventListener('change', (e) => applyLanguage(e.target.value));

        // Get legal help
        $('tab-voice').addEventListener('click', () => switchInputTab('voice'));
        $('tab-text').addEventListener('click', () => switchInputTab('text'));
        $('issue-language').addEventListener('change', () => { issueLangChosen = true; updateScriptToggle(); });
        $('script-native').addEventListener('click', () => { useNativeScript = true; updateScriptToggle(); });
        $('script-roman').addEventListener('click', () => { useNativeScript = false; updateScriptToggle(); });
        $('mic-button').addEventListener('click', toggleRecording);
        $('issue-text').addEventListener('input', () => {
            $('char-count').textContent = `${$('issue-text').value.length} / ${MAX_TEXT_LENGTH}`;
        });
        $('text-form').addEventListener('submit', (e) => {
            e.preventDefault();
            const text = $('issue-text').value.trim();
            if (!text) { showError('ask-error', 'errEmptyText'); return; }
            analyseIssue(text.slice(0, MAX_TEXT_LENGTH), $('issue-language').value);
        });
        $('draft-button').addEventListener('click', () => {
            if (!lastTriage) return;
            const c = lastTriage.classification || {};
            draftPetition({
                facts: lastTriage.extractedFacts, category: c.category, sections: c.relevantSections,
                language: lastTriageInput ? lastTriageInput.language : uiLang, text: lastTriage.transcription
            });
        });
        $('new-question').addEventListener('click', () => {
            lastTriage = null;
            $('ask-results').classList.add('hidden');
            $('issue-text').value = '';
            $('char-count').textContent = `0 / ${MAX_TEXT_LENGTH}`;
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });

        // Documents
        setupDropZone('verify-drop', 'verify-file', verifyDocument);
        setupDropZone('translate-drop', 'translate-file', translateDocument);
        $('translate-language').addEventListener('change', () => { translateLangChosen = true; });
        $('verify-again').addEventListener('click', () => {
            lastVerification = null;
            $('verify-results').classList.add('hidden');
            $('verify-file').click();
        });
        $('translate-again').addEventListener('click', () => {
            lastTranslation = null;
            $('translate-results').classList.add('hidden');
            $('translate-file').click();
        });
        $('translate-copy').addEventListener('click', (e) => copyText($('translate-output').textContent, e.currentTarget));
        $('translate-download').addEventListener('click', () => {
            const base = (lastTranslation && lastTranslation.fileName || 'document').replace(/\.[^.]+$/, '');
            downloadText($('translate-output').textContent, base + '-translated.txt');
        });

        // Cases (event delegation for cards on home and cases pages)
        document.addEventListener('click', (e) => {
            const button = e.target.closest('[data-case]');
            if (button) showCase(button.dataset.case);
        });
        $('modal-close').addEventListener('click', closeModal);
        $('modal').addEventListener('click', (e) => { if (e.target === $('modal')) closeModal(); });

        // Library
        $('library-search').addEventListener('input', renderLibrary);
        $('library-filters').addEventListener('click', (e) => {
            const button = e.target.closest('[data-cat]');
            if (!button) return;
            libraryCategory = button.dataset.cat;
            renderLibrary();
        });

        $('char-count').textContent = `0 / ${MAX_TEXT_LENGTH}`;
        $('issue-text').maxLength = MAX_TEXT_LENGTH;
        currentPage = PAGES.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'home';
        switchInputTab('voice');
        setMicState('idle');
        applyLanguage(storageGet('ui-language') || 'en');
        showPage(currentPage);
    }

    document.addEventListener('DOMContentLoaded', init);
})();
