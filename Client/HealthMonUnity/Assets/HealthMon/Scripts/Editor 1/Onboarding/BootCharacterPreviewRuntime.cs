using UnityEngine;
using UnityEngine.UI;

public class BootCharacterPreviewRuntime : MonoBehaviour
{
    [Header("Prefab")]
    public GameObject slimePrefab;

    [Header("UI RawImages (3개)")]
    public RawImage[] previewImages = new RawImage[3];

    [Header("Preview Colors")]
    public Color[] previewColors = new Color[3]
    {
        new Color(1f, 0.55f, 0.25f, 1f),   // 썬 - 주황
        new Color(0.25f, 0.95f, 0.70f, 1f), // 민트
        new Color(0.75f, 0.55f, 1f, 1f)     // 라벤더
    };

    [Header("Preview Root Base Position")]
    public Vector3 previewBaseWorldPos = new Vector3(0f, -1000f, 0f);

    private Transform runtimeRoot;
    private readonly RenderTexture[] renderTextures = new RenderTexture[3];

    private void Start()
    {
        BuildPreviews();
    }

    [ContextMenu("Build Previews")]
    public void BuildPreviews()
    {
        if (slimePrefab == null)
        {
            Debug.LogError("[BootPreview] slimePrefab 이 비어있음");
            return;
        }

        if (previewImages == null || previewImages.Length < 3)
        {
            Debug.LogError("[BootPreview] previewImages 배열에 3개를 넣어야 함");
            return;
        }

        GameObject oldRoot = GameObject.Find("HealthMonStartRuntime_Auto");
        if (oldRoot != null)
            Destroy(oldRoot);

        GameObject rootGo = new GameObject("HealthMonStartRuntime_Auto");
        runtimeRoot = rootGo.transform;

        for (int i = 0; i < 3; i++)
        {
            CreateSinglePreview(i);
        }
    }

    private void CreateSinglePreview(int index)
    {
        GameObject singleRoot = new GameObject($"PreviewRoot_{index}");
        singleRoot.transform.SetParent(runtimeRoot, false);
        singleRoot.transform.position = previewBaseWorldPos + new Vector3(index * 6f, 0f, 0f);

        // 모델 생성
        GameObject model = Instantiate(slimePrefab, singleRoot.transform);
        model.name = $"PreviewSlime_{index}";
        model.transform.localPosition = Vector3.zero;
        model.transform.localRotation = Quaternion.Euler(0f, 180f, 0f);
        model.transform.localScale = Vector3.one * 1.15f;

        Color tint = previewColors[Mathf.Clamp(index, 0, previewColors.Length - 1)];
        TintAllRenderers(model, tint);

        // 프리뷰 카메라 생성
        GameObject camGo = new GameObject($"PreviewCamera_{index}");
        camGo.transform.SetParent(singleRoot.transform, false);
        camGo.transform.localPosition = new Vector3(0f, 0.1f, -2.2f);
        camGo.transform.localRotation = Quaternion.identity;

        Camera cam = camGo.AddComponent<Camera>();
        cam.clearFlags = CameraClearFlags.SolidColor;

        // 중요: 배경 투명
        cam.backgroundColor = new Color(0f, 0f, 0f, 0f);

        cam.fieldOfView = 28f;
        cam.nearClipPlane = 0.1f;
        cam.farClipPlane = 50f;
        cam.enabled = true;

        // 중요: 배경 투명 유지용 포맷
        RenderTexture rt = new RenderTexture(512, 512, 24, RenderTextureFormat.ARGB32);
        rt.name = $"RT_BootCharacter_{index}";
        rt.Create();

        cam.targetTexture = rt;
        renderTextures[index] = rt;

        // UI RawImage 연결
        if (previewImages[index] != null)
        {
            previewImages[index].texture = rt;

            // 중요: RawImage 자체는 투명하게 하지 말고 흰색 100%
            previewImages[index].color = Color.white;
            previewImages[index].uvRect = new Rect(0, 0, 1, 1);
        }
        else
        {
            Debug.LogWarning($"[BootPreview] previewImages[{index}] 가 비어있음");
        }
    }

    private void TintAllRenderers(GameObject target, Color tint)
    {
        Renderer[] renderers = target.GetComponentsInChildren<Renderer>(true);

        foreach (Renderer r in renderers)
        {
            Material[] mats = r.materials;

            for (int i = 0; i < mats.Length; i++)
            {
                if (mats[i] == null) continue;

                Material newMat = new Material(mats[i]);

                // URP / Standard 둘 다 대응
                if (newMat.HasProperty("_BaseColor"))
                    newMat.SetColor("_BaseColor", tint);

                if (newMat.HasProperty("_Color"))
                    newMat.SetColor("_Color", tint);

                mats[i] = newMat;
            }

            r.materials = mats;
        }
    }
}