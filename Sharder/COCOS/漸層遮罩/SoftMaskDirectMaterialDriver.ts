import { _decorator, Component, Sprite, Material, Enum, Vec4 } from 'cc';
import { EDITOR } from 'cc/env';

const { ccclass, property, executeInEditMode } = _decorator;

export enum SoftMaskDirection {
    BottomToTop = 0,
    TopToBottom = 1,
    LeftToRight = 2,
    RightToLeft = 3,
}

@ccclass('SoftMaskDirectMaterialDriver')
@executeInEditMode(true)
export class SoftMaskDirectMaterialDriver extends Component {
    @property({
        type: Sprite,
        displayName: 'Target Sprite',
        tooltip: '拖 Black 節點上的 cc.Sprite 進來',
    })
    targetSprite: Sprite | null = null;

    @property({
        type: Material,
        displayName: 'Target Material',
        tooltip: '拖 Mat-SoftMask.effect.mtl 進來',
    })
    targetMaterial: Material | null = null;

    @property({
        type: Enum(SoftMaskDirection),
        displayName: 'Direction',
    })
    direction: SoftMaskDirection = SoftMaskDirection.BottomToTop;

    @property({
        range: [0, 1],
        slide: true,
        displayName: 'Progress',
        tooltip: '0 = 黑遮罩完整顯示，1 = 黑遮罩完全消失',
    })
    progress = 0;

    @property({
        range: [0.001, 0.5],
        slide: true,
        displayName: 'Feather',
    })
    feather = 0.08;

    @property({
        range: [0, 1],
        slide: true,
        displayName: 'Alpha Mul',
    })
    alphaMul = 1;

    @property({
        displayName: 'Preview In Editor',
        tooltip: '在編輯器或 Animation 視窗中也即時套用',
    })
    previewInEditor = true;

    @property({
        displayName: 'Apply Every Frame',
        tooltip: '動畫控制 Progress 時請開啟',
    })
    applyEveryFrame = true;
    @property({ tooltip: '各遮罩獨立修改；若關閉則同一材質的所有物件同步，僅掛一支 Driver。' })
    independentMaterial = true;

    @property({
        displayName: 'Debug Log',
    })
    debugLog = false;

    private _fadeParams = new Vec4(0, 0.08, 1, 0);
    private _lastKey = '';
    private _appliedMaterial: Material | null = null;
    private _originalMaterial: Material | null = null;
    private _boundSprite: Sprite | null = null;
    private _assignedMaterial: Material | null = null;
    private _independentMode: boolean | null = null;

    onDisable() { this.restore(); }
    onDestroy() { this.restore(); }

    private restore() {
        if (this._boundSprite && this._boundSprite.isValid && this._boundSprite.customMaterial === this._assignedMaterial)
            this._boundSprite.customMaterial = this._originalMaterial;
        this._boundSprite = null; this._appliedMaterial = null; this._assignedMaterial = null; this._independentMode = null; this._lastKey = '';
    }

    onLoad() {
        this.apply();
    }

    onEnable() {
        this.apply();
    }

    start() {
        this.apply();
    }

    onValidate() {
        this.apply();
    }

    lateUpdate() {
        if (this.applyEveryFrame) {
            this.apply();
        }
    }

    private clamp(v: number, min: number, max: number) {
        return Number.isFinite(v) ? Math.max(min, Math.min(max, v)) : min;
    }

    public apply() {
        if (EDITOR && !this.previewInEditor) { this.restore(); return; }
        if (!this.enabledInHierarchy) return;
        if (!this.targetMaterial) {
            this.restore();
            if (this.debugLog) {
                console.warn('[SoftMaskDirectMaterialDriver] Missing Target Material');
            }
            return;
        }

        this.progress = this.clamp(this.progress, 0, 1);
        this.feather = this.clamp(this.feather, 0.001, 0.5);
        this.alphaMul = this.clamp(this.alphaMul, 0, 1);

        this._fadeParams.set(
            this.progress,
            this.feather,
            this.alphaMul,
            this.direction
        );

        if (!this.targetSprite && this._boundSprite) this.restore();
        if (this.targetSprite) {
            if (this._boundSprite !== this.targetSprite) {
                this.restore();
                this._boundSprite = this.targetSprite;
                this._originalMaterial = this.targetSprite.customMaterial;
            }
            if (this.targetSprite.customMaterial !== this.targetMaterial) {
                this.targetSprite.customMaterial = this.targetMaterial;
            }
            if (this._independentMode !== null && this._independentMode !== this.independentMaterial) {
                this.targetSprite.customMaterial = null;
                this.targetSprite.customMaterial = this.targetMaterial;
            }
            this._assignedMaterial = this.targetMaterial;
            this._independentMode = this.independentMaterial;
        }
        if (this.independentMaterial && !this.targetSprite) return;
        const material = this.independentMaterial ? this.targetSprite!.getMaterialInstance(0) : this.targetMaterial;
        if (!material) return;
        const key = [this.progress, this.feather, this.alphaMul, this.direction].join('|');
        if (key === this._lastKey && material === this._appliedMaterial) return;
        material.setProperty('fadeParams', this._fadeParams, 0);
        this._lastKey = key; this._appliedMaterial = material;

        if (this.debugLog) {
            console.log(
                '[SoftMaskDirectMaterialDriver]',
                'progress =', this.progress,
                'feather =', this.feather,
                'alphaMul =', this.alphaMul,
                'direction =', this.direction
            );
        }
    }

    public showMaskImmediately() {
        this.progress = 0;
        this.apply();
    }

    public hideMaskImmediately() {
        this.progress = 1;
        this.apply();
    }
}
