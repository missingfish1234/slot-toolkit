using UnityEngine;
using UnityEngine.UI;

[ExecuteAlways]
[DisallowMultipleComponent]
public class BMFontUv2Normalizer : BaseMeshEffect
{
    public override void ModifyMesh(VertexHelper vh)
    {
        if (!IsActive() || vh.currentVertCount < 4) return;

        int count = vh.currentVertCount;
        var v = new UIVertex();

        // 遍歷所有頂點，預設每 4 個頂點組成一個字 (Quad)
        for (int i = 0; i < count; i += 4)
        {
            // 為了處理不同字型的頂點順序，我們用座標來判斷哪個是左下、哪個是右上
            // 先抓出這四個點的幾何邊界
            float minX = float.MaxValue, minY = float.MaxValue;
            float maxX = float.MinValue, maxY = float.MinValue;

            for (int k = 0; k < 4; k++)
            {
                if (i + k >= count) break;
                vh.PopulateUIVertex(ref v, i + k);
                Vector3 pos = v.position;
                if (pos.x < minX) minX = pos.x;
                if (pos.y < minY) minY = pos.y;
                if (pos.x > maxX) maxX = pos.x;
                if (pos.y > maxY) maxY = pos.y;
            }

            float width = maxX - minX;
            float height = maxY - minY;

            // 再次遍歷這 4 個點，根據它們在邊界中的位置，寫入 0~1 的座標
            for (int k = 0; k < 4; k++)
            {
                if (i + k >= count) break;
                vh.PopulateUIVertex(ref v, i + k);

                // 計算歸一化座標 (0~1)
                // 這裡使用 position 來算，保證是針對"形狀"的完美拉伸
                float normX = (width > 0) ? (v.position.x - minX) / width : 0;
                float normY = (height > 0) ? (v.position.y - minY) / height : 0;

                // ★ 關鍵修改：
                // uv1 存放歸一化座標 (0~1)，這就是彩虹的進度
                v.uv1 = new Vector2(normX, normY);
                
                // uv2 存放一個 "訊號"，告訴 Shader "我有正確的資料了"
                // 我們設為 (100, 100) 這種不可能在字體 Atlas 出現的大小作為標記
                v.uv2 = new Vector2(100f, 100f);

                vh.SetUIVertex(v, i + k);
            }
        }
    }
}