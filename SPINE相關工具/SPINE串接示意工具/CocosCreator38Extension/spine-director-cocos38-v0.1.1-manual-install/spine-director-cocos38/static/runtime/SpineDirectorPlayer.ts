import {
    _decorator,
    Asset,
    Component,
    JsonAsset,
    Node,
    resources,
    sp,
    Sprite,
    SpriteFrame,
    UIOpacity,
    v3,
} from 'cc';

const { ccclass, property } = _decorator;

type EaseName = 'linear' | 'easeOutQuad' | 'easeInOutQuad' | 'easeOutBack' | 'easeOutElastic';

interface RuntimeClip {
    id: string;
    start: number;
    end: number;
    easing?: EaseName;
    startX?: number;
    startY?: number;
    endX?: number;
    endY?: number;
    startValue?: number;
    endValue?: number;
}

interface RuntimeAnimationClip {
    id: string;
    track: number;
    animation: string;
    start: number;
    end: number;
    loop: boolean;
    mixDuration: number;
    dropEnable?: boolean;
    dropHeight?: number;
    dropBounce?: number;
    dropDuration?: number;
    dropDelay?: number;
}

interface RuntimeCharacter {
    id: string;
    name: string;
    type: 'spine' | 'image';
    order: number;
    resourcePath: string;
    base: {
        x: number;
        y: number;
        rotation: number;
        scaleX: number;
        scaleY: number;
        alpha: number;
        flipX: boolean;
        visible: boolean;
        skin?: string | null;
    };
    animations: RuntimeAnimationClip[];
    move: RuntimeClip[];
    rotate: RuntimeClip[];
    scale: RuntimeClip[];
    alpha: RuntimeClip[];
}

interface RuntimeConfig {
    schema: string;
    duration: number;
    loop: boolean;
    characters: RuntimeCharacter[];
}

interface CharacterState {
    data: RuntimeCharacter;
    node: Node;
    spine: sp.Skeleton | null;
    opacity: UIOpacity;
    activeAnimations: Map<number, string>;
}

@ccclass('SpineDirectorPlayer')
export class SpineDirectorPlayer extends Component {
    @property({ tooltip: 'resources 內的播放設定路徑；專案輸出元件會自動填入。' })
    public configPath = '';

    @property
    public playOnLoad = true;

    @property
    public loop = false;

    private config: RuntimeConfig | null = null;
    private states: CharacterState[] = [];
    private time = 0;
    private playing = false;
    private loading = false;

    protected getDefaultConfigPath(): string {
        return '';
    }

    protected onLoad(): void {
        if (!this.configPath) this.configPath = this.getDefaultConfigPath();
        if (this.configPath) void this.loadDirector();
    }

    public async loadDirector(): Promise<void> {
        if (this.loading || !this.configPath) return;
        this.loading = true;
        try {
            const jsonAsset = await this.loadResource<JsonAsset>(this.configPath, JsonAsset);
            const config = jsonAsset.json as unknown as RuntimeConfig;
            if (!config || config.schema !== 'spine-director-runtime@1') {
                throw new Error('播放設定格式不正確。');
            }
            this.config = config;
            this.loop = config.loop ?? this.loop;
            await this.createCharacters(config.characters || []);
            this.seek(0);
            if (this.playOnLoad) this.play();
        } catch (error) {
            console.error('[SpineDirectorPlayer] 載入失敗', error);
        } finally {
            this.loading = false;
        }
    }

    public play(): void {
        if (this.config) this.playing = true;
    }

    public pause(): void {
        this.playing = false;
    }

    public stop(): void {
        this.playing = false;
        this.time = 0;
        this.resetAnimationState();
        this.evaluate(0);
    }

    public seek(seconds: number): void {
        if (!this.config) return;
        this.time = Math.max(0, Math.min(seconds, this.config.duration));
        this.resetAnimationState();
        this.evaluate(this.time);
    }

    protected update(deltaTime: number): void {
        if (!this.playing || !this.config) return;
        this.time += deltaTime;
        if (this.time >= this.config.duration) {
            if (this.loop && this.config.duration > 0) {
                this.time %= this.config.duration;
                this.resetAnimationState();
            } else {
                this.time = this.config.duration;
                this.playing = false;
            }
        }
        this.evaluate(this.time);
    }

    private async createCharacters(characters: RuntimeCharacter[]): Promise<void> {
        for (const state of this.states) state.node.destroy();
        this.states.length = 0;

        const sorted = [...characters].sort((a, b) => a.order - b.order);
        await Promise.all(sorted.map(async (data) => {
            const child = new Node(data.name);
            child.setParent(this.node);
            child.setSiblingIndex(Math.max(0, data.order));
            const opacity = child.addComponent(UIOpacity);
            const state: CharacterState = {
                data,
                node: child,
                spine: null,
                opacity,
                activeAnimations: new Map(),
            };

            if (data.type === 'spine') {
                const skeletonData = await this.loadResource<sp.SkeletonData>(data.resourcePath, sp.SkeletonData);
                const skeleton = child.addComponent(sp.Skeleton);
                skeleton.skeletonData = skeletonData;
                if (data.base.skin) skeleton.setSkin(data.base.skin);
                state.spine = skeleton;
            } else {
                const spriteFrame = await this.loadResource<SpriteFrame>(data.resourcePath, SpriteFrame);
                const sprite = child.addComponent(Sprite);
                sprite.spriteFrame = spriteFrame;
            }

            this.states.push(state);
        }));
        this.states.sort((a, b) => a.data.order - b.data.order);
    }

    private evaluate(time: number): void {
        for (const state of this.states) {
            const data = state.data;
            const x = this.evaluateVector(data.move, time, data.base.x, 'x');
            const sourceY = this.evaluateVector(data.move, time, data.base.y, 'y');
            const rotation = this.evaluateNumber(data.rotate, time, data.base.rotation);
            const scale = this.evaluateNumber(data.scale, time, data.base.scaleX);
            const alpha = this.evaluateNumber(data.alpha, time, data.base.alpha);

            let y = -sourceY;
            const mainAnimation = data.animations.find((clip) =>
                clip.track === 0 && time >= clip.start && time < clip.end
            );
            if (mainAnimation?.dropEnable) {
                const local = time - mainAnimation.start - (mainAnimation.dropDelay || 0);
                const duration = mainAnimation.dropDuration || 0.5;
                if (local < 0) {
                    y += mainAnimation.dropHeight || 500;
                } else if (local < duration) {
                    const progress = this.bounce(local / duration, mainAnimation.dropBounce || 0.5);
                    y += (mainAnimation.dropHeight || 500) * (1 - progress);
                }
            }

            state.node.active = data.base.visible;
            state.node.setPosition(x, y, 0);
            state.node.setRotationFromEuler(0, 0, -rotation);
            const flip = data.base.flipX ? -1 : 1;
            const scaleRatioY = data.base.scaleX === 0 ? 1 : data.base.scaleY / data.base.scaleX;
            state.node.setScale(v3(scale * flip, scale * scaleRatioY, 1));
            state.opacity.opacity = Math.round(Math.max(0, Math.min(1, alpha)) * 255);

            if (state.spine) this.evaluateAnimations(state, time);
        }
    }

    private evaluateAnimations(state: CharacterState, time: number): void {
        const tracks = new Set(state.data.animations.map((clip) => clip.track));
        for (const track of tracks) {
            const clip = state.data.animations.find((candidate) =>
                candidate.track === track &&
                time >= candidate.start + (candidate.dropDelay || 0) &&
                time < candidate.end
            );
            const activeId = state.activeAnimations.get(track);

            if (clip && activeId !== clip.id) {
                const entry = state.spine!.setAnimation(track, clip.animation, clip.loop);
                if (entry) entry.mixDuration = clip.mixDuration || 0;
                state.activeAnimations.set(track, clip.id);
            } else if (!clip && activeId) {
                state.spine!.clearTrack(track);
                state.activeAnimations.delete(track);
            }
        }
    }

    private evaluateVector(clips: RuntimeClip[], time: number, fallback: number, axis: 'x' | 'y'): number {
        const startKey = axis === 'x' ? 'startX' : 'startY';
        const endKey = axis === 'x' ? 'endX' : 'endY';
        const active = clips.find((clip) => time >= clip.start && time <= clip.end);
        if (active) {
            const start = active[startKey] ?? fallback;
            const end = active[endKey] ?? start;
            return this.interpolate(start, end, active, time);
        }
        const previous = [...clips].reverse().find((clip) => clip.end <= time);
        return previous?.[endKey] ?? fallback;
    }

    private evaluateNumber(clips: RuntimeClip[], time: number, fallback: number): number {
        const active = clips.find((clip) => time >= clip.start && time <= clip.end);
        if (active) {
            return this.interpolate(active.startValue ?? fallback, active.endValue ?? fallback, active, time);
        }
        const previous = [...clips].reverse().find((clip) => clip.end <= time);
        return previous?.endValue ?? fallback;
    }

    private interpolate(start: number, end: number, clip: RuntimeClip, time: number): number {
        if (clip.end <= clip.start) return start;
        const ratio = Math.max(0, Math.min(1, (time - clip.start) / (clip.end - clip.start)));
        const eased = this.ease(clip.easing || 'linear', ratio);
        return start + (end - start) * eased;
    }

    private ease(name: EaseName, t: number): number {
        switch (name) {
            case 'easeOutQuad': return t * (2 - t);
            case 'easeInOutQuad': return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
            case 'easeOutBack': {
                const c1 = 1.70158;
                return 1 + (c1 + 1) * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
            }
            case 'easeOutElastic': {
                const c4 = (2 * Math.PI) / 3;
                return t === 0 || t === 1 ? t : Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * c4) + 1;
            }
            default: return t;
        }
    }

    private bounce(t: number, amount: number): number {
        if (amount <= 0.05) return t * t * t;
        const n1 = 7.5625;
        const d1 = 2.75;
        if (t < 1 / d1) return n1 * t * t;
        if (t < 2 / d1) return n1 * (t -= 1.5 / d1) * t + 0.75;
        if (t < 2.5 / d1) return n1 * (t -= 2.25 / d1) * t + 0.9375;
        return n1 * (t -= 2.625 / d1) * t + 0.984375;
    }

    private resetAnimationState(): void {
        for (const state of this.states) {
            state.spine?.clearTracks();
            state.activeAnimations.clear();
        }
    }

    private loadResource<T extends Asset>(resourcePath: string, type: new (...args: any[]) => T): Promise<T> {
        return new Promise<T>((resolve, reject) => {
            resources.load(resourcePath, type, (error, asset) => {
                if (error || !asset) reject(error || new Error(`找不到素材：${resourcePath}`));
                else resolve(asset);
            });
        });
    }
}
