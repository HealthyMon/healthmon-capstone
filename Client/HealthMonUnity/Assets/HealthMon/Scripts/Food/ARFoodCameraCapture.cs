using System;
using System.Collections;
using System.IO;
using Unity.Collections;
using UnityEngine;
using UnityEngine.XR.ARFoundation;
using UnityEngine.XR.ARSubsystems;

public class ARFoodCameraCapture : MonoBehaviour
{
    [Header("AR Camera")]
    [SerializeField] private ARCameraManager cameraManager;

    [Header("Capture Settings")]
    [Range(1, 100)]
    [SerializeField] private int jpegQuality = 80;

    public Texture2D LastCapturedTexture { get; private set; }
    public byte[] LastCapturedJpg { get; private set; }
    public bool LastCaptureWasTestImage { get; private set; }

    public event Action<Texture2D, byte[]> OnCaptureCompleted;
    public event Action<string> OnCaptureFailed;

    public void Capture()
    {
        StartCoroutine(CaptureRoutine());
    }

    private IEnumerator CaptureRoutine()
    {

        // 실패 후 이전 촬영 파일을 다시 보내지 않도록 전송 데이터를 초기화한다.
        LastCapturedJpg = null;
        LastCaptureWasTestImage = false;

#if UNITY_EDITOR
    // PC Unity Editor에서는 가상 카메라 대신 Food/food.jpg 사용
    CaptureEditorTestImage();
    yield break;
#endif

        if (cameraManager == null)
        {
#if UNITY_EDITOR
            CaptureEditorTestImage();
#else
            Fail("ARCameraManager가 연결되어 있지 않습니다.");
#endif
            yield break;
        }

        if (!cameraManager.TryAcquireLatestCpuImage(out XRCpuImage cpuImage))
        {
#if UNITY_EDITOR
            CaptureEditorTestImage();
#else
            Fail("현재 카메라 이미지를 가져오지 못했습니다.");
#endif
            yield break;
        }

        var conversionParams =
            new XRCpuImage.ConversionParams(
                cpuImage,
                TextureFormat.RGBA32,
                XRCpuImage.Transformation.MirrorY
            );

        int size =
            cpuImage.GetConvertedDataSize(conversionParams);

        NativeArray<byte> buffer =
            new NativeArray<byte>(
                size,
                Allocator.Temp
            );

        try
        {
            cpuImage.Convert(
                conversionParams,
                buffer
            );

            Vector2Int dimensions =
                conversionParams.outputDimensions;

            Texture2D texture =
                new Texture2D(
                    dimensions.x,
                    dimensions.y,
                    TextureFormat.RGBA32,
                    false
                );

            texture.LoadRawTextureData(buffer);
            texture.Apply();

            if (LastCapturedTexture != null)
            {
                Destroy(LastCapturedTexture);
            }

            LastCapturedTexture = texture;

            LastCapturedJpg =
                texture.EncodeToJPG(jpegQuality);

            Debug.Log(
                $"[FoodCapture] 촬영 완료 " +
                $"{dimensions.x}x{dimensions.y} / " +
                $"{LastCapturedJpg.Length} bytes"
            );

            OnCaptureCompleted?.Invoke(
                LastCapturedTexture,
                LastCapturedJpg
            );
        }
        catch (Exception e)
        {
            Fail(
                "카메라 이미지 변환 실패: " +
                e.Message
            );
        }
        finally
        {
            buffer.Dispose();
            cpuImage.Dispose();
        }

        yield return null;
    }

#if UNITY_EDITOR
    private void CaptureEditorTestImage()
    {
        string path = Path.Combine(Application.dataPath, "HealthMon/Scripts/Food/food.jpg");
        Texture2D texture = null;
        try
        {
            byte[] jpg = File.ReadAllBytes(path);
            if (jpg.Length == 0 || jpg.Length > 8 * 1024 * 1024)
                throw new InvalidDataException("테스트 사진은 0바이트보다 크고 8MB 이하여야 합니다.");
            texture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            if (!ImageConversion.LoadImage(texture, jpg))
                throw new InvalidDataException("food.jpg 이미지를 읽을 수 없습니다.");
            if (LastCapturedTexture != null) Destroy(LastCapturedTexture);
            LastCapturedTexture = texture;
            // 재인코딩 없이 Food 폴더의 원본 파일 바이트를 전송한다.
            LastCapturedJpg = jpg;
            LastCaptureWasTestImage = true;
        }
        catch (Exception ex)
        {
            if (texture != null) Destroy(texture);
            Fail("테스트 사진 읽기 실패: " + path + " / " + ex.Message);
            return;
        }
        Debug.Log("[FoodCapture] 카메라 사용 불가 → 테스트 사진 전송: " + path + " / " + LastCapturedJpg.Length + " bytes");
        OnCaptureCompleted?.Invoke(LastCapturedTexture, LastCapturedJpg);
    }
#endif

    private void Fail(string message)
    {
        Debug.LogError(
            "[FoodCapture] " + message
        );

        OnCaptureFailed?.Invoke(message);
    }
}
