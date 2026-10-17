using System;
using System.Collections;
using System.IO;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

public class FoodApiSender : MonoBehaviour
{
    [SerializeField] private ARFoodCameraCapture cameraCapture;
    [SerializeField] private string serverUrl = "http://localhost:8000/food/analyze";
    [Tooltip("비워두면 이미지 API와 같은 서버의 /food/nutrition 사용")]
    [SerializeField] private string nutritionServerUrl = "";
    [Tooltip("절대 경로 또는 persistentDataPath 기준 상대 경로")]
    [SerializeField] private string imageFilePath = "food.jpg";
    [SerializeField] private string nutritionFilePath = "my_nutrition.json";

    public FoodResult LastAnalysis { get; private set; }
    public FoodNutritionResult LastNutrition { get; private set; }
    public bool IsBusy { get; private set; }
    public event Action<FoodResult> OnAnalysisCompleted;
    public event Action<FoodNutritionResult> OnNutritionCompleted;
    public event Action<string> OnRequestFailed;

    private void Start()
    {
        if (GetComponent<FoodScanLiveUI>() == null)
            gameObject.AddComponent<FoodScanLiveUI>().Initialize(this);
    }

    public void UseManualCapture()
    {
        if (cameraCapture != null) cameraCapture.OnCaptureCompleted -= OnCaptured;
        cameraCapture = null;
    }

    public void CancelRequests()
    {
        StopAllCoroutines();
        IsBusy = false;
        LastAnalysis = null;
        LastNutrition = null;
    }

    private void OnEnable()
    {
        if (cameraCapture != null) cameraCapture.OnCaptureCompleted += OnCaptured;
    }

    private void OnDisable()
    {
        if (cameraCapture != null) cameraCapture.OnCaptureCompleted -= OnCaptured;
    }

    private void OnCaptured(Texture2D texture, byte[] jpg) { SendImageBytes(jpg); }

    [ContextMenu("Send food.jpg")]
    public void SendFoodImageFile() { SendFile(imageFilePath, false); }

    [ContextMenu("Send my_nutrition.json")]
    public void SendNutritionFile() { SendFile(nutritionFilePath, true); }

    private void SendFile(string path, bool nutrition)
    {
        byte[] data;
        try
        {
            if (!Path.IsPathRooted(path)) path = Path.Combine(Application.persistentDataPath, path);
            data = File.ReadAllBytes(path);
        }
        catch (Exception ex) { Fail("파일 읽기 실패: " + ex.Message); return; }
        BeginRequest(data, nutrition);
    }

    public void SendImageBytes(byte[] jpg) { BeginRequest(jpg, false); }

    public void SendNutritionJson(string json)
    {
        BeginRequest(string.IsNullOrWhiteSpace(json) ? null : Encoding.UTF8.GetBytes(json), true);
    }

    // UI 후보 버튼에서 0, 1, 2를 전달하면 선택 음식과 예측 중량을 JSON으로 업로드한다.
    public void SelectCandidate(int index)
    {
        if (LastAnalysis == null || LastAnalysis.candidates == null ||
            index < 0 || index >= LastAnalysis.candidates.Length || LastAnalysis.weight == null)
        { Fail("먼저 이미지 분석을 완료하고 유효한 후보를 선택하세요."); return; }
        string json = JsonUtility.ToJson(new FoodNutritionSelection {
            name = LastAnalysis.candidates[index].food, grams = LastAnalysis.weight.predicted_g
        });
        try
        {
            File.WriteAllText(Path.Combine(Application.persistentDataPath, "my_nutrition.json"), json, new UTF8Encoding(false));
        }
        catch (Exception ex) { Fail("선택 음식 JSON 저장 실패: " + ex.Message); return; }
        SendNutritionJson(json);
    }

    private void BeginRequest(byte[] data, bool nutrition)
    {
        if (!isActiveAndEnabled) { Fail("FoodApiSender가 활성화되어 있지 않습니다."); return; }
        if (IsBusy) { Fail("이전 요청이 진행 중입니다."); return; }
        if (data == null || data.Length == 0) { Fail("전송할 파일이 비어 있습니다."); return; }
        if (data.Length > (nutrition ? 64 * 1024 : 8 * 1024 * 1024))
        { Fail(nutrition ? "JSON은 64KB 이하로 보내주세요." : "사진은 8MB 이하로 보내주세요."); return; }
        string url = serverUrl;
        if (nutrition)
        {
            if (!string.IsNullOrWhiteSpace(nutritionServerUrl)) url = nutritionServerUrl;
            else if (Uri.TryCreate(serverUrl, UriKind.Absolute, out Uri imageUri))
                url = new Uri(imageUri, "/food/nutrition").AbsoluteUri;
            else { Fail("서버 URL이 올바르지 않습니다."); return; }
        }
        if (!Uri.TryCreate(url, UriKind.Absolute, out Uri endpoint) ||
            (endpoint.Scheme != "http" && endpoint.Scheme != "https"))
        { Fail("HTTP 서버 URL을 입력하세요."); return; }
        LastNutrition = null;
        if (!nutrition) LastAnalysis = null;
        StartCoroutine(SendUpload(data, nutrition, url));
    }

    private IEnumerator SendUpload(byte[] data, bool nutrition, string url)
    {
        IsBusy = true;
        string responseJson = null;
        try
        {
            WWWForm form = new WWWForm();
            form.AddBinaryData(nutrition ? "file" : "image", data,
                nutrition ? "my_nutrition.json" : "food.jpg",
                nutrition ? "application/json" : "image/jpeg");
            using (UnityWebRequest request = UnityWebRequest.Post(url, form))
            {
                request.timeout = nutrition ? 30 : 330;
                yield return request.SendWebRequest();
                if (request.result != UnityWebRequest.Result.Success)
                { Fail(request.error + "\n" + request.downloadHandler.text); yield break; }
                responseJson = request.downloadHandler.text;
            }
        }
        finally { IsBusy = false; }
        if (responseJson != null) ProcessResponse(responseJson, nutrition);
    }

    private void ProcessResponse(string json, bool nutrition)
    {
        try
        {
            if (nutrition)
            {
                FoodNutritionResponse response = JsonUtility.FromJson<FoodNutritionResponse>(json);
                if (response == null || response.status != "success" || response.result == null || response.result.nutrients == null)
                    throw new FormatException("영양소 응답을 읽지 못했습니다.");
                LastNutrition = response.result;
                Debug.Log("[FoodAPI] " + LastNutrition.food + " / " + LastNutrition.display_basis);
                foreach (FoodNutrient item in LastNutrition.nutrients)
                    Debug.Log(item.label + ": " + (item.has_value ? item.value + " " + item.unit : "데이터 없음"));
            }
            else
            {
                FoodApiResponse response = JsonUtility.FromJson<FoodApiResponse>(json);
                if (response == null || response.status != "success" || response.result == null ||
                    response.result.candidates == null || response.result.candidates.Length != 3 ||
                    response.result.weight == null || response.result.weight.predicted_g <= 0 ||
                    float.IsNaN(response.result.weight.predicted_g) || float.IsInfinity(response.result.weight.predicted_g))
                    throw new FormatException("음식 후보 3개와 유효한 중량이 필요합니다.");
                LastAnalysis = response.result;
                foreach (FoodDetection item in LastAnalysis.candidates)
                    Debug.Log("[FoodAPI] 후보: " + item.food + " / 신뢰도 " + item.confidence);
                Debug.Log("[FoodAPI] 예측 중량: " + LastAnalysis.weight.predicted_g + "g");
            }
        }
        catch (Exception ex) { Fail("응답 처리 실패: " + ex.Message); return; }
        // 결과 이벤트에서 바로 다음 요청을 시작할 수 있도록 완료 상태를 먼저 갱신한다.
        IsBusy = false;
        if (nutrition) OnNutritionCompleted?.Invoke(LastNutrition);
        else OnAnalysisCompleted?.Invoke(LastAnalysis);
    }

    private void Fail(string message)
    {
        Debug.LogError("[FoodAPI] " + message);
        OnRequestFailed?.Invoke(message);
    }
}

[Serializable] public class FoodApiResponse
{
    public string status;
    public bool ai_analyzed;
    public FoodResult result;
}
[Serializable] public class FoodResult
{
    public FoodDetection[] detections;
    public FoodDetection[] candidates;
    public FoodWeight weight;
    public string weight_error;
}
[Serializable] public class FoodDetection
{
    public string food;
    public float confidence;
    public bool below_threshold;
}
[Serializable] public class FoodWeight { public float predicted_g; }
[Serializable] public class FoodNutritionSelection { public string name; public float grams; }
[Serializable] public class FoodNutritionResponse { public string status; public FoodNutritionResult result; }
[Serializable] public class FoodNutritionResult
{
    public string food;
    public string display_basis;
    public FoodNutrient[] nutrients;
}
[Serializable] public class FoodNutrient
{
    public string key;
    public string label;
    public string unit;
    public bool has_value;
    public float value;
}
