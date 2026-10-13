using System;
using System.Collections;
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

    public event Action<Texture2D, byte[]> OnCaptureCompleted;
    public event Action<string> OnCaptureFailed;

    public void Capture()
    {
        StartCoroutine(CaptureRoutine());
    }

    private IEnumerator CaptureRoutine()
    {
        if (cameraManager == null)
        {
            Fail("ARCameraManager가 연결되어 있지 않습니다.");
            yield break;
        }

        if (!cameraManager.TryAcquireLatestCpuImage(out XRCpuImage cpuImage))
        {
            Fail("현재 카메라 이미지를 가져오지 못했습니다.");
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

    private void Fail(string message)
    {
        Debug.LogError(
            "[FoodCapture] " + message
        );

        OnCaptureFailed?.Invoke(message);
    }
}