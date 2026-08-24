'use strict';

const packageJSON = require('../../../package.json');

const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const number = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
const round = (value, digits = 3) => Number(number(value).toFixed(digits));
const uid = (prefix) => `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
const MIN_TIMELINE_ZOOM = 0.1;
const MAX_TIMELINE_ZOOM = 32;

function freshProject() {
    return {
        schema: 'cocos-native-timeline@1',
        name: 'MainTimeline',
        duration: 5,
        autoDuration: true,
        fps: 30,
        loop: false,
        tracks: []
    };
}

function interpolateKeys(keys, time, fallback) {
    if (!keys || !keys.length) return fallback;
    const sorted = [...keys].sort((a, b) => a.time - b.time);
    if (time <= sorted[0].time) return sorted[0];
    if (time >= sorted[sorted.length - 1].time) return sorted[sorted.length - 1];
    const rightIndex = sorted.findIndex((key) => key.time >= time);
    const left = sorted[Math.max(0, rightIndex - 1)];
    const right = sorted[rightIndex];
    const ratio = right.time === left.time ? 0 : (time - left.time) / (right.time - left.time);
    const result = { ...left, time };
    for (const field of ['x', 'y', 'z', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz', 'opacity']) {
        if (Number.isFinite(Number(left[field])) && Number.isFinite(Number(right[field]))) {
            result[field] = number(left[field]) + (number(right[field]) - number(left[field])) * ratio;
        }
    }
    result.active = ratio < 1 ? left.active : right.active;
    return result;
}

function sameTransform(a, b) {
    if (!a || !b) return false;
    return ['x', 'y', 'z', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz', 'opacity']
        .every((field) => Math.abs(number(a[field]) - number(b[field])) < 0.0001)
        && a.active === b.active;
}

function lanesForTrack(track) {
    const lanes = [{ type: 'transform', title: 'Transform', icon: '◇' }];
    if (track.capabilities.spine) lanes.push({ type: 'spine', title: 'Spine Animation', icon: 'S' });
    if (track.capabilities.particle2d) lanes.push({ type: 'particle2d', title: 'Particle System 2D', icon: '✦' });
    if (track.capabilities.particle3d) lanes.push({ type: 'particle3d', title: 'Particle System 3D', icon: '✦' });
    if (track.capabilities.animation) lanes.push({ type: 'animation', title: 'Cocos Animation', icon: 'A' });
    return lanes;
}

module.exports = Editor.Panel.define({
    template: `
        <div id="app">
            <div class="toolbar">
                <button id="new-project" class="file" title="建立新的空白 Timeline">📄</button>
                <button id="save" class="file" title="儲存 Timeline">💾</button>
                <button id="load" class="file" title="開啟 Assets 中選取的 Timeline">📂</button>
                <span class="separator"></span>
                <button id="to-start" title="第一幀">⏮</button>
                <button id="previous-frame" title="上一幀">◀</button>
                <button id="play" class="play" title="播放 / 暫停">▶</button>
                <button id="next-frame" title="下一幀">▶|</button>
                <button id="stop" title="停止並還原 Scene">■</button>
                <button id="record" class="record" title="錄製 Scene Transform 變更">●</button>
                <button id="magnet" class="mode active" title="吸附播放頭、片段邊界與時間軸邊界">🧲 磁吸</button>
                <button id="ripple" class="mode active" title="移動或拉長片段時推動後續片段">⇥ 推擠</button>
                <button id="zoom-fit" class="mode" title="重設時間軸縮放並顯示完整長度">Fit 100%</button>
                <label class="time-box"><input id="time" type="number" min="0" step="0.033" value="0"> s</label>
                <span class="separator"></span>
                <label>Timeline <input id="project-name" type="text" value="MainTimeline"></label>
                <label>長度 <input id="duration" type="number" min="0.1" step="0.1" value="5"></label>
                <label title="依最後一個動畫片段或 Transform 關鍵幀自動設定長度"><input id="auto-duration" type="checkbox" checked> 自動長度</label>
                <label>FPS <input id="fps" type="number" min="1" max="120" step="1" value="30"></label>
                <label><input id="loop" type="checkbox"> Loop</label>
                <span id="drag-monitor">v0.13.0｜拖放待命</span>
                <span id="status">拖曳 Hierarchy 物件到下方 Timeline</span>
            </div>
            <ui-drag-area id="workspace" droppable="cc.Node">
                <div id="track-panel">
                    <div class="track-header">
                        <button id="add-selected" title="將 Hierarchy 選取物件加入 Timeline">＋</button>
                        <span>Tracks</span>
                    </div>
                    <div id="labels-scroll"><div id="labels"></div></div>
                </div>
                <div id="time-panel">
                    <div id="time-scroll">
                        <div id="timeline-content">
                            <div id="ruler"></div>
                            <div id="rows"></div>
                            <div id="playhead"></div>
                        </div>
                    </div>
                    <div id="drop-empty">
                        <div class="drop-icon">＋</div>
                        <strong>將 Hierarchy 物件拖到這裡</strong>
                        <span>接收 Cocos 的 cc.Node 拖放並自動建立元件軌道</span>
                        <div id="pending-binding">
                            <span id="pending-selection">目前未選取 Scene 節點</span>
                            <button id="bind-pending" disabled>將目前選取加入 Timeline</button>
                        </div>
                    </div>
                    <div id="drop-overlay">放開以建立物件軌道</div>
                </div>
                <aside id="inspector">
                    <div class="inspector-head">Inspector</div>
                    <div id="inspector-empty">
                        選取物件軌道、動畫片段或 Transform Key
                    </div>
                    <div id="track-inspector" hidden></div>
                    <div id="item-inspector" hidden>
                        <div class="field-row"><label id="item-start-label">Start</label><input id="item-start" type="number" min="0" step="0.033"></div>
                        <div id="duration-row" class="field-row"><label>Duration</label><input id="item-duration" type="number" min="0.033" step="0.033"></div>
                        <div id="animation-row" class="field-row"><label>Animation</label><select id="item-animation"></select></div>
                        <div id="loop-row" class="field-row"><label>Loop</label><input id="item-loop" type="checkbox"></div>
                        <button id="delete-item" class="danger wide">Delete</button>
                    </div>
                    <div class="help">
                        <b>Unity 式操作</b>
                        <span>雙擊空白軌道：建立片段／Key</span>
                        <span>拖曳片段：調整開始時間</span>
                        <span>拖曳片段兩端：調整長度</span>
                        <span>紅色 ●：錄製 Scene Transform</span>
                    </div>
                </aside>
            </ui-drag-area>
            <div id="context-menu" hidden></div>
        </div>
    `,
    style: `
        :host { display:block; width:100%; height:100%; color:#d7d9dc; font:12px "Segoe UI",sans-serif; }
        * { box-sizing:border-box; }
        #app { position:relative; width:100%; height:100%; display:flex; flex-direction:column; overflow:hidden; background:#1c1d20; }
        button,input,select { font:inherit; }
        button { height:24px; border:1px solid #484c52; border-radius:2px; background:#35383d; color:#e5e5e5; padding:2px 7px; cursor:pointer; }
        button:hover { background:#474b51; }
        button:disabled { opacity:.38; cursor:default; }
        input,select { height:23px; border:1px solid #454950; border-radius:2px; background:#24262a; color:#ededed; padding:2px 5px; }
        input[type=number] { width:64px; }
        input[type=checkbox] { width:auto; height:auto; }
        .toolbar { min-height:36px; display:flex; align-items:center; gap:5px; flex:0 0 auto; padding:5px 7px; border-bottom:1px solid #42464b; background:#292b2f; }
        .toolbar label { display:flex; align-items:center; gap:4px; white-space:nowrap; color:#b8bbc0; }
        .toolbar button.file { font-size:13px; padding:1px 6px; }
        .toolbar button.play { color:#7fe581; }
        .toolbar button.record { color:#ff6861; border-radius:50%; font-size:15px; padding:0; width:24px; }
        .toolbar button.record.active { color:#fff; background:#c73535; border-color:#ff6b65; box-shadow:0 0 6px #e33; }
        .toolbar button.mode { color:#aeb3b9; }
        .toolbar button.mode.active { color:#fff; border-color:#2992cf; background:#176894; }
        .separator { height:20px; border-left:1px solid #50545a; margin:0 2px; }
        .time-box input { color:#70c9ff; text-align:right; }
        #project-name { width:115px; }
        #status { min-width:60px; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; text-align:right; color:#969aa0; }
        #status.success { color:#78db91; }
        #status.error { color:#ff7c75; }
        #drag-monitor { padding:3px 6px; border:1px solid #4b5056; border-radius:3px; color:#aeb3b9; background:#23262a; white-space:nowrap; }
        #drag-monitor.active { color:#dff5ff; border-color:#2992cf; background:#175d82; }
        #drag-monitor.success { color:#b9f5c8; border-color:#2e8f51; background:#205c35; }
        #workspace { min-height:0; flex:1; display:grid; grid-template-columns:235px minmax(360px,1fr) 225px; }
        #workspace[hoving] #time-panel { outline:2px solid #52b8f5; outline-offset:-2px; }
        #track-panel { min-width:0; display:flex; flex-direction:column; border-right:1px solid #45494e; background:#25272a; z-index:4; }
        .track-header,.inspector-head { height:31px; flex:0 0 31px; display:flex; align-items:center; gap:7px; padding:3px 7px; border-bottom:1px solid #44484d; background:#2d3034; color:#c5c8cc; font-weight:600; }
        .track-header button { width:25px; padding:0; font-size:16px; }
        #labels-scroll { position:relative; flex:1; overflow:hidden; }
        #labels { position:absolute; top:0; left:0; right:0; }
        .object-label { height:28px; display:flex; align-items:center; gap:5px; padding:0 6px; border-bottom:1px solid #44474c; background:#303338; cursor:pointer; }
        .object-label.selected { background:#174e75; }
        .fold { width:14px; text-align:center; color:#aeb2b7; }
        .object-icon { width:16px; height:16px; display:inline-flex; align-items:center; justify-content:center; border-radius:2px; background:#52565c; font-size:10px; }
        .object-name { min-width:0; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .object-remove { width:20px; height:20px; padding:0; border:0; background:transparent; color:#c9cbd0; }
        .lane-label { height:32px; display:flex; align-items:center; gap:6px; padding:0 6px 0 24px; border-bottom:1px solid #383b3f; color:#aeb2b8; }
        .lane-icon { width:16px; height:16px; display:inline-flex; align-items:center; justify-content:center; border-radius:2px; background:#3f4349; font-size:9px; color:#d6dae0; }
        .lane-title { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .add-item { width:20px; height:20px; padding:0; border:0; background:transparent; font-size:15px; color:#bfc3c8; }
        #time-panel { position:relative; min-width:0; min-height:0; overflow:hidden; background:#18191b; }
        #time-scroll { position:absolute; inset:0; overflow:auto; }
        #time-scroll.panning { cursor:grabbing; }
        #time-scroll.panning * { cursor:grabbing !important; user-select:none !important; }
        #timeline-content { position:relative; min-width:100%; min-height:100%; }
        #ruler { position:sticky; top:0; height:31px; z-index:5; border-bottom:1px solid #484c51; background:#2d3034; cursor:ew-resize; }
        #rows { position:relative; }
        .object-row { height:28px; border-bottom:1px solid #44474c; background:#25272b; }
        .lane-row { position:relative; height:32px; border-bottom:1px solid #35383c; background-image:linear-gradient(to right,rgba(255,255,255,.045) 1px,transparent 1px); }
        .lane-row:hover { background-color:#202328; }
        .tick { position:absolute; top:0; height:100%; border-left:1px solid #555a60; color:#adb1b7; padding:4px 0 0 4px; font-size:10px; pointer-events:none; }
        .tick.minor { border-left-color:#3a3d41; color:transparent; }
        #playhead { position:absolute; top:0; bottom:0; width:1px; background:#ff5d58; z-index:8; pointer-events:none; }
        #playhead::before { content:""; position:absolute; top:0; left:-5px; border-left:6px solid transparent; border-right:6px solid transparent; border-top:8px solid #ff5d58; }
        .key { position:absolute; top:11px; width:10px; height:10px; transform:translate(-5px,-1px) rotate(45deg); border:1px solid #f7e98c; background:#c3ad20; cursor:ew-resize; z-index:3; }
        .key.selected { background:#fff; box-shadow:0 0 3px #fff; }
        .clip { position:absolute; top:4px; height:24px; min-width:10px; display:flex; align-items:center; border:1px solid rgba(255,255,255,.25); border-radius:2px; overflow:hidden; color:#eaf8ff; cursor:move; user-select:none; }
        .clip.spine { background:#176a86; }
        .clip.particle2d,.clip.particle3d { background:#796018; color:#ffe39a; }
        .clip.animation { background:#603b88; color:#e6ccff; }
        .clip.selected { outline:2px solid #eee; z-index:4; }
        .clip-label { min-width:0; flex:1; padding:0 4px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; pointer-events:none; }
        .trim { width:5px; height:100%; flex:0 0 5px; cursor:ew-resize; background:rgba(255,255,255,.1); }
        .trim:hover { background:rgba(255,255,255,.45); }
        #drop-empty { position:absolute; inset:31px 0 0 0; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:5px; pointer-events:none; color:#858a90; }
        #drop-empty strong { color:#c0c3c7; font-size:14px; }
        #pending-binding { display:flex; align-items:center; gap:8px; margin-top:8px; padding:7px 9px; border:1px solid #444950; border-radius:3px; background:#24272b; pointer-events:auto; }
        #pending-selection { max-width:250px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#b8bdc3; }
        #bind-pending { color:#d9f1ff; border-color:#257eaf; background:#205d80; }
        #bind-pending:hover { background:#28759e; }
        .drop-icon { width:34px; height:34px; display:flex; align-items:center; justify-content:center; border:1px dashed #666b72; border-radius:4px; font-size:22px; }
        #drop-overlay { display:none; position:absolute; inset:5px; z-index:20; align-items:center; justify-content:center; border:2px dashed #52b8f5; border-radius:4px; background:rgba(19,83,123,.78); color:white; font-size:16px; font-weight:600; pointer-events:none; }
        #time-panel.drop-active #drop-overlay { display:flex; }
        #inspector { min-width:0; display:flex; flex-direction:column; border-left:1px solid #45494e; background:#25272a; }
        #inspector-empty,#track-inspector,#item-inspector { padding:10px; color:#969aa0; }
        #track-inspector .object-title { color:#e2e4e7; font-size:14px; margin-bottom:8px; overflow-wrap:anywhere; }
        #track-inspector .component-list { display:flex; flex-wrap:wrap; gap:4px; }
        .component-chip { padding:2px 5px; border-radius:8px; background:#3b4046; color:#c8ccd1; font-size:10px; }
        .field-row { display:grid; grid-template-columns:68px minmax(0,1fr); align-items:center; gap:5px; margin-bottom:7px; }
        .field-row input,.field-row select { width:100%; min-width:0; }
        .field-row input[type=checkbox] { width:auto; justify-self:start; }
        button.wide { width:100%; margin-top:4px; }
        button.danger { color:#ff8881; }
        .help { margin-top:auto; display:flex; flex-direction:column; gap:3px; padding:8px; border-top:1px solid #3e4247; color:#858a91; font-size:10px; }
        .help b { color:#b8bcc1; margin-bottom:2px; }
        #context-menu { position:fixed; z-index:100; min-width:190px; max-height:260px; overflow:auto; padding:4px 0; border:1px solid #555a60; border-radius:3px; background:#2b2e32; box-shadow:0 4px 16px rgba(0,0,0,.5); }
        #context-menu button { display:block; width:100%; height:25px; padding:2px 10px; border:0; border-radius:0; background:transparent; text-align:left; }
        #context-menu button:hover { background:#17679a; }
        @media (max-width:900px) { #workspace { grid-template-columns:210px minmax(340px,1fr); } #inspector { display:none; } .toolbar label:nth-of-type(n+3){display:none;} }
    `,
    $: {
        newProject: '#new-project', save: '#save', load: '#load',
        toStart: '#to-start', previousFrame: '#previous-frame',
        play: '#play', nextFrame: '#next-frame', stop: '#stop', record: '#record',
        magnet: '#magnet', ripple: '#ripple', zoomFit: '#zoom-fit',
        time: '#time', projectName: '#project-name', duration: '#duration',
        autoDuration: '#auto-duration', fps: '#fps',
        loop: '#loop', status: '#status', dragMonitor: '#drag-monitor', addSelected: '#add-selected',
        workspace: '#workspace', trackPanel: '#track-panel',
        labelsScroll: '#labels-scroll', labels: '#labels', timePanel: '#time-panel',
        timeScroll: '#time-scroll', timelineContent: '#timeline-content', ruler: '#ruler',
        rows: '#rows', playhead: '#playhead', dropEmpty: '#drop-empty',
        pendingSelection: '#pending-selection', bindPending: '#bind-pending',
        inspectorEmpty: '#inspector-empty', trackInspector: '#track-inspector',
        itemInspector: '#item-inspector', itemStartLabel: '#item-start-label',
        itemStart: '#item-start', durationRow: '#duration-row',
        itemDuration: '#item-duration', animationRow: '#animation-row',
        itemAnimation: '#item-animation', loopRow: '#loop-row',
        itemLoop: '#item-loop', deleteItem: '#delete-item', contextMenu: '#context-menu'
    },
    methods: {
        setStatus(text, kind = '') {
            this.$.status.textContent = text;
            this.$.status.title = text;
            this.$.status.className = kind;
        },
        setDragMonitor(text, kind = '') {
            this.$.dragMonitor.textContent = `v0.13.0｜${text}`;
            this.$.dragMonitor.className = kind;
        },
        deleteSelection() {
            this.deleteSelectedItem();
        },
        snap(time, clampToDuration = true) {
            const frame = 1 / Math.max(1, this.project.fps);
            const snapped = round(Math.round(number(time) / frame) * frame, 4);
            return clamp(snapped, 0, clampToDuration ? this.project.duration : Number.POSITIVE_INFINITY);
        },
        magnetize(track, item, proposedValue, mode) {
            const allowBeyondDuration = mode === 'trim-right' || !!this.project.autoDuration;
            let value = this.snap(proposedValue, !allowBeyondDuration);
            if (!this.magnetEnabled) return value;
            const candidates = [0, this.currentTime, this.project.duration];
            if (mode === 'key') {
                for (const key of track.transformKeys || []) {
                    if (key.id !== item.id) candidates.push(key.time);
                }
            } else {
                for (const clip of track.clips || []) {
                    if (clip.id === item.id || clip.type !== item.type) continue;
                    candidates.push(clip.start, clip.start + clip.duration);
                }
            }
            const probes = mode === 'clip'
                ? [{ value, offset: 0 }, { value: value + item.duration, offset: -item.duration }]
                : [{ value, offset: 0 }];
            let best = null;
            for (const probe of probes) {
                for (const candidate of candidates) {
                    const distance = Math.abs(probe.value - candidate);
                    if (!best || distance < best.distance) {
                        best = { distance, value: candidate + probe.offset };
                    }
                }
            }
            const threshold = 10 / this.pixelsPerSecond();
            return best && best.distance <= threshold
                ? clamp(round(best.value, 4), 0, allowBeyondDuration ? Number.POSITIVE_INFINITY : this.project.duration)
                : value;
        },
        rippleTrack(track, anchor) {
            if (!this.rippleEnabled || !anchor || anchor.start === undefined) return;
            const sameLane = (track.clips || [])
                .filter((clip) => clip.id !== anchor.id && clip.type === anchor.type);
            const priorEnd = sameLane
                .filter((clip) => clip.start < anchor.start)
                .reduce((maximum, clip) => Math.max(maximum, clip.start + clip.duration), 0);
            if (priorEnd > anchor.start) anchor.start = round(priorEnd, 4);

            let cursor = anchor.start + anchor.duration;
            const following = sameLane
                .filter((clip) => clip.start >= anchor.start)
                .sort((a, b) => a.start - b.start);
            for (const clip of following) {
                if (clip.start >= cursor - 0.0001) break;
                clip.start = round(cursor, 4);
                cursor = clip.start + clip.duration;
            }
            const maximumEnd = (track.clips || [])
                .reduce((maximum, clip) => Math.max(maximum, clip.start + clip.duration), 0);
            if (maximumEnd > this.project.duration) {
                this.project.duration = Math.ceil(maximumEnd * this.project.fps) / this.project.fps;
                this.syncControls();
            }
        },
        animationColor(track, clip) {
            if (!['spine', 'animation'].includes(clip.type)) return '';
            const options = clip.type === 'spine'
                ? track.capabilities.spineAnimations
                : track.capabilities.animationClips;
            const palette = [
                '#176a86', '#874d72', '#85691b', '#39764f',
                '#874b35', '#505d98', '#923f55', '#33767c',
                '#704c96', '#82702f', '#3f708e', '#746043'
            ];
            const index = Math.max(0, (options || []).findIndex((item) => item.name === clip.animation));
            return palette[index % palette.length];
        },
        pixelsPerSecond() {
            const viewport = Math.max(360, this.$.timePanel.clientWidth || 700);
            return viewport / Math.max(0.1, this.project.duration) * this.zoom;
        },
        timelineWidth() {
            return Math.max(this.$.timePanel.clientWidth || 500, this.project.duration * this.pixelsPerSecond());
        },
        rulerUnit() {
            const target = 105 / this.pixelsPerSecond();
            const exponent = 10 ** Math.floor(Math.log10(Math.max(0.0001, target)));
            const normalized = target / exponent;
            const factor = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
            const major = factor * exponent;
            return {
                major,
                minor: major / (factor === 5 ? 5 : 2)
            };
        },
        formatRulerTime(time, majorStep) {
            const digits = majorStep >= 1 ? 1 : majorStep >= 0.1 ? 2 : 3;
            return `${round(time, digits)}s`;
        },
        updateZoomLabel() {
            this.$.zoomFit.textContent = this.zoom === 1 ? 'Fit 100%' : `${Math.round(this.zoom * 100)}%`;
            this.$.zoomFit.classList.toggle('active', Math.abs(this.zoom - 1) > 0.0001);
        },
        resetZoom() {
            this.zoom = 1;
            this.render();
            this.$.timeScroll.scrollLeft = 0;
            this.updateZoomLabel();
            this.setStatus('時間軸已顯示完整長度');
        },
        zoomAtPointer(event) {
            event.preventDefault();
            const rect = this.$.timeScroll.getBoundingClientRect();
            const localX = event.clientX - rect.left;
            const oldPixelsPerSecond = this.pixelsPerSecond();
            const timeUnderPointer = (this.$.timeScroll.scrollLeft + localX) / oldPixelsPerSecond;
            const deltaScale = event.deltaMode === 1 ? 40 : event.deltaMode === 2 ? 300 : 1;
            const multiplier = Math.exp(-number(event.deltaY) * deltaScale * 0.0015);
            const nextZoom = clamp(
                this.zoom * multiplier,
                MIN_TIMELINE_ZOOM,
                MAX_TIMELINE_ZOOM
            );
            if (Math.abs(nextZoom - this.zoom) < 0.0001) return;
            this.zoom = nextZoom;
            this.render();
            const newPixelsPerSecond = this.pixelsPerSecond();
            this.$.timeScroll.scrollLeft = Math.max(0, timeUnderPointer * newPixelsPerSecond - localX);
            this.updateZoomLabel();
        },
        beginTimelinePan(event) {
            if (event.button !== 1) return;
            event.preventDefault();
            event.stopPropagation();
            const startX = event.clientX;
            const startY = event.clientY;
            const startLeft = this.$.timeScroll.scrollLeft;
            const startTop = this.$.timeScroll.scrollTop;
            this.$.timeScroll.classList.add('panning');
            const move = (pointerEvent) => {
                this.$.timeScroll.scrollLeft = startLeft - (pointerEvent.clientX - startX);
                this.$.timeScroll.scrollTop = startTop - (pointerEvent.clientY - startY);
                this.syncVerticalScroll();
            };
            const up = () => {
                this.$.timeScroll.classList.remove('panning');
                document.removeEventListener('pointermove', move);
                document.removeEventListener('pointerup', up);
            };
            document.addEventListener('pointermove', move);
            document.addEventListener('pointerup', up);
        },
        findTrack(trackId) {
            return this.project.tracks.find((track) => track.id === trackId);
        },
        findSelection() {
            if (!this.selection) return null;
            const track = this.findTrack(this.selection.trackId);
            if (!track) return null;
            if (this.selection.kind === 'track') return { track, item: null };
            if (this.selection.kind === 'key') {
                return { track, item: track.transformKeys.find((key) => key.id === this.selection.itemId) };
            }
            return { track, item: track.clips.find((clip) => clip.id === this.selection.itemId) };
        },
        escape(value) {
            const div = document.createElement('div');
            div.textContent = String(value || '');
            return div.innerHTML;
        },
        syncControls() {
            this.$.projectName.value = this.project.name;
            this.$.duration.value = this.project.duration;
            this.$.autoDuration.checked = this.project.autoDuration !== false;
            this.$.duration.disabled = this.project.autoDuration !== false;
            this.$.fps.value = this.project.fps;
            this.$.loop.checked = !!this.project.loop;
            this.$.time.step = String(1 / this.project.fps);
            this.$.time.value = round(this.currentTime);
        },
        normalizeProject() {
            this.project.name = this.$.projectName.value.trim() || 'MainTimeline';
            this.project.fps = clamp(Math.round(number(this.$.fps.value, 30)), 1, 120);
            this.project.autoDuration = this.$.autoDuration.checked;
            if (this.project.autoDuration) {
                this.updateAutoDuration();
            } else {
                this.project.duration = Math.max(0.1, number(this.$.duration.value, 5));
            }
            this.project.loop = this.$.loop.checked;
            this.currentTime = clamp(this.currentTime, 0, this.project.duration);
        },
        updateAutoDuration() {
            if (!this.project.autoDuration) return;
            let maximum = 0;
            let hasContent = false;
            for (const track of this.project.tracks || []) {
                for (const key of track.transformKeys || []) {
                    maximum = Math.max(maximum, number(key.time));
                    hasContent = true;
                }
                for (const clip of track.clips || []) {
                    maximum = Math.max(maximum, number(clip.start) + number(clip.duration));
                    hasContent = true;
                }
            }
            if (!hasContent) return;
            const fps = Math.max(1, number(this.project.fps, 30));
            this.project.duration = Math.max(0.1, Math.ceil(maximum * fps - 0.000001) / fps);
            this.currentTime = clamp(this.currentTime, 0, this.project.duration);
            if (this.$.duration) this.$.duration.value = round(this.project.duration, 4);
        },
        render() {
            this.updateAutoDuration();
            const pps = this.pixelsPerSecond();
            const width = this.timelineWidth();
            const rulerUnit = this.rulerUnit();
            const tickStep = rulerUnit.major;
            const minorStep = rulerUnit.minor;
            const visibleDuration = Math.max(this.project.duration, width / pps);
            this.$.timelineContent.style.width = `${width}px`;
            this.$.ruler.innerHTML = '';
            for (let time = 0; time <= visibleDuration + 0.001; time += minorStep) {
                const tick = document.createElement('span');
                const major = Math.abs(time / tickStep - Math.round(time / tickStep)) < 0.001;
                tick.className = `tick${major ? '' : ' minor'}`;
                tick.style.left = `${time * pps}px`;
                tick.textContent = major ? this.formatRulerTime(time, tickStep) : '';
                this.$.ruler.appendChild(tick);
            }
            this.$.labels.innerHTML = '';
            this.$.rows.innerHTML = '';
            for (const track of this.project.tracks) this.renderTrack(track, width, minorStep * pps);
            this.$.dropEmpty.style.display = this.project.tracks.length ? 'none' : 'flex';
            this.$.playhead.style.left = `${this.currentTime * pps}px`;
            this.$.time.value = round(this.currentTime);
            this.renderInspector();
            this.syncVerticalScroll();
        },
        renderTrack(track, width, gridSize) {
            const objectLabel = document.createElement('div');
            objectLabel.className = `object-label${this.selection && this.selection.kind === 'track' && this.selection.trackId === track.id ? ' selected' : ''}`;
            objectLabel.innerHTML = `
                <span class="fold">${track.collapsed ? '▶' : '▼'}</span>
                <span class="object-icon">◈</span>
                <span class="object-name" title="${this.escape(track.nodeName)}">${this.escape(track.nodeName)}</span>
                <button class="object-remove" title="移除物件軌道">×</button>`;
            objectLabel.addEventListener('click', (event) => {
                if (event.target.closest('.object-remove')) return;
                if (event.target.closest('.fold')) {
                    track.collapsed = !track.collapsed;
                    this.render();
                    return;
                }
                this.selection = { trackId: track.id, kind: 'track' };
                this.render();
            });
            objectLabel.querySelector('.object-remove').addEventListener('click', () => this.removeTrack(track.id));
            this.$.labels.appendChild(objectLabel);
            const objectRow = document.createElement('div');
            objectRow.className = 'object-row';
            objectRow.style.width = `${width}px`;
            objectRow.addEventListener('click', (event) => this.seekFromEvent(event));
            this.$.rows.appendChild(objectRow);
            if (track.collapsed) return;

            for (const lane of lanesForTrack(track)) {
                const laneLabel = document.createElement('div');
                laneLabel.className = 'lane-label';
                laneLabel.innerHTML = `
                    <span class="lane-icon ${lane.type}">${lane.icon}</span>
                    <span class="lane-title">${lane.title}</span>
                    <button class="add-item" title="在播放頭新增">＋</button>`;
                laneLabel.querySelector('.add-item').addEventListener('click', (event) => {
                    if (lane.type === 'transform') void this.captureSingleTrack(track);
                    else this.showAddMenu(track, lane.type, event.clientX, event.clientY);
                });
                this.$.labels.appendChild(laneLabel);

                const row = document.createElement('div');
                row.className = `lane-row ${lane.type}`;
                row.dataset.trackId = track.id;
                row.dataset.lane = lane.type;
                row.style.width = `${width}px`;
                row.style.backgroundSize = `${gridSize}px 100%`;
                row.addEventListener('dblclick', (event) => {
                    this.seekFromEvent(event);
                    if (lane.type === 'transform') void this.captureSingleTrack(track);
                    else this.showAddMenu(track, lane.type, event.clientX, event.clientY);
                });
                row.addEventListener('contextmenu', (event) => {
                    event.preventDefault();
                    this.seekFromEvent(event);
                    this.showAddMenu(track, lane.type, event.clientX, event.clientY);
                });
                row.addEventListener('click', (event) => {
                    if (!event.target.closest('.clip,.key')) this.seekFromEvent(event);
                });

                if (lane.type === 'transform') {
                    for (const key of track.transformKeys || []) row.appendChild(this.createKeyElement(track, key));
                } else {
                    for (const clip of (track.clips || []).filter((item) => item.type === lane.type)) {
                        row.appendChild(this.createClipElement(track, clip));
                    }
                }
                this.$.rows.appendChild(row);
            }
        },
        createKeyElement(track, key) {
            const element = document.createElement('span');
            const selected = this.selection && this.selection.kind === 'key'
                && this.selection.trackId === track.id && this.selection.itemId === key.id;
            element.className = `key${selected ? ' selected' : ''}`;
            element.style.left = `${key.time * this.pixelsPerSecond()}px`;
            element.title = `Transform @ ${round(key.time)}s`;
            element.addEventListener('pointerdown', (event) => {
                if (event.button !== 0) return;
                event.stopPropagation();
                this.selection = { trackId: track.id, kind: 'key', itemId: key.id };
                this.beginItemDrag(event, track, key, 'key');
            });
            element.addEventListener('click', (event) => event.stopPropagation());
            return element;
        },
        createClipElement(track, clip) {
            const element = document.createElement('span');
            const selected = this.selection && this.selection.kind === 'clip'
                && this.selection.trackId === track.id && this.selection.itemId === clip.id;
            element.className = `clip ${clip.type}${selected ? ' selected' : ''}`;
            element.style.left = `${clip.start * this.pixelsPerSecond()}px`;
            element.style.width = `${Math.max(10, clip.duration * this.pixelsPerSecond())}px`;
            const animationColor = this.animationColor(track, clip);
            if (animationColor) element.style.background = animationColor;
            const label = clip.type === 'spine' || clip.type === 'animation'
                ? clip.animation || 'Animation'
                : clip.type === 'particle2d' ? 'Particle 2D' : 'Particle 3D';
            element.innerHTML = `<span class="trim left"></span><span class="clip-label">${this.escape(label)}</span><span class="trim right"></span>`;
            element.addEventListener('pointerdown', (event) => {
                if (event.button !== 0) return;
                event.stopPropagation();
                this.selection = { trackId: track.id, kind: 'clip', itemId: clip.id };
                const target = event.target;
                const mode = target.classList.contains('left')
                    ? 'trim-left'
                    : target.classList.contains('right') ? 'trim-right' : 'clip';
                this.beginItemDrag(event, track, clip, mode);
            });
            element.addEventListener('click', (event) => event.stopPropagation());
            return element;
        },
        beginItemDrag(event, track, item, mode) {
            event.preventDefault();
            const startX = event.clientX;
            const originalStart = item.start !== undefined ? item.start : item.time;
            const originalDuration = item.duration || 0;
            const move = (pointerEvent) => {
                const delta = (pointerEvent.clientX - startX) / this.pixelsPerSecond();
                if (mode === 'key') {
                    item.time = this.magnetize(track, item, originalStart + delta, 'key');
                } else if (mode === 'clip') {
                    item.start = this.magnetize(track, item, originalStart + delta, 'clip');
                    if (!this.project.autoDuration) {
                        item.start = Math.min(item.start, Math.max(0, this.project.duration - item.duration));
                    }
                } else if (mode === 'trim-right') {
                    const proposedEnd = originalStart + originalDuration + delta;
                    const end = this.magnetize(track, item, proposedEnd, 'trim-right');
                    item.duration = Math.max(1 / this.project.fps, end - item.start);
                } else {
                    const end = originalStart + originalDuration;
                    item.start = clamp(
                        this.magnetize(track, item, originalStart + delta, 'trim-left'),
                        0,
                        end - 1 / this.project.fps
                    );
                    item.duration = end - item.start;
                }
                if (mode !== 'key') this.rippleTrack(track, item);
                this.render();
                this.queuePreview();
            };
            const up = () => {
                document.removeEventListener('pointermove', move);
                document.removeEventListener('pointerup', up);
                this.render();
            };
            document.addEventListener('pointermove', move);
            document.addEventListener('pointerup', up);
            this.renderInspector();
        },
        showAddMenu(track, laneType, x, y) {
            this.hideContextMenu();
            if (laneType === 'transform') {
                void this.captureSingleTrack(track);
                return;
            }
            const options = laneType === 'spine'
                ? track.capabilities.spineAnimations
                : laneType === 'animation' ? track.capabilities.animationClips : [];
            const menu = this.$.contextMenu;
            const actions = [];
            if (laneType === 'particle2d' || laneType === 'particle3d') {
                actions.push({
                    label: laneType === 'particle2d' ? 'Add Particle 2D Clip' : 'Add Particle 3D Clip',
                    run: () => this.addClip(track, laneType)
                });
            } else if (options && options.length) {
                for (const option of options) {
                    actions.push({
                        label: `${option.name}${option.duration ? `  (${round(option.duration, 2)}s)` : ''}`,
                        run: () => this.addClip(track, laneType, option)
                    });
                }
            } else {
                actions.push({ label: '沒有可用的動畫', disabled: true });
            }
            for (const action of actions) {
                const button = document.createElement('button');
                button.textContent = action.label;
                button.disabled = !!action.disabled;
                button.addEventListener('pointerdown', (event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    this.hideContextMenu();
                    if (action.run) action.run();
                });
                menu.appendChild(button);
            }
            menu.style.left = `${clamp(x, 2, window.innerWidth - 210)}px`;
            menu.style.top = `${clamp(y, 2, window.innerHeight - 270)}px`;
            menu.hidden = false;
        },
        hideContextMenu() {
            this.$.contextMenu.hidden = true;
            this.$.contextMenu.innerHTML = '';
        },
        addClip(track, type, option = null) {
            const available = Math.max(1 / this.project.fps, this.project.duration - this.currentTime);
            const duration = option && option.duration ? option.duration : 1;
            const clip = {
                id: uid('clip'),
                type,
                start: this.snap(this.currentTime),
                duration: round(this.project.autoDuration ? duration : Math.min(duration, available), 4),
                animation: option ? option.name : '',
                loop: false
            };
            track.clips.push(clip);
            this.rippleTrack(track, clip);
            this.selection = { trackId: track.id, kind: 'clip', itemId: clip.id };
            this.render();
            this.queuePreview();
        },
        renderInspector() {
            const selected = this.findSelection();
            this.$.inspectorEmpty.hidden = !!selected;
            this.$.trackInspector.hidden = !selected || this.selection.kind !== 'track';
            this.$.itemInspector.hidden = !selected || this.selection.kind === 'track';
            if (!selected) return;
            if (this.selection.kind === 'track') {
                const chips = lanesForTrack(selected.track)
                    .map((lane) => `<span class="component-chip">${this.escape(lane.title)}</span>`).join('');
                this.$.trackInspector.innerHTML = `
                    <div class="object-title">${this.escape(selected.track.nodeName)}</div>
                    <div class="component-list">${chips}</div>`;
                return;
            }
            const isKey = this.selection.kind === 'key';
            const item = selected.item;
            if (!item) return;
            this.$.itemStartLabel.textContent = isKey ? 'Time' : 'Start';
            this.$.itemStart.value = isKey ? item.time : item.start;
            this.$.durationRow.hidden = isKey;
            this.$.itemDuration.value = isKey ? 0 : item.duration;
            const hasAnimation = !isKey && ['spine', 'animation'].includes(item.type);
            this.$.animationRow.hidden = !hasAnimation;
            this.$.loopRow.hidden = !hasAnimation;
            if (hasAnimation) {
                const options = item.type === 'spine'
                    ? selected.track.capabilities.spineAnimations
                    : selected.track.capabilities.animationClips;
                this.$.itemAnimation.innerHTML = '';
                for (const option of options || []) {
                    const element = document.createElement('option');
                    element.value = option.name;
                    element.textContent = option.name;
                    this.$.itemAnimation.appendChild(element);
                }
                this.$.itemAnimation.value = item.animation || '';
                this.$.itemLoop.checked = !!item.loop;
            }
        },
        seekFromEvent(event) {
            const rect = this.$.timelineContent.getBoundingClientRect();
            this.seek((event.clientX - rect.left) / this.pixelsPerSecond());
        },
        seek(time) {
            this.currentTime = this.snap(time);
            this.$.playhead.style.left = `${this.currentTime * this.pixelsPerSecond()}px`;
            this.$.time.value = round(this.currentTime);
            this.queuePreview();
        },
        evaluate() {
            return {
                time: this.currentTime,
                playing: this.playing,
                states: this.project.tracks.map((track) => ({
                    nodeUuid: track.nodeUuid,
                    ownedTypes: [...new Set((track.clips || []).map((clip) => clip.type))],
                    transform: interpolateKeys(track.transformKeys, this.currentTime, track.initialTransform),
                    clips: (track.clips || []).filter((clip) => (
                        this.currentTime >= clip.start && this.currentTime < clip.start + clip.duration
                    )).map((clip) => ({ ...clip, localTime: Math.max(0, this.currentTime - clip.start) }))
                }))
            };
        },
        queuePreview() {
            this.pendingPreview = this.evaluate();
            void this.flushPreview();
        },
        async flushPreview() {
            if (this.previewBusy || !this.pendingPreview) return;
            this.previewBusy = true;
            try {
                while (this.pendingPreview) {
                    const payload = this.pendingPreview;
                    this.pendingPreview = null;
                    await Editor.Message.request(packageJSON.name, 'timeline-preview', payload);
                }
            } catch (error) {
                this.pendingPreview = null;
                this.setStatus(`Scene 預覽失敗：${error.message || error}`, 'error');
            } finally {
                this.previewBusy = false;
            }
        },
        extractDragPayload(dataTransfer) {
            if (!dataTransfer) return [];
            const values = [];
            for (const type of Array.from(dataTransfer.types || [])) {
                try {
                    const value = dataTransfer.getData(type);
                    if (value) values.push(value);
                } catch (_) {}
            }
            return values;
        },
        getCocosDragInfo() {
            try {
                const dragInfo = Editor.UI && Editor.UI.DragArea && Editor.UI.DragArea.currentDragInfo;
                return dragInfo ? JSON.parse(JSON.stringify(dragInfo)) : null;
            } catch (_) {
                return null;
            }
        },
        extractDropPayload(event, capturedDragInfo = null) {
            const values = this.extractDragPayload(event && event.dataTransfer);
            const dragInfo = capturedDragInfo || this.getCocosDragInfo();
            if (dragInfo) values.push(dragInfo);
            if (event && event.detail) values.push(event.detail);
            return values;
        },
        cocosNodeDragInfo() {
            const dragInfo = this.getCocosDragInfo();
            if (!dragInfo) return null;
            const types = [
                dragInfo.type,
                ...(Array.isArray(dragInfo.types) ? dragInfo.types : []),
                ...((dragInfo.additional || []).map((item) => item && item.type))
            ].filter(Boolean);
            return types.includes('cc.Node') ? dragInfo : null;
        },
        acceptCocosNodeDrag(source = 'drag') {
            const dragInfo = this.cocosNodeDragInfo();
            if (!dragInfo) return false;
            let signature = '';
            try {
                signature = JSON.stringify(dragInfo);
            } catch (_) {
                signature = String(dragInfo.value || 'cc.Node');
            }
            this.$.timePanel.classList.add('drop-active');
            this.setDragMonitor('已偵測 cc.Node', 'active');
            this.setStatus('已接收 Hierarchy 拖曳，正在建立軌道…');
            if (signature && signature !== this.acceptedDragSignature) {
                this.acceptedDragSignature = signature;
                this.lastDropTypes = ['cc.Node', source];
                void this.addDroppedNodes([dragInfo]).then(() => {
                    this.setDragMonitor('節點已接收', 'success');
                });
            }
            return true;
        },
        onExternalSelection(type, value) {
            if (type !== 'node') return;
            this.$.pendingSelection.textContent = 'Hierarchy 已選取節點，正在讀取…';
            this.$.addSelected.disabled = false;
            this.$.bindPending.disabled = false;
            void this.refreshPendingSelection();
        },
        async refreshPendingSelection() {
            if (this.selectionPolling) return;
            this.selectionPolling = true;
            try {
                const nodes = await Editor.Message.request(packageJSON.name, 'timeline-peek-selection');
                this.pendingSelectionNodes = Array.isArray(nodes) ? nodes : [];
                const names = this.pendingSelectionNodes.map((node) => node.nodeName).filter(Boolean);
                this.$.pendingSelection.textContent = names.length
                    ? `目前選取：${names.join('、')}`
                    : '目前未選取 Scene 節點';
                this.$.pendingSelection.title = names.join('、');
                this.$.bindPending.disabled = !this.pendingSelectionNodes.length;
                this.$.addSelected.disabled = !this.pendingSelectionNodes.length;
            } catch (_) {
                this.pendingSelectionNodes = [];
                this.$.pendingSelection.textContent = '目前未選取 Scene 節點';
                this.$.bindPending.disabled = true;
                this.$.addSelected.disabled = true;
            } finally {
                this.selectionPolling = false;
            }
        },
        async addCurrentSelection() {
            await this.refreshPendingSelection();
            const nodes = this.pendingSelectionNodes || [];
            if (!nodes.length) {
                this.setStatus('請先在 Hierarchy 點選一個 Scene 節點', 'error');
                return;
            }
            const added = this.mergeNodeDescriptions(nodes);
            this.setStatus(added ? `已建立 ${added} 個物件軌道` : '物件已存在 Timeline', 'success');
        },
        mergeNodeDescriptions(nodes) {
            let added = 0;
            const shouldSuggestName = this.project.name === 'MainTimeline'
                && this.project.tracks.length === 0;
            for (const node of nodes || []) {
                if (!node || !node.nodeUuid) continue;
                if (this.project.tracks.some((track) => track.nodeUuid === node.nodeUuid)) continue;
                this.project.tracks.push({
                    id: uid('track'),
                    nodeUuid: node.nodeUuid,
                    nodeName: node.nodeName,
                    nodePath: node.nodePath || '',
                    initialTransform: node.transform,
                    capabilities: node.capabilities,
                    transformKeys: [],
                    clips: [],
                    collapsed: false
                });
                added += 1;
                if (shouldSuggestName && added === 1) {
                    const parts = String(node.nodePath || '').split('/').filter(Boolean);
                    const parent = parts.length > 1 ? parts[parts.length - 2] : '';
                    const genericParents = new Set(['Canvas', 'Scene', 'scene-2d', 'scene-3d']);
                    this.project.name = parent && !genericParents.has(parent)
                        ? parent
                        : (node.nodeName || 'MainTimeline');
                    this.syncControls();
                }
            }
            this.render();
            return added;
        },
        prepareDropSnapshot() {
            if (this.dropSnapshotPromise) return;
            this.dropSnapshotPromise = Editor.Message.request(packageJSON.name, 'timeline-add-selected')
                .then((nodes) => Array.isArray(nodes) ? nodes : [])
                .catch(() => []);
        },
        async addDroppedNodes(payload = []) {
            const typeText = this.lastDropTypes && this.lastDropTypes.length
                ? `；格式：${this.lastDropTypes.join(', ')}`
                : '；使用 Hierarchy 選取備援';
            this.setStatus(`正在建立物件與元件軌道${typeText}`);
            try {
                const snapshot = this.dropSnapshotPromise ? await this.dropSnapshotPromise : [];
                let nodes = [];
                try {
                    nodes = await Editor.Message.request(packageJSON.name, 'timeline-add-dropped', payload);
                } catch (error) {
                    if (!snapshot.length) throw error;
                }
                const byUuid = new Map();
                for (const node of [...snapshot, ...(nodes || [])]) {
                    if (node && node.nodeUuid) byUuid.set(node.nodeUuid, node);
                }
                const added = this.mergeNodeDescriptions([...byUuid.values()]);
                if (!byUuid.size) throw new Error('拖放事件已收到，但未取得 Hierarchy 節點 UUID。請先點選節點再拖入。');
                this.setStatus(added ? `已建立 ${added} 個物件軌道` : '物件已存在 Timeline', 'success');
            } catch (error) {
                this.setStatus(`建立軌道失敗：${error.message || error}`, 'error');
            } finally {
                this.dropSnapshotPromise = null;
                this.lastDropTypes = [];
            }
        },
        removeTrack(trackId) {
            this.project.tracks = this.project.tracks.filter((track) => track.id !== trackId);
            if (this.selection && this.selection.trackId === trackId) this.selection = null;
            this.render();
            this.queuePreview();
        },
        async captureSingleTrack(track, transformOverride = null) {
            try {
                let transform = transformOverride;
                if (!transform) {
                    const nodes = await Editor.Message.request(packageJSON.name, 'timeline-inspect-nodes', [track.nodeUuid]);
                    if (!nodes || !nodes[0]) throw new Error('Scene 中找不到該節點');
                    transform = nodes[0].transform;
                }
                const existing = track.transformKeys.find((key) => Math.abs(key.time - this.currentTime) < 0.0005);
                const key = { id: existing ? existing.id : uid('key'), time: this.snap(this.currentTime), ...transform };
                if (existing) Object.assign(existing, key);
                else track.transformKeys.push(key);
                this.selection = { trackId: track.id, kind: 'key', itemId: key.id };
                this.render();
                this.queuePreview();
            } catch (error) {
                this.setStatus(`建立 Key 失敗：${error.message || error}`, 'error');
            }
        },
        async toggleRecording() {
            this.recording = !this.recording;
            this.$.record.classList.toggle('active', this.recording);
            this.setStatus(this.recording ? 'Recording：在 Scene 或 Inspector 移動物件會自動記錄 Transform' : '已停止錄製', this.recording ? 'error' : '');
            if (this.recording) {
                this.recordSnapshot = new Map();
                try {
                    const uuids = this.project.tracks.map((track) => track.nodeUuid);
                    const nodes = await Editor.Message.request(packageJSON.name, 'timeline-inspect-nodes', uuids);
                    for (const node of nodes || []) this.recordSnapshot.set(node.nodeUuid, { ...node.transform });
                } catch (error) {
                    this.recording = false;
                    this.$.record.classList.remove('active');
                    this.setStatus(`無法開始錄製：${error.message || error}`, 'error');
                    return;
                }
                this.scheduleRecordPoll();
            } else if (this.recordTimer) {
                clearTimeout(this.recordTimer);
                this.recordTimer = 0;
            }
        },
        scheduleRecordPoll() {
            if (!this.recording) return;
            this.recordTimer = setTimeout(() => void this.pollRecording(), 250);
        },
        async pollRecording() {
            if (!this.recording || this.recordPolling || !this.project.tracks.length) {
                this.scheduleRecordPoll();
                return;
            }
            this.recordPolling = true;
            try {
                const uuids = this.project.tracks.map((track) => track.nodeUuid);
                const nodes = await Editor.Message.request(packageJSON.name, 'timeline-inspect-nodes', uuids);
                for (const node of nodes || []) {
                    const expected = this.recordSnapshot.get(node.nodeUuid);
                    if (expected && !sameTransform(expected, node.transform)) {
                        const track = this.project.tracks.find((item) => item.nodeUuid === node.nodeUuid);
                        if (track) {
                            await this.captureSingleTrack(track, node.transform);
                            this.recordSnapshot.set(node.nodeUuid, { ...node.transform });
                            this.setStatus(`Recorded：${track.nodeName} @ ${round(this.currentTime)}s`, 'error');
                        }
                    }
                }
            } catch (error) {
                this.setStatus(`錄製失敗：${error.message || error}`, 'error');
            } finally {
                this.recordPolling = false;
                this.scheduleRecordPoll();
            }
        },
        startPlayback() {
            if (this.playing) {
                this.playing = false;
                this.$.play.textContent = '▶';
                this.queuePreview();
                return;
            }
            if (this.currentTime >= this.project.duration) this.currentTime = 0;
            this.playing = true;
            this.playStartClock = performance.now();
            this.playStartTime = this.currentTime;
            this.$.play.textContent = '❚❚';
            this.playFrame();
        },
        playFrame() {
            if (!this.playing) return;
            let next = this.playStartTime + (performance.now() - this.playStartClock) / 1000;
            if (next >= this.project.duration) {
                if (this.project.loop) {
                    next %= this.project.duration;
                    this.playStartClock = performance.now();
                    this.playStartTime = next;
                } else {
                    next = this.project.duration;
                    this.playing = false;
                    this.$.play.textContent = '▶';
                }
            }
            this.currentTime = next;
            this.$.playhead.style.left = `${this.currentTime * this.pixelsPerSecond()}px`;
            this.$.time.value = round(this.currentTime);
            this.queuePreview();
            if (this.playing) this.frameHandle = requestAnimationFrame(() => this.playFrame());
        },
        async stopPlayback() {
            this.playing = false;
            this.$.play.textContent = '▶';
            if (this.frameHandle) cancelAnimationFrame(this.frameHandle);
            try {
                const result = await Editor.Message.request(packageJSON.name, 'timeline-restore');
                this.setStatus(`已停止並還原 ${result.restored || 0} 個 Scene 物件`, 'success');
            } catch (error) {
                this.setStatus(`還原失敗：${error.message || error}`, 'error');
            }
        },
        deleteSelectedItem() {
            const selected = this.findSelection();
            if (!selected || this.selection.kind === 'track') return;
            if (this.selection.kind === 'key') {
                selected.track.transformKeys = selected.track.transformKeys.filter((item) => item.id !== this.selection.itemId);
            } else {
                selected.track.clips = selected.track.clips.filter((item) => item.id !== this.selection.itemId);
            }
            this.selection = null;
            this.render();
            this.queuePreview();
        },
        async saveProject() {
            this.normalizeProject();
            try {
                const result = await Editor.Message.request(packageJSON.name, 'timeline-save', this.project);
                this.setStatus(`已輸出 ${result.timelineName}；使用元件 ${result.className}`, 'success');
            } catch (error) {
                this.setStatus(`儲存失敗：${error.message || error}`, 'error');
            }
        },
        async createNewProject() {
            const hasContent = (this.project.tracks || []).some((track) => (
                (track.transformKeys && track.transformKeys.length)
                || (track.clips && track.clips.length)
            ));
            if (hasContent && !window.confirm('建立新的 Timeline？尚未儲存的修改會遺失。')) return;
            await this.stopPlayback();
            this.project = freshProject();
            this.currentTime = 0;
            this.selection = null;
            this.zoom = 1;
            this.syncControls();
            this.render();
            this.setStatus('已建立空白 Timeline；加入第一個 Prefab 物件後會自動建議名稱', 'success');
        },
        async loadProject() {
            try {
                const result = await Editor.Message.request(packageJSON.name, 'timeline-load-selected');
                this.project = result.project;
                this.project.autoDuration = this.project.autoDuration !== false;
                for (const track of this.project.tracks) track.collapsed = !!track.collapsed;
                this.currentTime = 0;
                this.selection = null;
                this.syncControls();
                this.render();
                this.queuePreview();
                this.setStatus(`Opened：${result.assetUrl}`, 'success');
            } catch (error) {
                this.setStatus(`開啟失敗：${error.message || error}`, 'error');
            }
        },
        syncVerticalScroll() {
            this.$.labels.style.transform = `translateY(${-this.$.timeScroll.scrollTop}px)`;
        }
    },
    ready() {
        this.project = freshProject();
        this.currentTime = 0;
        this.playing = false;
        this.recording = false;
        this.magnetEnabled = true;
        this.rippleEnabled = true;
        this.zoom = 1;
        this.recordPolling = false;
        this.recordTimer = 0;
        this.selection = null;
        this.previewBusy = false;
        this.pendingPreview = null;
        this.frameHandle = 0;
        this.dropSnapshotPromise = null;
        this.lastDropTypes = [];
        this.pendingSelectionNodes = [];
        this.selectionPolling = false;
        this.selectionPollTimer = 0;
        this.dragWatchTimer = 0;
        this.acceptedDragSignature = '';

        this.$.newProject.addEventListener('click', () => void this.createNewProject());
        this.$.save.addEventListener('click', () => void this.saveProject());
        this.$.load.addEventListener('click', () => void this.loadProject());
        this.$.addSelected.addEventListener('click', () => void this.addCurrentSelection());
        this.$.bindPending.addEventListener('click', () => void this.addCurrentSelection());
        this.$.toStart.addEventListener('click', () => this.seek(0));
        this.$.previousFrame.addEventListener('click', () => this.seek(this.currentTime - 1 / this.project.fps));
        this.$.nextFrame.addEventListener('click', () => this.seek(this.currentTime + 1 / this.project.fps));
        this.$.play.addEventListener('click', () => this.startPlayback());
        this.$.stop.addEventListener('click', () => void this.stopPlayback());
        this.$.record.addEventListener('click', () => void this.toggleRecording());
        this.$.magnet.addEventListener('click', () => {
            this.magnetEnabled = !this.magnetEnabled;
            this.$.magnet.classList.toggle('active', this.magnetEnabled);
            this.setStatus(this.magnetEnabled ? '磁吸已開啟' : '磁吸已關閉');
        });
        this.$.ripple.addEventListener('click', () => {
            this.rippleEnabled = !this.rippleEnabled;
            this.$.ripple.classList.toggle('active', this.rippleEnabled);
            this.setStatus(this.rippleEnabled ? '推擠已開啟' : '推擠已關閉');
        });
        this.$.zoomFit.addEventListener('click', () => this.resetZoom());
        this.$.time.addEventListener('change', () => this.seek(this.$.time.value));
        for (const element of [
            this.$.projectName,
            this.$.duration,
            this.$.autoDuration,
            this.$.fps,
            this.$.loop
        ]) {
            element.addEventListener('change', () => {
                this.normalizeProject();
                this.syncControls();
                this.render();
            });
        }
        this.$.ruler.addEventListener('pointerdown', (event) => {
            if (event.button !== 0) return;
            const move = (pointerEvent) => this.seekFromEvent(pointerEvent);
            const up = () => {
                document.removeEventListener('pointermove', move);
                document.removeEventListener('pointerup', up);
            };
            move(event);
            document.addEventListener('pointermove', move);
            document.addEventListener('pointerup', up);
        });
        this.$.timeScroll.addEventListener('wheel', (event) => this.zoomAtPointer(event), { passive: false });
        this.$.timeScroll.addEventListener('pointerdown', (event) => this.beginTimelinePan(event));
        this.$.timeScroll.addEventListener('auxclick', (event) => {
            if (event.button === 1) event.preventDefault();
        });
        this.$.timeScroll.addEventListener('scroll', () => this.syncVerticalScroll());
        this.onTimelineDragEnter = (event) => {
            event.preventDefault();
            if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
            this.$.timePanel.classList.add('drop-active');
            this.prepareDropSnapshot();
            const dragInfo = this.getCocosDragInfo();
            if (dragInfo && dragInfo.type && dragInfo.type !== 'cc.Node') {
                this.setDragMonitor(`收到 ${dragInfo.type}`, 'active');
                this.setStatus('目前拖入的是 Assets 素材；Timeline 需要 Scene 裡的 Hierarchy 節點');
            } else {
                this.setDragMonitor('收到 dragenter', 'active');
                this.acceptCocosNodeDrag('dragenter');
            }
        };
        this.onTimelineDragOver = (event) => {
            event.preventDefault();
            if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
            this.$.timePanel.classList.add('drop-active');
            this.acceptCocosNodeDrag('dragover');
        };
        this.onTimelineDragLeave = (event) => {
            const related = event.relatedTarget;
            if (!related || !this.$.workspace.contains(related)) {
                this.$.timePanel.classList.remove('drop-active');
            }
        };
        this.onTimelineDrop = (event) => {
            const dragInfo = this.getCocosDragInfo();
            const payload = this.extractDropPayload(event, dragInfo);
            event.preventDefault();
            event.stopPropagation();
            this.$.timePanel.classList.remove('drop-active');
            this.lastDropTypes = [
                ...Array.from(event.dataTransfer && event.dataTransfer.types || []),
                ...(dragInfo && dragInfo.type ? [dragInfo.type] : [])
            ];
            if (dragInfo && dragInfo.type && dragInfo.type !== 'cc.Node') {
                this.setDragMonitor(`不接受 ${dragInfo.type}`, 'error');
                this.setStatus('拖入的是 Assets 素材。請先把素材放進 Scene，再從 Hierarchy 拖入該節點。', 'error');
                this.dropSnapshotPromise = null;
                this.lastDropTypes = [];
                return;
            }
            void this.addDroppedNodes(payload);
        };
        this.$.workspace.addEventListener('dragenter', this.onTimelineDragEnter);
        this.$.workspace.addEventListener('dragover', this.onTimelineDragOver);
        this.$.workspace.addEventListener('dragleave', this.onTimelineDragLeave);
        this.$.workspace.addEventListener('drop', this.onTimelineDrop);
        this.$.contextMenu.addEventListener('pointerdown', (event) => event.stopPropagation());
        document.addEventListener('pointerdown', (event) => {
            const path = typeof event.composedPath === 'function' ? event.composedPath() : [];
            if (!path.includes(this.$.contextMenu)) this.hideContextMenu();
        });
        this.$.itemStart.addEventListener('change', () => {
            const selected = this.findSelection();
            if (!selected || !selected.item) return;
            if (this.selection.kind === 'key') {
                selected.item.time = this.magnetize(selected.track, selected.item, this.$.itemStart.value, 'key');
            } else {
                selected.item.start = this.magnetize(selected.track, selected.item, this.$.itemStart.value, 'clip');
                this.rippleTrack(selected.track, selected.item);
            }
            this.render();
            this.queuePreview();
        });
        this.$.itemDuration.addEventListener('change', () => {
            const selected = this.findSelection();
            if (!selected || !selected.item || this.selection.kind === 'key') return;
            selected.item.duration = Math.max(1 / this.project.fps, number(this.$.itemDuration.value, 1));
            this.rippleTrack(selected.track, selected.item);
            this.render();
            this.queuePreview();
        });
        this.$.itemAnimation.addEventListener('change', () => {
            const selected = this.findSelection();
            if (!selected || !selected.item) return;
            selected.item.animation = this.$.itemAnimation.value;
            const options = selected.item.type === 'spine'
                ? selected.track.capabilities.spineAnimations
                : selected.track.capabilities.animationClips;
            const option = (options || []).find((item) => item.name === selected.item.animation);
            if (option && option.duration) selected.item.duration = option.duration;
            this.rippleTrack(selected.track, selected.item);
            this.render();
            this.queuePreview();
        });
        this.$.itemLoop.addEventListener('change', () => {
            const selected = this.findSelection();
            if (selected && selected.item) selected.item.loop = this.$.itemLoop.checked;
            this.queuePreview();
        });
        this.$.deleteItem.addEventListener('click', () => this.deleteSelectedItem());
        this.onPanelKeyDown = (event) => {
            if (event.key !== 'Delete' && event.key !== 'Backspace') return;
            const target = event.target;
            const tagName = target && target.tagName ? target.tagName.toLowerCase() : '';
            if (
                tagName === 'input'
                || tagName === 'textarea'
                || tagName === 'select'
                || (target && target.isContentEditable)
            ) return;
            const selected = this.findSelection();
            if (!selected || !this.selection || this.selection.kind === 'track') return;
            event.preventDefault();
            event.stopPropagation();
            this.deleteSelectedItem();
        };
        document.addEventListener('keydown', this.onPanelKeyDown);
        this.syncControls();
        this.updateZoomLabel();
        this.render();
        void this.refreshPendingSelection();
        this.selectionPollTimer = setInterval(() => void this.refreshPendingSelection(), 750);
        this.dragWatchTimer = setInterval(() => {
            const dragInfo = this.cocosNodeDragInfo();
            if (!dragInfo) {
                this.acceptedDragSignature = '';
                return;
            }
            let overWorkspace = false;
            try {
                overWorkspace = this.$.workspace.matches(':hover') || this.$.workspace.hasAttribute('hoving');
            } catch (_) {}
            if (overWorkspace) this.acceptCocosNodeDrag('hover-watch');
        }, 80);
    },
    close() {
        this.playing = false;
        this.recording = false;
        if (this.frameHandle) cancelAnimationFrame(this.frameHandle);
        if (this.recordTimer) clearTimeout(this.recordTimer);
        if (this.selectionPollTimer) clearInterval(this.selectionPollTimer);
        if (this.dragWatchTimer) clearInterval(this.dragWatchTimer);
        if (this.onPanelKeyDown) document.removeEventListener('keydown', this.onPanelKeyDown);
        if (this.onTimelineDragEnter) {
            this.$.workspace.removeEventListener('dragenter', this.onTimelineDragEnter);
            this.$.workspace.removeEventListener('dragover', this.onTimelineDragOver);
            this.$.workspace.removeEventListener('dragleave', this.onTimelineDragLeave);
            this.$.workspace.removeEventListener('drop', this.onTimelineDrop);
        }
        void Editor.Message.request(packageJSON.name, 'timeline-restore').catch(() => {});
    }
});
