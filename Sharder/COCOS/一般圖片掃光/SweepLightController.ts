import { _decorator, Component, Sprite, Material, math } from 'cc';
const { ccclass, property, requireComponent } = _decorator;

@ccclass('SweepLightController')
@requireComponent(Sprite) // 強制要求掛載此腳本的節點必須要有 Sprite 組件
export class SweepLightController extends Component {

    @property({ tooltip: '掃光一次所需時間(秒)' })
    duration: number = 1.0;

    @property({ tooltip: '每次掃光的間隔時間(秒)' })
    interval: number = 2.0;

    @property({ tooltip: '是否啟動時自動循環' })
    loop: boolean = true;
    @property({ tooltip: '啟用時各 Sprite 使用獨立進度；關閉時需由單一 Controller 同步控制共用材質。' })
    independentMaterial = true;

    private _material: Material | null = null;
    private _timer: number = 0;
    private _isSweeping: boolean = false;
    private _waitTimer: number = 0;

    protected onEnable() {
        const sprite = this.getComponent(Sprite);
        if (sprite) {
            // 獲取自定義材質的實例 (Instance)
            // 這樣修改 progress 時，才不會影響到其他使用同一顆材質的物件
            this._material = this.independentMaterial ? sprite.getMaterialInstance(0) : sprite.customMaterial;
        }
        
        // 初始狀態將光芒移出畫面外
        this.resetProgress();

        if (this.loop) {
            this.play();
        }
    }

    /** 呼叫此方法即可播放一次掃光 */
    public play() {
        this._timer = 0;
        this._isSweeping = true;
        this._waitTimer = 0;
    }

    private resetProgress() {
        if (this._material) {
             // progress 在 -1.0 到 1.0 之間時會出現在畫面上，設為 2.0 代表藏在畫面外
            this._material.setProperty('progress', 2.0);
        }
    }

    protected onDisable() {
        this._isSweeping = false;
        this.resetProgress();
        this._material = null;
    }

    protected update(dt: number) {
        if (!this._material) return;

        if (this._isSweeping) {
            this._timer += dt;
            const safeDuration = Number.isFinite(this.duration) ? Math.max(0.001, this.duration) : 1;
            let timeRatio = Math.min(1, this._timer / safeDuration);
            
            // 將時間比例 (0~1) 映射到 Shader 需要的進度 (-1.0 ~ 1.0)
            let shaderProgress = math.lerp(-1.0, 1.0, timeRatio);
            this._material.setProperty('progress', shaderProgress);

            // 掃光結束
            if (this._timer >= safeDuration) {
                this._isSweeping = false;
                this.resetProgress();
            }
        } else if (this.loop) {
            // 等待下一次間隔
            this._waitTimer += dt;
            if (this._waitTimer >= this.interval) {
                this.play();
            }
        }
    }
}
