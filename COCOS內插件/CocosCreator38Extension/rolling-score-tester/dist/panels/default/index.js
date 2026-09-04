'use strict';

const packageJSON = require('../../../package.json');
const { clamp, ease, finite, formatValue } = require('../../shared');

const STRESS_CASES = [
    '44444', '41414', '11111', '99999',
    '0', '1,000', '9,999', '9.99K', '123.45M', '999,999,999.99T'
];
// Editor.Message 每次都要跨到 Scene 程序。60 FPS 會讓浮動面板的計時遠快於
// Scene View/Inspector 的實際更新，因此 QA 模式限制在穩定且足以目視的 15 FPS。
const MAX_SCENE_FPS = 15;

function round(value, digits = 3) {
    return Number(finite(value).toFixed(digits));
}

function summarize(samples, target) {
    const actual = samples.map((item) => finite(item.actualFontSize, NaN)).filter(Number.isFinite);
    const ratios = samples.map((item) => finite(item.scaleRatio, NaN)).filter(Number.isFinite);
    const shrinkSamples = samples.filter((item) => item.fontSize > 0 && item.actualFontSize < item.fontSize - 0.01);
    const widthsByLength = new Map();
    for (const item of samples) {
        if (!Number.isFinite(item.renderWidth)) continue;
        const key = String(item.text).length;
        if (!widthsByLength.has(key)) widthsByLength.set(key, []);
        widthsByLength.get(key).push(item);
    }
    const widthDrift = [];
    for (const [length, items] of widthsByLength) {
        const values = items.map((item) => item.renderWidth);
        const min = Math.min(...values);
        const max = Math.max(...values);
        if (max - min > 1) {
            widthDrift.push({ length, min: round(min), max: round(max), delta: round(max - min) });
        }
    }
    return {
        target: target ? {
            path: target.path,
            fontName: target.fontName,
            bitmapFont: target.bitmapFont,
            overflow: target.overflow,
            fontSize: target.fontSize,
            lineHeight: target.lineHeight,
            spacingX: target.spacingX,
            boxWidth: target.boxWidth,
            boxHeight: target.boxHeight
        } : null,
        sampleCount: samples.length,
        shrinkDetected: shrinkSamples.length > 0,
        shrinkSampleCount: shrinkSamples.length,
        minimumActualFontSize: actual.length ? Math.min(...actual) : null,
        maximumActualFontSize: actual.length ? Math.max(...actual) : null,
        actualFontSizeChanged: actual.length ? Math.max(...actual) - Math.min(...actual) > 0.01 : false,
        minimumScaleRatio: ratios.length ? round(Math.min(...ratios), 4) : null,
        sameLengthWidthDrift: widthDrift,
        renderWidthAvailable: samples.some((item) => Number.isFinite(item.renderWidth))
    };
}

module.exports = Editor.Panel.define({
    template: `
        <div id="app">
            <header>
                <div>
                    <h1>滾分 QA 測試工具</h1>
                    <p>直接在 Scene 檢查 BMFont 字距跳動與 Cocos SHRINK。</p>
                </div>
                <span class="version">v${packageJSON.version}</span>
            </header>

            <section class="target card">
                <div class="section-title"><span>1</span> 測試目標</div>
                <div class="target-row">
                    <button id="bind" class="primary">綁定目前選取</button>
                    <select id="targets" disabled><option>尚未綁定 Label</option></select>
                    <button id="refresh" disabled>重新讀取</button>
                </div>
                <div id="target-info" class="info empty">請在 Hierarchy 選取 Label 或其父節點。</div>
            </section>

            <main>
                <section class="card settings">
                    <div class="section-title"><span>2</span> 滾分設定</div>
                    <div class="form-grid">
                        <label>起始值<input id="start-value" type="number" value="0" step="1"></label>
                        <label>結束值<input id="end-value" type="number" value="999999" step="1"></label>
                        <label>秒數<input id="duration" type="number" value="2" min="0.05" step="0.1"></label>
                        <label>Scene 更新 FPS<input id="fps" type="number" value="15" min="1" max="15" step="1"></label>
                        <label>小數位<input id="decimals" type="number" value="0" min="0" max="8" step="1"></label>
                        <label>Easing<select id="easing"><option value="linear">Linear</option><option value="ease-out" selected>Ease Out</option><option value="ease-in">Ease In</option><option value="ease-in-out">Ease In Out</option></select></label>
                        <label>前綴<input id="prefix" type="text" value=""></label>
                        <label>後綴<input id="suffix" type="text" value=""></label>
                    </div>
                    <div class="checks">
                        <label><input id="thousands" type="checkbox" checked> 千分位</label>
                        <label><input id="compact" type="checkbox"> 自動 K / M / B / T</label>
                        <label><input id="loop" type="checkbox"> 循環</label>
                    </div>
                    <div class="actions">
                        <button id="start" class="run" disabled>▶ 開始滾分</button>
                        <button id="pause" disabled>暫停</button>
                        <button id="stop" disabled>停止</button>
                        <button id="reset" disabled>還原字串</button>
                    </div>
                    <button id="stress" class="stress" disabled>字距／縮放壓力測試</button>
                    <p class="stress-hint">依序測試 44444、41414、11111、99999、千分位與超長值。</p>
                </section>

                <section class="card monitor">
                    <div class="section-title"><span>3</span> 即時監測</div>
                    <div class="value-preview" id="preview">—</div>
                    <div class="meters">
                        <div><small>設定字級</small><strong id="font-size">—</strong></div>
                        <div><small>實際字級</small><strong id="actual-size">—</strong></div>
                        <div><small>縮放比例</small><strong id="scale-ratio">—</strong></div>
                        <div><small>渲染寬度</small><strong id="render-width">—</strong></div>
                    </div>
                    <div id="diagnosis" class="diagnosis idle">等待測試</div>
                    <div class="summary-grid">
                        <span>樣本 <b id="sample-count">0</b></span>
                        <span>縮小樣本 <b id="shrink-count">0</b></span>
                        <span>最小字級 <b id="min-size">—</b></span>
                        <span>寬度漂移 <b id="drift-count">0</b></span>
                    </div>
                    <button id="copy" disabled>複製 JSON 報告</button>
                </section>
            </main>

            <footer id="status">待命</footer>
        </div>
    `,
    style: `
        :host { display:block; width:100%; height:100%; color:#e0e5e9; font:13px "Segoe UI","Microsoft JhengHei",sans-serif; }
        * { box-sizing:border-box; }
        #app { min-height:100%; padding:16px; overflow:auto; background:linear-gradient(145deg,#171c21,#111519 55%,#17222a); }
        header { display:flex; align-items:flex-start; justify-content:space-between; margin-bottom:13px; }
        h1 { margin:0; color:#f2f8fc; font-size:20px; letter-spacing:.4px; }
        header p { margin:4px 0 0; color:#82919b; }
        .version { padding:4px 8px; border:1px solid #355b70; border-radius:12px; color:#77cef9; background:#173142; }
        .card { border:1px solid #303a41; border-radius:8px; background:rgba(35,42,48,.9); box-shadow:0 7px 22px rgba(0,0,0,.2); }
        .target { padding:13px; margin-bottom:12px; }
        .section-title { display:flex; align-items:center; gap:7px; margin-bottom:11px; color:#dce8ee; font-weight:700; }
        .section-title span { display:inline-flex; align-items:center; justify-content:center; width:20px; height:20px; border-radius:50%; color:#10202a; background:#69c9f5; font-size:11px; }
        .target-row { display:grid; grid-template-columns:auto minmax(180px,1fr) auto; gap:7px; }
        button,select,input { font:inherit; }
        button { min-height:30px; padding:4px 10px; border:1px solid #46535d; border-radius:5px; color:#dce3e8; background:#333d44; cursor:pointer; }
        button:hover:not(:disabled) { background:#40505a; border-color:#607584; }
        button:disabled { opacity:.38; cursor:default; }
        button.primary,.run { color:#09202d; border-color:#6fd0fb; background:#62c3ef; font-weight:700; }
        button.primary:hover:not(:disabled),.run:hover:not(:disabled) { background:#83d8fd; }
        select,input { width:100%; height:30px; padding:4px 7px; border:1px solid #414d55; border-radius:4px; color:#edf2f5; background:#171d21; }
        .info { margin-top:9px; padding:8px 10px; border-left:3px solid #4b9dc5; color:#abc3d0; background:#18252c; overflow-wrap:anywhere; }
        .info.empty { border-color:#5a6268; color:#818a91; }
        main { display:grid; grid-template-columns:minmax(330px,1.15fr) minmax(300px,.85fr); gap:12px; }
        .settings,.monitor { padding:13px; min-height:370px; }
        .form-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:9px 11px; }
        .form-grid label { display:flex; flex-direction:column; gap:4px; color:#9eabb3; font-size:12px; }
        .checks { display:flex; flex-wrap:wrap; gap:14px; margin:12px 0; color:#b8c3ca; }
        .checks label { display:flex; align-items:center; gap:5px; }
        input[type=checkbox] { width:auto; height:auto; }
        .actions { display:grid; grid-template-columns:1.4fr repeat(3,1fr); gap:6px; }
        .stress { width:100%; margin-top:10px; border-color:#8d7134; color:#ffe19b; background:#4d4025; }
        .stress:hover:not(:disabled) { background:#67542d; border-color:#b79444; }
        .stress-hint { margin:6px 1px 0; color:#727e85; font-size:11px; }
        .value-preview { min-height:66px; display:flex; align-items:center; justify-content:center; padding:8px; border:1px solid #35444d; border-radius:6px; color:#fff; background:#11181d; font-size:26px; font-weight:700; word-break:break-all; text-align:center; }
        .meters { display:grid; grid-template-columns:repeat(2,1fr); gap:7px; margin-top:9px; }
        .meters div { padding:8px; border:1px solid #354047; border-radius:5px; background:#1a2227; }
        .meters small { display:block; color:#7f8d96; }
        .meters strong { display:block; margin-top:2px; color:#dcecf4; font-size:17px; }
        .diagnosis { margin-top:9px; padding:10px; border-radius:5px; border:1px solid #485159; color:#aab3b9; background:#20262a; }
        .diagnosis.pass { border-color:#327b50; color:#a9edbf; background:#193225; }
        .diagnosis.warn { border-color:#a8792f; color:#ffd993; background:#3b2e19; }
        .diagnosis.fail { border-color:#a44a49; color:#ffaaa7; background:#3a1d1e; }
        .summary-grid { display:grid; grid-template-columns:1fr 1fr; gap:5px; margin:10px 0; color:#89979f; font-size:12px; }
        .summary-grid b { color:#d5e0e6; }
        #copy { width:100%; }
        footer { margin-top:11px; min-height:26px; padding:5px 9px; border-radius:4px; color:#8e9ba3; background:#151b1f; }
        footer.success { color:#8fe6ac; }
        footer.error { color:#ff9994; }
        @media(max-width:760px) { main { grid-template-columns:1fr; } .target-row { grid-template-columns:1fr; } .actions { grid-template-columns:1fr 1fr; } }
    `,
    $: {
        bind: '#bind', targets: '#targets', refresh: '#refresh', targetInfo: '#target-info',
        startValue: '#start-value', endValue: '#end-value', duration: '#duration', fps: '#fps',
        decimals: '#decimals', easing: '#easing', prefix: '#prefix', suffix: '#suffix',
        thousands: '#thousands', compact: '#compact', loop: '#loop',
        start: '#start', pause: '#pause', stop: '#stop', reset: '#reset', stress: '#stress',
        preview: '#preview', fontSize: '#font-size', actualSize: '#actual-size',
        scaleRatio: '#scale-ratio', renderWidth: '#render-width', diagnosis: '#diagnosis',
        sampleCount: '#sample-count', shrinkCount: '#shrink-count', minSize: '#min-size',
        driftCount: '#drift-count', copy: '#copy', status: '#status'
    },
    methods: {
        setStatus(text, kind = '') {
            this.$.status.textContent = text;
            this.$.status.className = kind;
        },

        async bindSelection() {
            try {
                await this.stopRun(true);
                const labels = await Editor.Message.request(packageJSON.name, 'bind-selection');
                this.labels = labels || [];
                this.$.targets.innerHTML = '';
                for (const [index, label] of this.labels.entries()) {
                    const option = document.createElement('option');
                    option.value = String(index);
                    option.textContent = `${label.path || label.name}  [${label.fontName}]`;
                    this.$.targets.appendChild(option);
                }
                this.$.targets.disabled = !this.labels.length;
                this.$.refresh.disabled = !this.labels.length;
                this.selectTarget(0);
                this.setStatus(`找到 ${this.labels.length} 個 Label`, 'success');
            } catch (error) {
                this.setStatus(error.message || String(error), 'error');
            }
        },

        selectTarget(index) {
            this.target = this.labels[Number(index)] || null;
            this.samples = [];
            this.updateTargetInfo();
            this.updateSummary();
            this.setEnabled(!!this.target);
        },

        async changeTarget(index) {
            await this.stopRun(true);
            this.selectTarget(index);
            await this.refreshTarget();
        },

        async refreshTarget() {
            if (!this.target) return;
            try {
                this.target = await Editor.Message.request(packageJSON.name, 'inspect-target', this.target);
                const index = Number(this.$.targets.value);
                if (this.labels[index]) this.labels[index] = this.target;
                this.updateTargetInfo();
                this.updateMetrics(this.target);
                this.setStatus('Label 資訊已更新', 'success');
            } catch (error) {
                this.setStatus(error.message || String(error), 'error');
            }
        },

        updateTargetInfo() {
            const target = this.target;
            if (!target) {
                this.$.targetInfo.textContent = '請在 Hierarchy 選取 Label 或其父節點。';
                this.$.targetInfo.className = 'info empty';
                return;
            }
            this.$.targetInfo.className = 'info';
            this.$.targetInfo.textContent = `${target.path} ｜ ${target.bitmapFont ? 'BMFont' : '系統字型'}: ${target.fontName} ｜ Overflow ${target.overflow} ｜ Box ${round(target.boxWidth)}×${round(target.boxHeight)} ｜ spacingX ${target.spacingX} ｜ node scale ${round(target.nodeScaleX)}×${round(target.nodeScaleY)}`;
        },

        setEnabled(enabled) {
            for (const element of [this.$.start, this.$.stress, this.$.reset]) element.disabled = !enabled;
            this.$.copy.disabled = !this.samples.length;
        },

        options() {
            return {
                decimals: clamp(Math.trunc(finite(this.$.decimals.value)), 0, 8),
                thousands: this.$.thousands.checked,
                compact: this.$.compact.checked,
                prefix: this.$.prefix.value,
                suffix: this.$.suffix.value
            };
        },

        async apply(text, mode, progress) {
            if (!this.target || this.requestBusy) return;
            this.requestBusy = true;
            try {
                const metrics = await Editor.Message.request(packageJSON.name, 'apply-text', {
                    target: this.target,
                    text
                });
                const sample = {
                    timeMs: Date.now(), mode, progress: round(progress, 4), text: metrics.text ?? text,
                    fontSize: metrics.fontSize,
                    actualFontSize: metrics.actualFontSize,
                    scaleRatio: metrics.scaleRatio,
                    boxWidth: metrics.boxWidth,
                    boxHeight: metrics.boxHeight,
                    renderWidth: metrics.renderWidth,
                    renderHeight: metrics.renderHeight
                };
                this.samples.push(sample);
                if (this.samples.length > 6000) this.samples.shift();
                this.updateMetrics(sample);
                this.updateSummary();
            } catch (error) {
                this.running = false;
                this.setStatus(error.message || String(error), 'error');
            } finally {
                this.requestBusy = false;
            }
        },

        async startRoll() {
            if (!this.target) return;
            this.cancelFrame();
            this.samples = [];
            this.running = true;
            this.paused = false;
            this.mode = 'roll';
            this.lastSentAt = -Infinity;
            this.$.start.disabled = true;
            this.$.stress.disabled = true;
            this.$.pause.disabled = false;
            this.$.pause.textContent = '暫停';
            this.$.stop.disabled = false;
            this.setStatus('正在讓 Scene 確認起始值…');
            const start = finite(this.$.startValue.value);
            await this.apply(formatValue(start, this.options()), 'roll', 0);
            if (!this.running) return;
            this.startedAt = performance.now();
            this.lastSentAt = this.startedAt;
            this.setStatus(`滾分測試中…（Scene ${Math.min(MAX_SCENE_FPS, finite(this.$.fps.value, MAX_SCENE_FPS))} FPS）`);
            this.frameHandle = requestAnimationFrame((time) => this.tickRoll(time));
        },

        tickRoll(now) {
            if (!this.running || this.mode !== 'roll') return;
            if (this.paused) {
                this.frameHandle = requestAnimationFrame((time) => this.tickRoll(time));
                return;
            }
            const durationMs = Math.max(50, finite(this.$.duration.value, 2) * 1000);
            const raw = (now - this.startedAt) / durationMs;
            const progress = clamp(raw, 0, 1);
            const fps = clamp(finite(this.$.fps.value, MAX_SCENE_FPS), 1, MAX_SCENE_FPS);
            if (now - this.lastSentAt >= 1000 / fps || progress >= 1) {
                const start = finite(this.$.startValue.value);
                const end = finite(this.$.endValue.value);
                const value = start + (end - start) * ease(this.$.easing.value, progress);
                void this.apply(formatValue(value, this.options()), 'roll', progress);
                this.lastSentAt = now;
            }
            if (raw >= 1) {
                if (this.$.loop.checked) {
                    this.startedAt = now;
                } else {
                    this.finishRun('滾分完成；畫面保留終值，按「還原字串」可復原。');
                    return;
                }
            }
            this.frameHandle = requestAnimationFrame((time) => this.tickRoll(time));
        },

        startStress() {
            if (!this.target) return;
            this.cancelFrame();
            this.samples = [];
            this.running = true;
            this.paused = false;
            this.mode = 'stress';
            this.startedAt = performance.now();
            this.stressIndex = -1;
            this.$.start.disabled = true;
            this.$.stress.disabled = true;
            this.$.pause.disabled = false;
            this.$.pause.textContent = '暫停';
            this.$.stop.disabled = false;
            this.setStatus('字距／縮放壓力測試中…');
            this.frameHandle = requestAnimationFrame((time) => this.tickStress(time));
        },

        tickStress(now) {
            if (!this.running || this.mode !== 'stress') return;
            if (this.paused) {
                this.frameHandle = requestAnimationFrame((time) => this.tickStress(time));
                return;
            }
            const index = Math.floor((now - this.startedAt) / 550);
            if (index >= STRESS_CASES.length) {
                this.finishRun('壓力測試完成；請查看診斷結果。');
                return;
            }
            if (index !== this.stressIndex) {
                this.stressIndex = index;
                void this.apply(STRESS_CASES[index], 'stress', index / (STRESS_CASES.length - 1));
            }
            this.frameHandle = requestAnimationFrame((time) => this.tickStress(time));
        },

        togglePause() {
            if (!this.running) return;
            this.paused = !this.paused;
            if (this.paused) {
                this.pausedAt = performance.now();
                this.$.pause.textContent = '繼續';
                this.setStatus('已暫停');
            } else {
                this.startedAt += performance.now() - this.pausedAt;
                this.$.pause.textContent = '暫停';
                this.setStatus(this.mode === 'stress' ? '壓力測試中…' : '滾分測試中…');
            }
        },

        finishRun(message) {
            this.running = false;
            this.cancelFrame();
            this.$.start.disabled = !this.target;
            this.$.stress.disabled = !this.target;
            this.$.pause.disabled = true;
            this.$.stop.disabled = true;
            this.$.copy.disabled = !this.samples.length;
            this.setStatus(message, 'success');
        },

        async stopRun(restore = true) {
            this.running = false;
            this.cancelFrame();
            this.$.start.disabled = !this.target;
            this.$.stress.disabled = !this.target;
            this.$.pause.disabled = true;
            this.$.stop.disabled = true;
            if (restore) await this.restore();
        },

        cancelFrame() {
            if (this.frameHandle) cancelAnimationFrame(this.frameHandle);
            this.frameHandle = 0;
        },

        async restore() {
            try {
                await Editor.Message.request(packageJSON.name, 'restore-preview');
                if (this.target) await this.refreshTarget();
                this.setStatus('已還原測試前的 Label 字串', 'success');
            } catch (error) {
                this.setStatus(error.message || String(error), 'error');
            }
        },

        updateMetrics(item) {
            this.$.preview.textContent = item.text ?? '—';
            this.$.fontSize.textContent = Number.isFinite(item.fontSize) ? round(item.fontSize) : '—';
            this.$.actualSize.textContent = Number.isFinite(item.actualFontSize) ? round(item.actualFontSize) : '—';
            this.$.scaleRatio.textContent = Number.isFinite(item.scaleRatio) ? `${round(item.scaleRatio * 100, 1)}%` : '—';
            this.$.renderWidth.textContent = Number.isFinite(item.renderWidth) ? round(item.renderWidth) : 'N/A';
        },

        updateSummary() {
            const summary = summarize(this.samples, this.target);
            this.summary = summary;
            this.$.sampleCount.textContent = String(summary.sampleCount);
            this.$.shrinkCount.textContent = String(summary.shrinkSampleCount);
            this.$.minSize.textContent = summary.minimumActualFontSize === null ? '—' : round(summary.minimumActualFontSize);
            this.$.driftCount.textContent = String(summary.sameLengthWidthDrift.length);
            this.$.copy.disabled = !this.samples.length;
            if (!this.samples.length) {
                this.$.diagnosis.textContent = '等待測試';
                this.$.diagnosis.className = 'diagnosis idle';
            } else if (summary.shrinkDetected) {
                this.$.diagnosis.textContent = `偵測到 SHRINK：最小 actualFontSize ${round(summary.minimumActualFontSize)}（${round(summary.minimumScaleRatio * 100, 1)}%）`;
                this.$.diagnosis.className = 'diagnosis fail';
            } else if (summary.sameLengthWidthDrift.length) {
                this.$.diagnosis.textContent = '字級沒有縮小，但相同字數的渲染寬度不同；請檢查 BMFont xadvance／xoffset。';
                this.$.diagnosis.className = 'diagnosis warn';
            } else {
                this.$.diagnosis.textContent = summary.renderWidthAvailable
                    ? '未偵測到字級縮小或同字數寬度漂移。'
                    : '未偵測到字級縮小；此 Creator 組版未回傳渲染頂點寬度，請搭配 Scene 目視字距。';
                this.$.diagnosis.className = 'diagnosis pass';
            }
        },

        async copyReport() {
            const report = {
                schema: 'rolling-score-qa@1',
                generatedAt: new Date().toISOString(),
                creatorTarget: '3.8.x',
                settings: {
                    start: finite(this.$.startValue.value), end: finite(this.$.endValue.value),
                    duration: finite(this.$.duration.value), fps: finite(this.$.fps.value),
                    decimals: finite(this.$.decimals.value), easing: this.$.easing.value,
                    thousands: this.$.thousands.checked, compact: this.$.compact.checked,
                    prefix: this.$.prefix.value, suffix: this.$.suffix.value
                },
                summary: summarize(this.samples, this.target),
                samples: this.samples
            };
            try {
                await Editor.Message.request(packageJSON.name, 'copy-report', report);
                this.setStatus('JSON 報告已複製到剪貼簿', 'success');
            } catch (error) {
                this.setStatus(error.message || String(error), 'error');
            }
        }
    },

    ready() {
        this.labels = [];
        this.target = null;
        this.samples = [];
        this.summary = summarize([], null);
        this.running = false;
        this.paused = false;
        this.requestBusy = false;
        this.frameHandle = 0;
        this.$.bind.addEventListener('click', () => void this.bindSelection());
        this.$.targets.addEventListener('change', () => void this.changeTarget(this.$.targets.value));
        this.$.refresh.addEventListener('click', () => void this.refreshTarget());
        this.$.start.addEventListener('click', () => void this.startRoll());
        this.$.stress.addEventListener('click', () => this.startStress());
        this.$.pause.addEventListener('click', () => this.togglePause());
        this.$.stop.addEventListener('click', () => void this.stopRun(true));
        this.$.reset.addEventListener('click', () => void this.stopRun(true));
        this.$.copy.addEventListener('click', () => void this.copyReport());
        this.updateSummary();
    },

    close() {
        this.running = false;
        this.cancelFrame();
        void Editor.Message.request(packageJSON.name, 'restore-preview').catch(() => {});
    }
});
