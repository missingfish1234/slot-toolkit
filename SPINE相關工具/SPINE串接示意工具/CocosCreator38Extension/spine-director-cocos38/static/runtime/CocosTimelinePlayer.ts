import {
    _decorator,
    Animation,
    Component,
    director,
    JsonAsset,
    Node,
    ParticleSystem,
    ParticleSystem2D,
    resources,
    sp,
    UIOpacity,
    v3,
} from 'cc';

const { ccclass, property } = _decorator;

interface TimelineTransform {
    x: number;
    y: number;
    z: number;
    rx: number;
    ry: number;
    rz: number;
    sx: number;
    sy: number;
    sz: number;
    active: boolean;
    opacity: number;
}

interface TimelineKey extends TimelineTransform {
    id: string;
    time: number;
}

interface TimelineClip {
    id: string;
    type: 'spine' | 'animation' | 'particle2d' | 'particle3d';
    animation?: string;
    start: number;
    duration: number;
    loop?: boolean;
}

interface TimelineTrack {
    id: string;
    nodeUuid: string;
    nodeName: string;
    nodePath?: string;
    initialTransform: TimelineTransform;
    transformKeys: TimelineKey[];
    clips: TimelineClip[];
}

interface NativeTimeline {
    schema: 'cocos-native-timeline@1';
    name: string;
    duration: number;
    fps: number;
    loop: boolean;
    tracks: TimelineTrack[];
}

interface BoundTrack {
    data: TimelineTrack;
    node: Node;
    spine: sp.Skeleton | null;
    animation: Animation | null;
    particle2d: ParticleSystem2D | null;
    particle3d: ParticleSystem | null;
    opacity: UIOpacity | null;
    activeClips: Map<string, string>;
}

function findNodeByUuid(root: Node, uuid: string): Node | null {
    if (root.uuid === uuid) return root;
    for (const child of root.children) {
        const found = findNodeByUuid(child, uuid);
        if (found) return found;
    }
    return null;
}

function findNodeByPath(root: Node, nodePath: string): Node | null {
    const names = String(nodePath || '').split('/').filter(Boolean);
    let current: Node | null = root;
    for (const name of names) {
        current = current.children.find((child) => child.name === name) || null;
        if (!current) return null;
    }
    return current;
}

function number(value: unknown, fallback = 0): number {
    const result = Number(value);
    return Number.isFinite(result) ? result : fallback;
}

function interpolateTransform(
    keys: TimelineKey[],
    time: number,
    fallback: TimelineTransform,
): TimelineTransform {
    if (!keys.length) return { ...fallback };
    const sorted = [...keys].sort((a, b) => a.time - b.time);
    if (time <= sorted[0].time) return { ...sorted[0] };
    if (time >= sorted[sorted.length - 1].time) return { ...sorted[sorted.length - 1] };
    const rightIndex = sorted.findIndex((key) => key.time >= time);
    const left = sorted[Math.max(0, rightIndex - 1)];
    const right = sorted[rightIndex];
    const ratio = right.time === left.time ? 0 : (time - left.time) / (right.time - left.time);
    const result = { ...left } as TimelineTransform;
    for (const field of ['x', 'y', 'z', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz', 'opacity'] as const) {
        result[field] = number(left[field]) + (number(right[field]) - number(left[field])) * ratio;
    }
    result.active = ratio < 1 ? left.active : right.active;
    return result;
}

@ccclass('CocosTimelinePlayerGameAnimation')
export class CocosTimelinePlayer extends Component {
    @property({ tooltip: 'resources 內的 Timeline 路徑；自動產生的播放元件會填入。' })
    public configPath = '';

    @property
    public playOnLoad = true;

    @property
    public loop = false;

    private timeline: NativeTimeline | null = null;
    private bindings: BoundTrack[] = [];
    private currentTime = 0;
    private playing = false;
    private loading = false;
    private lifecycleRevision = 0;
    private disposed = false;
    private resumeOnEnable = false;

    protected onEnable(): void {
        if (!this.timeline && this.configPath && !this.loading) void this.loadTimeline();
        else if (this.resumeOnEnable) { this.resumeOnEnable = false; this.play(); }
    }

    protected onDisable(): void {
        this.lifecycleRevision += 1;
        this.loading = false;
        this.resumeOnEnable = this.playing;
        this.playing = false;
        for (const binding of this.bindings) {
            if (binding.spine?.isValid) binding.spine.timeScale = 0;
            if (binding.animation?.isValid) binding.animation.pause();
            if (binding.particle3d?.isValid) binding.particle3d.pause();
        }
    }

    protected onDestroy(): void {
        this.disposed = true;
        this.lifecycleRevision += 1;
        this.loading = false;
        this.playing = false;
        this.bindings = [];
        this.timeline = null;
    }

    protected getDefaultConfigPath(): string {
        return '';
    }

    protected onLoad(): void {
        if (!this.configPath) this.configPath = this.getDefaultConfigPath();
        if (this.configPath) void this.loadTimeline();
    }

    public async loadTimeline(): Promise<void> {
        if (this.loading || !this.configPath) return;
        this.loading = true;
        const revision = ++this.lifecycleRevision;
        const loadingScene = director.getScene();
        try {
            const asset = await new Promise<JsonAsset>((resolve, reject) => {
                resources.load(this.configPath, JsonAsset, (error, result) => {
                    if (error || !result) reject(error || new Error(`找不到 Timeline：${this.configPath}`));
                    else resolve(result);
                });
            });
            if (this.disposed || revision !== this.lifecycleRevision || !this.isValid || !this.enabledInHierarchy || director.getScene() !== loadingScene) return;
            const timeline = asset.json as unknown as NativeTimeline;
            if (!timeline || timeline.schema !== 'cocos-native-timeline@1') {
                throw new Error('Timeline 格式不正確。');
            }
            this.timeline = timeline;
            this.loop = timeline.loop ?? this.loop;
            this.bindSceneNodes();
            this.seek(0);
            if (this.playOnLoad) this.play();
        } catch (error) {
            if (!this.disposed && revision === this.lifecycleRevision) console.error('[CocosTimelinePlayer] 載入失敗', error);
        } finally {
            if (revision === this.lifecycleRevision) this.loading = false;
        }
    }

    public play(): void {
        if (!this.timeline) return;
        this.playing = true;
        this.evaluate(this.currentTime, true);
        for (const binding of this.bindings) {
            if (binding.spine) binding.spine.timeScale = 1;
        }
    }

    public pause(): void {
        this.playing = false;
        this.evaluate(this.currentTime, true);
        for (const binding of this.bindings) {
            if (binding.spine) binding.spine.timeScale = 0;
            binding.animation?.pause();
        }
    }

    public stop(): void {
        this.playing = false;
        this.currentTime = 0;
        for (const binding of this.bindings) binding.activeClips.clear();
        this.evaluate(0, true);
    }

    public seek(seconds: number): void {
        if (!this.timeline) return;
        this.currentTime = Math.max(0, Math.min(number(seconds), this.timeline.duration));
        for (const binding of this.bindings) binding.activeClips.clear();
        this.evaluate(this.currentTime, true);
    }

    public get time(): number {
        return this.currentTime;
    }

    protected update(deltaTime: number): void {
        if (!this.playing || !this.timeline) return;
        this.currentTime += deltaTime;
        if (this.currentTime >= this.timeline.duration) {
            if (this.loop && this.timeline.duration > 0) {
                this.currentTime %= this.timeline.duration;
                for (const binding of this.bindings) binding.activeClips.clear();
                this.evaluate(this.currentTime, true);
                return;
            }
            this.currentTime = this.timeline.duration;
            this.playing = false;
        }
        this.evaluate(this.currentTime, false);
    }

    private bindSceneNodes(): void {
        this.bindings.length = 0;
        const scene = director.getScene();
        if (!scene || !this.timeline) return;
        for (const track of this.timeline.tracks || []) {
            const node = (track.nodePath ? findNodeByPath(scene, track.nodePath) : null)
                || findNodeByUuid(scene, track.nodeUuid);
            if (!node) {
                console.warn(`[CocosTimelinePlayer] 找不到節點：${track.nodePath || track.nodeName}`);
                continue;
            }
            this.bindings.push({
                data: track,
                node,
                spine: node.getComponent(sp.Skeleton),
                animation: node.getComponent(Animation),
                particle2d: node.getComponent(ParticleSystem2D),
                particle3d: node.getComponent(ParticleSystem),
                opacity: node.getComponent(UIOpacity),
                activeClips: new Map(),
            });
        }
    }

    private evaluate(time: number, forceSeek: boolean): void {
        for (const binding of this.bindings) {
            const transform = interpolateTransform(
                binding.data.transformKeys || [],
                time,
                binding.data.initialTransform,
            );
            binding.node.active = transform.active !== false;
            binding.node.setPosition(v3(transform.x, transform.y, transform.z));
            binding.node.setRotationFromEuler(transform.rx, transform.ry, transform.rz);
            binding.node.setScale(v3(transform.sx, transform.sy, transform.sz));
            if (binding.opacity) binding.opacity.opacity = Math.max(0, Math.min(255, transform.opacity));

            const clips = binding.data.clips || [];
            this.evaluateSpine(
                binding,
                this.activeClip(clips, 'spine', time),
                time,
                forceSeek,
                clips.some((clip) => clip.type === 'spine'),
            );
            this.evaluateAnimation(binding, this.activeClip(clips, 'animation', time), time, forceSeek);
            this.evaluateParticle2D(
                binding,
                this.activeClip(clips, 'particle2d', time),
                time,
                forceSeek,
            );
            this.evaluateParticle3D(binding, this.activeClip(clips, 'particle3d', time));
        }
    }

    private activeClip(clips: TimelineClip[], type: TimelineClip['type'], time: number): TimelineClip | null {
        return clips.find((clip) => (
            clip.type === type && time >= clip.start && time < clip.start + clip.duration
        )) || null;
    }

    private evaluateSpine(
        binding: BoundTrack,
        clip: TimelineClip | null,
        time: number,
        forceSeek: boolean,
        owned: boolean,
    ): void {
        const skeleton = binding.spine;
        const activeId = binding.activeClips.get('spine');
        if (!skeleton || !clip || !clip.animation) {
            if (skeleton && owned) {
                if (activeId !== '__off__') {
                    skeleton.enabled = true;
                    skeleton.clearTrack(0);
                    skeleton.setToSetupPose();
                    skeleton.updateAnimation(0);
                }
                skeleton.enabled = false;
                binding.activeClips.set('spine', '__off__');
                (skeleton as any)._markForUpdateRenderData?.();
            } else {
                binding.activeClips.delete('spine');
            }
            return;
        }
        skeleton.enabled = true;
        if (activeId !== clip.id || forceSeek) {
            skeleton.setAnimationCacheMode(sp.Skeleton.AnimationCacheMode.REALTIME);
            skeleton.paused = false;
            skeleton.timeScale = 1;
            skeleton.clearTrack(0);
            skeleton.setToSetupPose();
            const entry = skeleton.setAnimation(0, clip.animation, !!clip.loop);
            if (entry && forceSeek) {
                const localTime = Math.max(0, time - clip.start);
                entry.trackTime = localTime;
                const state = skeleton.getState();
                const runtimeSkeleton = (skeleton as any)._skeleton;
                if (state && runtimeSkeleton && typeof state.apply === 'function') {
                    state.update(0);
                    state.apply(runtimeSkeleton);
                    runtimeSkeleton.updateWorldTransform?.();
                    (skeleton as any)._markForUpdateRenderData?.();
                } else {
                    entry.trackTime = 0;
                    skeleton.updateAnimation(localTime);
                }
            }
            binding.activeClips.set('spine', clip.id);
        }
        skeleton.timeScale = this.playing ? 1 : 0;
    }

    private evaluateAnimation(
        binding: BoundTrack,
        clip: TimelineClip | null,
        time: number,
        forceSeek: boolean,
    ): void {
        const animation = binding.animation;
        const activeId = binding.activeClips.get('animation');
        if (!animation || !clip || !clip.animation) {
            if (animation && activeId) animation.stop();
            binding.activeClips.delete('animation');
            return;
        }
        if (activeId !== clip.id || forceSeek) {
            animation.play(clip.animation);
            binding.activeClips.set('animation', clip.id);
        }
        if (forceSeek) {
            const state = animation.getState(clip.animation);
            if (state) {
                state.setTime(Math.max(0, time - clip.start));
                state.sample();
                state.pause();
            }
        }
    }

    private evaluateParticle2D(
        binding: BoundTrack,
        clip: TimelineClip | null,
        time: number,
        forceSeek: boolean,
    ): void {
        if (!binding.particle2d) return;
        const particle = binding.particle2d;
        const activeId = binding.activeClips.get('particle2d');
        if (!clip) {
            if (activeId !== '__off__' || particle.enabled !== false) {
                particle.enabled = true;
                particle.resetSystem();
                particle.stopSystem();
                const renderData = (particle as any)._simulator?.renderData;
                renderData?.reset?.();
                renderData?.resize?.(0, 0);
                renderData?.setRenderDrawInfoAttributes?.();
                particle.enabled = false;
                (particle as any)._markForUpdateRenderData?.();
            }
            binding.activeClips.set('particle2d', '__off__');
            return;
        }
        if (activeId !== clip.id || forceSeek) {
            particle.enabled = true;
            (particle as any)._flushAssembler?.();
            particle.resetSystem();
            binding.activeClips.set('particle2d', clip.id);
            if (forceSeek) {
                let remaining = Math.max(0, time - clip.start);
                const simulator = (particle as any)._simulator;
                while (simulator && remaining > 0) {
                    const step = Math.min(1 / 30, remaining);
                    simulator.step(step);
                    remaining -= step;
                }
                if (simulator && !this.playing) {
                    simulator.active = false;
                    simulator.finished = true;
                    (particle as any)._stopped = false;
                    (particle as any)._markForUpdateRenderData?.();
                }
            }
        }
    }

    private evaluateParticle3D(binding: BoundTrack, clip: TimelineClip | null): void {
        if (!binding.particle3d) return;
        const activeId = binding.activeClips.get('particle3d');
        if (clip && activeId !== clip.id) {
            binding.particle3d.stop();
            binding.particle3d.play();
            binding.activeClips.set('particle3d', clip.id);
        } else if (!clip && activeId) {
            binding.particle3d.stop();
            binding.activeClips.delete('particle3d');
        }
    }
}
