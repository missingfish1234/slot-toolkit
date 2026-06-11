import { _decorator, Component, sp } from 'cc';
const { ccclass, executeInEditMode } = _decorator;

@ccclass('SpineTimelineHook')
@executeInEditMode
export class SpineTimelineHook extends Component {
    private spine: sp.Skeleton | null = null;

    private getSpine(): sp.Skeleton | null {
        if (!this.spine) {
            this.spine = this.getComponent(sp.Skeleton);
        }
        return this.spine;
    }

    /**
     * 提供給 Cocos Animation Event 呼叫。
     * HTML 工具 V119 會傳入：playSpineAnim(animName, loop)
     */
    public playSpineAnim(animName: string, loop: boolean = true) {
        const spine = this.getSpine();
        if (!spine || !animName) return;

        // 避免同一格 / 同一段事件重複呼叫時一直從頭播放，造成看起來卡住。
        const currentTrack = spine.getCurrent(0);
        const currentName = currentTrack?.animation?.name;
        if (currentName === animName) return;

        spine.setAnimation(0, animName, loop);
    }

    /**
     * 可選：給時間軸事件或手動測試用，清空 Track 0。
     */
    public clearSpineAnim(mixDuration: number = 0.1) {
        const spine = this.getSpine();
        if (!spine) return;
        spine.setEmptyAnimation(0, mixDuration);
    }
}
