import { _decorator, Component, Sprite, Material, Enum, Vec4 } from 'cc';

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

    @property({
        displayName: 'Debug Log',
    })
    debugLog = false;

    private _fadeParams = new Vec4(0, 0.08, 1, 0);

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
        if (this.previewInEditor) {
            this.apply();
        }
    }

    lateUpdate() {
        if (this.applyEveryFrame) {
            this.apply();
        }
    }

    private clamp(v: number, min: number, max: number) {
        return Math.max(min, Math.min(max, v));
    }

    public apply() {
        if (!this.targetMaterial) {
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

        // 直接改材質球本體。
        // 這顆就是你手動改 Progress 會生效的 Mat-SoftMask.effect.mtl。
        this.targetMaterial.setProperty('fadeParams', this._fadeParams, 0);
        this.targetMaterial.setProperty('progress', this.progress, 0);
        this.targetMaterial.setProperty('feather', this.feather, 0);
        this.targetMaterial.setProperty('alphaMul', this.alphaMul, 0);
        this.targetMaterial.setProperty('direction', this.direction, 0);

        // 確保 Black Sprite 用的就是這顆材質。
        // 注意：這裡塞的是 targetMaterial，不是 getMaterialInstance()。
        if (this.targetSprite) {
            if (this.targetSprite.customMaterial !== this.targetMaterial) {
                this.targetSprite.customMaterial = this.targetMaterial;
            }

            this.targetSprite.markForUpdateRenderData(true);
        }

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