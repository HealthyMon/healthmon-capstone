using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.XR.ARFoundation;

// Keep the component name/GUID so existing scene and button bindings stay valid.
// Food photos need an ordinary camera, including phones without ARCore support.
public class ARFoodCameraCapture : MonoBehaviour
{
    [Range(1, 100)] [SerializeField] private int jpegQuality = 80;
    public Texture2D LastCapturedTexture { get; private set; }
    public byte[] LastCapturedJpg { get; private set; }
    public bool LastCaptureWasTestImage { get; private set; }
    public event Action<Texture2D, byte[]> OnCaptureCompleted;
    public event Action<string> OnCaptureFailed;
    public event Action<string> OnPreviewStatusChanged;

    private RawImage preview;
    private RectTransform viewport;
    private GameObject captureView;
    private WebCamTexture cameraTexture;
    private Coroutine opening;
    private bool attempted, frozen, paused;
    private readonly List<ARSession> suspendedSessions = new List<ARSession>();

    public void ConfigurePreview(RawImage target, GameObject view)
    {
        captureView = view;
        if (preview == target && viewport != null) return;
        preview = target;
        if (preview == null) return;
        var rect = preview.rectTransform;
        viewport = (RectTransform)new GameObject("FoodCameraViewport", typeof(RectTransform), typeof(RectMask2D)).transform;
        viewport.SetParent(rect.parent, false);
        viewport.SetSiblingIndex(rect.GetSiblingIndex());
        viewport.anchorMin = rect.anchorMin; viewport.anchorMax = rect.anchorMax;
        viewport.pivot = rect.pivot; viewport.sizeDelta = rect.sizeDelta;
        viewport.anchoredPosition = rect.anchoredPosition;
        rect.SetParent(viewport, false);
        rect.anchorMin = rect.anchorMax = rect.pivot = new Vector2(.5f, .5f);
        rect.anchoredPosition = Vector2.zero;
        preview.raycastTarget = false;
        preview.color = Color.white;
    }

    private bool WantsCamera => !paused && !frozen && preview != null &&
        captureView != null && captureView.activeInHierarchy;

    private void Update()
    {
        if (!WantsCamera)
        {
            if (opening != null || cameraTexture != null) StopPreview();
            return;
        }
        if (!attempted)
        {
            attempted = true;
            opening = StartCoroutine(OpenCamera());
        }
        if (cameraTexture != null && cameraTexture.isPlaying && cameraTexture.width > 16 && cameraTexture.didUpdateThisFrame)
        {
            preview.texture = cameraTexture;
            preview.gameObject.SetActive(true);
        }
    }

    private void LateUpdate()
    {
        if (preview == null || preview.texture == null || viewport == null) return;
        bool live = preview.texture == cameraTexture;
        int rotation = live ? cameraTexture.videoRotationAngle : 0;
        bool mirror = live && cameraTexture.videoVerticallyMirrored;
        float width = preview.texture.width, height = preview.texture.height;
        if (width <= 16 || height <= 16) return;
        bool sideways = rotation == 90 || rotation == 270;
        float scale = Mathf.Max(viewport.rect.width / (sideways ? height : width),
                                viewport.rect.height / (sideways ? width : height));
        preview.rectTransform.sizeDelta = new Vector2(width, height) * scale;
        preview.rectTransform.localEulerAngles = new Vector3(0, 0, -rotation);
        preview.uvRect = mirror ? new Rect(0, 1, 1, -1) : new Rect(0, 0, 1, 1);
    }

    private IEnumerator OpenCamera()
    {
        // Yield first so StopPreview can always cancel the assigned coroutine.
        yield return null;
        OnPreviewStatusChanged?.Invoke("카메라 준비 중…");
#if UNITY_ANDROID && !UNITY_EDITOR
        if (!UnityEngine.Android.Permission.HasUserAuthorizedPermission(UnityEngine.Android.Permission.Camera))
        {
            bool answered = false;
            var callbacks = new UnityEngine.Android.PermissionCallbacks();
            callbacks.PermissionGranted += _ => answered = true;
            callbacks.PermissionDenied += _ => answered = true;
            callbacks.PermissionDeniedAndDontAskAgain += _ => answered = true;
            UnityEngine.Android.Permission.RequestUserPermission(UnityEngine.Android.Permission.Camera, callbacks);
            float permissionDeadline = Time.realtimeSinceStartup + 60;
            while (!answered && Time.realtimeSinceStartup < permissionDeadline) yield return null;
            if (!UnityEngine.Android.Permission.HasUserAuthorizedPermission(UnityEngine.Android.Permission.Camera))
            {
                PreviewFailed("카메라 권한 필요 · 휴대폰 설정에서 카메라 허용 후 다시 촬영");
                yield break;
            }
        }
#elif !UNITY_EDITOR
        if (!Application.HasUserAuthorization(UserAuthorization.WebCam))
            yield return Application.RequestUserAuthorization(UserAuthorization.WebCam);
        if (!Application.HasUserAuthorization(UserAuthorization.WebCam))
        {
            PreviewFailed("카메라 권한 필요 · 설정에서 카메라 허용 후 다시 촬영");
            yield break;
        }
#endif
        // ARSession lives outside the XR root in MainARScene. Disable it as well
        // as the AR view so it cannot retain the hardware camera.
        foreach (var session in FindObjectsByType<ARSession>(FindObjectsSortMode.None))
            if (session.isActiveAndEnabled) { suspendedSessions.Add(session); session.enabled = false; }
        yield return null;
        string device = null;
        foreach (var candidate in WebCamTexture.devices)
        {
            if (device == null) device = candidate.name;
            if (!candidate.isFrontFacing) { device = candidate.name; break; }
        }
        if (device == null)
        {
            PreviewFailed("카메라 없음 · 연결 상태 확인 후 다시 촬영");
            yield break;
        }
        for (int attempt = 0; attempt < 2; attempt++)
        {
            if (!TryOpenDevice(device, attempt == 0)) break;
            float deadline = Time.realtimeSinceStartup + (attempt == 0 ? 4 : 6);
            while (WantsCamera && Time.realtimeSinceStartup < deadline)
            {
                if (cameraTexture.isPlaying && cameraTexture.width > 16 && cameraTexture.didUpdateThisFrame)
                {
                    opening = null;
                    OnPreviewStatusChanged?.Invoke("음식을 프레임에 맞추고 촬영!");
                    Debug.Log("[FoodCapture] Preview ready " + cameraTexture.width + "x" + cameraTexture.height);
                    yield break;
                }
                yield return null;
            }
            ReleaseTexture();
        }
        PreviewFailed("카메라 연결 실패 · 촬영 버튼으로 재시도");
    }

    private bool TryOpenDevice(string device, bool requestSize)
    {
        try
        {
            cameraTexture = requestSize ? new WebCamTexture(device, 1280, 720, 15) : new WebCamTexture(device);
            cameraTexture.Play();
            return true;
        }
        catch (Exception error) { Debug.LogWarning("[FoodCapture] " + error.Message); return false; }
    }

    private void PreviewFailed(string message)
    {
        opening = null;
        ReleaseTexture(); RestoreSessions();
        OnPreviewStatusChanged?.Invoke(message);
        Debug.LogWarning("[FoodCapture] " + message);
    }

    public void ResetPreview()
    {
        StopPreview();
        frozen = false;
        LastCapturedJpg = null;
        LastCaptureWasTestImage = false;
        if (preview != null) { preview.texture = null; preview.gameObject.SetActive(false); }
        if (LastCapturedTexture != null) Destroy(LastCapturedTexture);
        LastCapturedTexture = null;
    }

    public void ShowPhoto(Texture2D texture)
    {
        frozen = true;
        StopPreview();
        if (LastCapturedTexture != null && LastCapturedTexture != texture) Destroy(LastCapturedTexture);
        LastCapturedTexture = texture;
        if (preview != null) { preview.texture = texture; preview.gameObject.SetActive(true); }
    }

    public void Capture()
    {
        LastCapturedJpg = null;
        LastCaptureWasTestImage = false;
        if (cameraTexture == null || !cameraTexture.isPlaying || cameraTexture.width <= 16)
        {
#if UNITY_EDITOR
            CaptureEditorTestImage();
#else
            ResetPreview();
            // Complete the failed attempt so the standalone food UI releases
            // its busy flag as well; opening the preview continues separately.
            OnCaptureFailed?.Invoke("카메라 준비 중 · 영상이 나타나면 촬영!");
#endif
            return;
        }
        Texture2D texture = null;
        try
        {
            int width = cameraTexture.width, height = cameraTexture.height, rotation = cameraTexture.videoRotationAngle;
            HealthMonPoseFrame.GetSize(width, height, rotation, 1600, out int outWidth, out int outHeight);
            var pixels = new Color32[outWidth * outHeight];
            HealthMonPoseFrame.CopyUpright(cameraTexture.GetPixels32(), pixels, width, height,
                rotation, cameraTexture.videoVerticallyMirrored, outWidth, outHeight);
            texture = new Texture2D(outWidth, outHeight, TextureFormat.RGBA32, false);
            texture.SetPixels32(pixels); texture.Apply();
            LastCapturedJpg = texture.EncodeToJPG(jpegQuality);
            ShowPhoto(texture);
        }
        catch (Exception error)
        {
            if (texture != null) Destroy(texture);
            Debug.LogError("[FoodCapture] " + error);
            OnCaptureFailed?.Invoke("사진 처리 실패 · 다시 촬영");
            return;
        }
        Debug.Log("[FoodCapture] Captured " + LastCapturedTexture.width + "x" + LastCapturedTexture.height + " / " + LastCapturedJpg.Length + " bytes");
        OnCaptureCompleted?.Invoke(LastCapturedTexture, LastCapturedJpg);
    }

    public void StopPreview()
    {
        if (opening != null) StopCoroutine(opening);
        opening = null; attempted = false;
        ReleaseTexture(); RestoreSessions();
    }

    private void ReleaseTexture()
    {
        if (cameraTexture == null) return;
        if (preview != null && preview.texture == cameraTexture)
        { preview.texture = null; preview.gameObject.SetActive(false); }
        cameraTexture.Stop(); Destroy(cameraTexture); cameraTexture = null;
    }

    private void RestoreSessions()
    {
        foreach (var session in suspendedSessions) if (session != null) session.enabled = true;
        suspendedSessions.Clear();
    }

    private void OnApplicationPause(bool value) { paused = value; if (value) StopPreview(); }
    private void OnDisable() { StopPreview(); }
    private void OnDestroy() { StopPreview(); if (LastCapturedTexture != null) Destroy(LastCapturedTexture); }

#if UNITY_EDITOR
    private void CaptureEditorTestImage()
    {
        string path = Path.Combine(Application.dataPath, "HealthMon/Scripts/Food/food.jpg");
        Texture2D texture = null;
        try
        {
            byte[] jpg = File.ReadAllBytes(path);
            if (jpg.Length == 0 || jpg.Length > 8 * 1024 * 1024) throw new InvalidDataException("Invalid fixture size");
            texture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            if (!ImageConversion.LoadImage(texture, jpg)) throw new InvalidDataException("Invalid food.jpg");
            ShowPhoto(texture);
            LastCapturedJpg = jpg;
            LastCaptureWasTestImage = true;
        }
        catch (Exception error)
        {
            if (texture != null) Destroy(texture);
            Debug.LogError("[FoodCapture] " + error);
            OnCaptureFailed?.Invoke("PC 테스트 사진 읽기 실패");
            return;
        }
        OnCaptureCompleted?.Invoke(LastCapturedTexture, LastCapturedJpg);
    }
#endif
}
