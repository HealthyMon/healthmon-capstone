using System;
using System.Collections;
using UnityEngine;
using UnityEngine.Networking;

public class HealthMonApiManager : MonoBehaviour
{
    [Header("Server")]
    [SerializeField]
    private string baseUrl =
        "http://localhost:8000";

    public string BaseUrl => baseUrl;

    public IEnumerator PostImage(
        string path,
        byte[] imageBytes,
        Action<string> onSuccess,
        Action<string> onError)
    {
        WWWForm form =
            new WWWForm();

        form.AddBinaryData(
            "image",
            imageBytes,
            "food.jpg",
            "image/jpeg"
        );

        using UnityWebRequest request =
            UnityWebRequest.Post(
                baseUrl + path,
                form
            );

        request.timeout = 15;

        yield return request.SendWebRequest();

        if (
            request.result ==
            UnityWebRequest.Result.Success
        )
        {
            onSuccess?.Invoke(
                request.downloadHandler.text
            );
        }
        else
        {
            onError?.Invoke(
                request.error
            );
        }
    }
}