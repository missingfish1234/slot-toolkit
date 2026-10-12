/* Load after the editor's main script. Pure builders are also usable from Node tests. */
(function (global) {
    'use strict';

    const seconds = value => Number(value instanceof Date ? value.valueOf() : new Date(value).valueOf()) / 1000;
    const number = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
    const initialVisible = char => char.baseVisible !== false;
    const animTracks = char => char.animTracks || (char.tracks && char.tracks.anim ? [char.tracks.anim] : []);
    const clipsFor = (items, group) => group ? items.filter(item => item.group === group && Number.isFinite(seconds(item.start))).slice().sort((a, b) => seconds(a.start) - seconds(b.start)) : [];
    const endTime = item => Number.isFinite(seconds(item.end)) ? seconds(item.end) : seconds(item.start);
    const animName = item => String(item.content || '').split(' (')[0];

    function getVisibilitySwitches(char, items) {
        const track = char.tracks && char.tracks.visibility || char.id + '_visibility';
        const atTime = new Map();
        clipsFor(items, track).forEach(item => {
            if (typeof item.visibilityEnabled === 'boolean') {
                // DataSet insertion order resolves switches sharing a timestamp.
                atTime.set(seconds(item.start), { startTime: seconds(item.start), visible: item.visibilityEnabled });
            }
        });
        return Array.from(atTime.values());
    }

    function getVisibilityEvents(char, items) {
        const atTime = new Map([[0, { startTime: 0, visible: initialVisible(char) }]]);
        getVisibilitySwitches(char, items).forEach(item => atTime.set(item.startTime, item));
        return Array.from(atTime.values()).sort((a, b) => a.startTime - b.startTime);
    }

    function buildSequence(char, items) {
        const tracks = animTracks(char);
        const data = { characterName: char.name, totalDuration: 0, initialVisible: initialVisible(char), visibility: getVisibilitySwitches(char, items), animations: [], transforms: [] };
        items.filter(item => tracks.includes(item.group)).slice().sort((a, b) => seconds(a.start) - seconds(b.start)).forEach(item => {
            if (!Number.isFinite(seconds(item.start))) return;
            data.animations.push({ track: tracks.indexOf(item.group), animName: animName(item), startTime: seconds(item.start), loop: item.loop !== false, mixTime: item.mixDuration !== undefined ? item.mixDuration : 0.2 });
            data.totalDuration = Math.max(data.totalDuration, endTime(item));
        });
        const fields = {
            move: item => ({ endX: item.motEndX, endY: item.motEndY }),
            scale: item => ({ endS: item.motEndS }),
            rotate: item => ({ endR: item.motEndR }),
            alpha: item => ({ endA: item.motEndA })
        };
        Object.keys(fields).forEach(type => clipsFor(items, char.tracks && char.tracks[type]).forEach(item => {
            const startTime = seconds(item.start), duration = Math.max(0, endTime(item) - startTime);
            data.transforms.push(Object.assign({ type, startTime, duration }, fields[type](item), { ease: item.easing || 'linear' }));
            data.totalDuration = Math.max(data.totalDuration, startTime + duration);
        }));
        data.visibility.forEach(item => { data.totalDuration = Math.max(data.totalDuration, item.startTime); });
        return data;
    }

    function buildNativeCocosAnim(char, items, name) {
        // Keep the legacy .anim curves and frame order byte-for-byte equivalent
        // after JSON serialization; only visibility events/duration are added.
        const exportTracks = animTracks(char).concat(['move', 'scale', 'rotate', 'alpha'].map(type => char.tracks && char.tracks[type]));
        let nativeDuration = 0;
        exportTracks.forEach(track => clipsFor(items, track).forEach(item => { nativeDuration = Math.max(nativeDuration, endTime(item)); }));
        getVisibilitySwitches(char, items).forEach(item => { nativeDuration = Math.max(nativeDuration, item.startTime); });
        const refs = [], events = [], output = [{
            __type__: 'cc.AnimationClip', _name: name, _objFlags: 0,
            __editorExtras__: { embeddedPlayerGroups: [] }, _native: '', sample: 60, speed: 1,
            wrapMode: 1, enableTrsBlending: false, _duration: nativeDuration || 1,
            _hash: Date.now() % 1000000000, _tracks: refs, _exoticAnimation: null, _events: events, _embeddedPlayers: []
        }];
        getVisibilityEvents(char, items).forEach(item => events.push({ frame: item.startTime, func: 'setSpineVisible', params: [item.visible] }));
        clipsFor(items, animTracks(char)[0]).forEach(item => events.push({ frame: seconds(item.start), func: 'playSpineAnim', params: [animName(item), item.loop !== undefined ? item.loop : true] }));
        events.sort((a, b) => a.frame - b.frame);
        const keyframe = value => ({ __type__: 'cc.RealKeyframeValue', interpolationMode: 0, value });

        function addVectorTrack(type, path, base, start, end) {
            const clips = clipsFor(items, char.tracks && char.tracks[type]);
            if (!clips.length) return;
            const id = output.length, times = [], values = [[], [], []];
            refs.push({ __id__: id });
            output.push({ __type__: 'cc.animation.VectorTrack', _nComponents: 3,
                _binding: { __type__: 'cc.animation.TrackBinding', path: { __type__: 'cc.animation.TrackPath', _paths: [path] }, proxy: null },
                _channels: [1, 3, 5].map(offset => ({ __id__: id + offset })) });
            function add(time, point) {
                times.push(time);
                point.forEach((value, axis) => values[axis].push(keyframe(value)));
            }
            if (seconds(clips[0].start) > 0) add(0, base);
            clips.forEach(item => {
                const s = seconds(item.start), e = endTime(item);
                add(s, start(item));
                if (e > s) add(e, end(item));
            });
            values.forEach((axisValues, axis) => {
                output.push({ __type__: 'cc.animation.Channel', _curve: { __id__: id + 2 + axis * 2 } });
                output.push({ __type__: 'cc.RealCurve', _times: times, _values: axisValues });
            });
        }
        addVectorTrack('move', 'position', [char.baseX, char.baseY * -1, 0], item => [item.motStartX, item.motStartY * -1, 0], item => [item.motEndX, item.motEndY * -1, 0]);
        addVectorTrack('scale', 'scale', [char.scaleX, char.scaleY, 1], item => [item.motStartS, item.motStartS, 1], item => [item.motEndS, item.motEndS, 1]);
        addVectorTrack('rotate', 'eulerAngles', [0, 0, char.baseRot * -1], item => [0, 0, item.motStartR * -1], item => [0, 0, item.motEndR * -1]);
        const alphas = clipsFor(items, char.tracks && char.tracks.alpha);
        if (alphas.length) {
            const id = output.length, times = [], values = [];
            refs.push({ __id__: id });
            output.push({ __type__: 'cc.animation.RealTrack',
                _binding: { __type__: 'cc.animation.TrackBinding', path: { __type__: 'cc.animation.TrackPath', _paths: [{ __type__: 'cc.animation.ComponentPath', component: 'cc.UIOpacity' }, 'opacity'] }, proxy: null },
                _channel: { __id__: id + 1 } });
            function add(time, alpha) { times.push(time); values.push(keyframe(Math.round(alpha * 255))); }
            if (seconds(alphas[0].start) > 0) add(0, char.baseAlpha !== undefined ? char.baseAlpha : 1);
            alphas.forEach(item => { const s = seconds(item.start), e = endTime(item); add(s, item.motStartA); if (e > s) add(e, item.motEndA); });
            output.push({ __type__: 'cc.animation.Channel', _curve: { __id__: id + 2 } });
            output.push({ __type__: 'cc.RealCurve', _times: times, _values: values });
        }
        return output;
    }

    function buildCodeSnippet(char, items, engine) {
        const cocos = engine !== 'unity', lines = [], tracks = animTracks(char), spineObject = char.type === 'spine';
        const visibilityEvents = getVisibilityEvents(char, items);
        const visibleAtStart = (visibilityEvents.find(item => item.startTime === 0) || { visible: initialVisible(char) }).visible;
        const f = value => number(value).toFixed(3).replace(/0+$/, '').replace(/\.$/, '.0');
        const cs = value => f(value) + 'f';
        const quote = value => JSON.stringify(String(value));
        const waitCall = (time, body) => cocos
            ? `tween(node).delay(${f(time)}).call(() => { ${body} }).start();`
            : `timeline.InsertCallback(${cs(time)}, () => { ${body} });`;
        const ease = value => {
            const name = value || 'linear';
            const cocosNames = { easeOutQuad: 'quadOut', easeInOutQuad: 'quadInOut', easeOutBack: 'backOut', easeOutElastic: 'elasticOut' };
            if (cocos) return quote(cocosNames[name] || name);
            const map = { linear: 'Linear', easeOutQuad: 'OutQuad', easeInOutQuad: 'InOutQuad', easeOutBack: 'OutBack', easeOutElastic: 'OutElastic', easeIn: 'InQuad', easeOut: 'OutQuad', easeInOut: 'InOutQuad', quadIn: 'InQuad', quadOut: 'OutQuad', quadInOut: 'InOutQuad', cubicIn: 'InCubic', cubicOut: 'OutCubic', cubicInOut: 'InOutCubic', quartIn: 'InQuart', quartOut: 'OutQuart', quartInOut: 'InOutQuart', quintIn: 'InQuint', quintOut: 'OutQuint', quintInOut: 'InOutQuint', sineIn: 'InSine', sineOut: 'OutSine', sineInOut: 'InOutSine', expoIn: 'InExpo', expoOut: 'OutExpo', expoInOut: 'InOutExpo', circIn: 'InCirc', circOut: 'OutCirc', circInOut: 'InOutCirc', elasticIn: 'InElastic', elasticOut: 'OutElastic', elasticInOut: 'InOutElastic', backIn: 'InBack', backOut: 'OutBack', backInOut: 'InOutBack', bounceIn: 'InBounce', bounceOut: 'OutBounce', bounceInOut: 'InOutBounce' };
            return 'Ease.' + (map[name] || 'Linear');
        };
        lines.push(`// 物件：${String(char.name).replace(/[\r\n]/g, ' ')}；所有時間均從序列開始計算（秒）。`);
        if (cocos) {
            lines.push('// Cocos Creator 3.x：在目標 node 執行；匯入 tween, v3, sp, Sprite, UIOpacity。', 'const spine = node.getComponent(sp.Skeleton);', 'const visual = spine || node.getComponent(Sprite);', 'if (!visual) throw new Error("找不到 sp.Skeleton 或 Sprite");', `visual.enabled = ${visibleAtStart};`);
        } else {
            if (spineObject) lines.push('// Unity：已取得 skeletonAnimation；需要 Spine.Unity 與 DG.Tweening。', 'var transform = skeletonAnimation.transform;');
            else lines.push('// Unity：已取得目標物件 transform；需要 DG.Tweening。');
            lines.push('var visualRenderer = transform.GetComponent<UnityEngine.Renderer>();', 'var timeline = DOTween.Sequence();', `visualRenderer.enabled = ${visibleAtStart};`);
        }
        visibilityEvents.forEach(item => lines.push(waitCall(item.startTime, cocos ? `visual.enabled = ${item.visible};` : `visualRenderer.enabled = ${item.visible};`)));
        const vector = (x, y, z) => cocos ? `v3(${f(x)}, ${f(y)}, ${f(z)})` : `new UnityEngine.Vector3(${cs(x)}, ${cs(y)}, ${cs(z)})`;
        const transformSpecs = {
            move: item => ({ property: 'position', start: vector(item.motStartX, cocos ? -number(item.motStartY) : item.motStartY, 0), end: vector(item.motEndX, cocos ? -number(item.motEndY) : item.motEndY, 0), method: 'DOLocalMove', assign: 'localPosition' }),
            scale: item => ({ property: 'scale', start: vector(item.motStartS, item.motStartS, 1), end: vector(item.motEndS, item.motEndS, 1), method: 'DOScale', assign: 'localScale' }),
            rotate: item => ({ property: 'eulerAngles', start: vector(0, 0, cocos ? -number(item.motStartR) : item.motStartR), end: vector(0, 0, cocos ? -number(item.motEndR) : item.motEndR), method: 'DOLocalRotate', assign: 'localEulerAngles' })
        };
        Object.keys(transformSpecs).forEach(type => clipsFor(items, char.tracks && char.tracks[type]).forEach(item => {
            const spec = transformSpecs[type](item), s = seconds(item.start), dur = Math.max(0, endTime(item) - s);
            if (cocos) lines.push(`tween(node).delay(${f(s)}).set({ ${spec.property}: ${spec.start} }).to(${f(dur)}, { ${spec.property}: ${spec.end} }, { easing: ${ease(item.easing)} }).start();`);
            else {
                lines.push(waitCall(s, `transform.${spec.assign} = ${spec.start};`));
                lines.push(`timeline.Insert(${cs(s)}, transform.${spec.method}(${spec.end}, ${cs(dur)}).SetEase(${ease(item.easing)}));`);
            }
        }));
        const alphas = clipsFor(items, char.tracks && char.tracks.alpha);
        if (alphas.length) {
            if (cocos) lines.push('const opacity = node.getComponent(UIOpacity) || node.addComponent(UIOpacity);');
            else lines.push('// ApplyObjectAlpha(float value)：自行實作物件材質或 Spine 色彩的透明度設定。');
            alphas.forEach(item => {
                const s = seconds(item.start), dur = Math.max(0, endTime(item) - s);
                if (cocos) lines.push(`tween(opacity).delay(${f(s)}).set({ opacity: ${Math.round(number(item.motStartA, 1) * 255)} }).to(${f(dur)}, { opacity: ${Math.round(number(item.motEndA, 1) * 255)} }, { easing: ${ease(item.easing)} }).start();`);
                else {
                    lines.push(waitCall(s, `ApplyObjectAlpha(${cs(item.motStartA)});`));
                    lines.push(`timeline.Insert(${cs(s)}, DOVirtual.Float(${cs(item.motStartA)}, ${cs(item.motEndA)}, ${cs(dur)}, ApplyObjectAlpha).SetEase(${ease(item.easing)}));`);
                }
            });
        }
        items.filter(item => spineObject && tracks.includes(item.group)).slice().sort((a, b) => seconds(a.start) - seconds(b.start)).forEach(item => {
            const track = tracks.indexOf(item.group), name = quote(animName(item)), loop = item.loop !== false;
            if (Number.isFinite(seconds(item.start))) lines.push(waitCall(seconds(item.start), cocos ? `spine.setAnimation(${track}, ${name}, ${loop});` : `skeletonAnimation.AnimationState.SetAnimation(${track}, ${name}, ${loop});`));
        });
        if (!cocos) lines.push(`timeline.AppendInterval(Mathf.Max(0f, ${cs(buildSequence(char, items).totalDuration)} - timeline.Duration()));`, 'timeline.Play();');
        return lines.join('\n') + '\n';
    }

    function selectedCharacter() {
        const char = typeof selectedCharId !== 'undefined' && typeof characters !== 'undefined' && characters.find(item => item.id === selectedCharId);
        if (!char) { global.alert('請先選擇一個 Spine 物件！'); return null; }
        return char;
    }
    function timelineItems() { return typeof timelineData !== 'undefined' && timelineData ? timelineData.get() : []; }
    function downloadJSON(data, filename) {
        const anchor = global.document.createElement('a');
        anchor.href = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(data, null, 2));
        anchor.download = filename;
        anchor.click();
    }
    function install() {
        global.exportSequenceJSON = function () {
            const char = selectedCharacter(); if (!char) return;
            downloadJSON(buildSequence(char, timelineItems()), char.name + '_Sequence.json');
        };
        global.exportNativeCocosAnim = function () {
            const char = selectedCharacter(); if (!char) return;
            const name = global.prompt('請輸入動畫名稱（檔名與 Cocos Clip Name）：', char.name + '_Anim');
            if (!name || !name.trim()) return;
            downloadJSON(buildNativeCocosAnim(char, timelineItems(), name.trim()), name.trim() + '.anim');
        };
        global.exportCodeSnippet = async function () {
            const char = selectedCharacter(); if (!char) return;
            const selection = global.document.querySelector('input[name="exportEngine"]:checked');
            const code = buildCodeSnippet(char, timelineItems(), selection ? selection.value : 'cocos');
            try {
                await global.navigator.clipboard.writeText(code);
                global.alert('腳本已複製！\n\n' + code);
            } catch (_) { global.prompt('瀏覽器無法直接複製，請從下方手動複製腳本：', code); }
        };
    }
    const api = { getVisibilitySwitches, getVisibilityEvents, buildSequence, buildNativeCocosAnim, buildCodeSnippet, install };
    global.SpineVisibilityExports = api;
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    if (typeof window !== 'undefined') install();
})(typeof globalThis !== 'undefined' ? globalThis : this);
