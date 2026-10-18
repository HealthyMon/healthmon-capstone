using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class FoodScanPrototype : MonoBehaviour
{
    [Header("Views")]
    [SerializeField] private GameObject captureView;
    [SerializeField] private GameObject candidateView;
    [SerializeField] private GameObject resultView;

    [Header("Result UI")]
    [SerializeField] private TMP_Text foodNameText;
    [SerializeField] private TMP_Text caloriesText;
    [SerializeField] private TMP_Text proteinText;
    [SerializeField] private TMP_Text carbText;
    [SerializeField] private TMP_Text fatText;
    [SerializeField]
    private QuestPrototype questPrototype;

    [Header("Real Camera Capture")]
    [SerializeField]
    private ARFoodCameraCapture cameraCapture;

    [SerializeField]
    private RawImage capturedPreview;

    [SerializeField]
    private TMP_Text scanStatusText;

    [SerializeField] private Button analyzeButton;

    [Header("API")]
    [SerializeField]
    private HealthMonApiManager apiManager;

    private void Start()
    {
        ShowCapture();

        if (cameraCapture != null)
        {
            cameraCapture.OnCaptureCompleted += HandleCaptureCompleted;
            cameraCapture.OnCaptureFailed += HandleCaptureFailed;
        }

        if (capturedPreview != null)
        {
            capturedPreview.gameObject.SetActive(false);
        }

        if (scanStatusText != null)
        {
            scanStatusText.text = "촬영 준비 완료";
        }

        if (analyzeButton != null)
        {
            analyzeButton.interactable = false;
        }
    }

    private void OnDestroy()
    {
        if (cameraCapture != null)
        {
            cameraCapture.OnCaptureCompleted
                -= HandleCaptureCompleted;

            cameraCapture.OnCaptureFailed
                -= HandleCaptureFailed;
        }
    }

    public void CaptureRealPhoto()
    {
        if (cameraCapture == null)
        {
            Debug.LogError("[FoodScan] ARFoodCameraCapture가 연결되지 않았습니다.");

            if (scanStatusText != null)
            {
                scanStatusText.text = "카메라 연결 오류";
            }

            return;
        }

        if (scanStatusText != null)
        {
            scanStatusText.text = "촬영 중...";
        }

        cameraCapture.Capture();
    }

    private void HandleCaptureCompleted(Texture2D texture, byte[] jpgBytes)
    {
        Debug.Log(
            $"[FoodScan] 촬영 이미지 수신 완료: {jpgBytes.Length} bytes"
        );

        if (capturedPreview != null)
        {
            capturedPreview.texture = texture;
            capturedPreview.gameObject.SetActive(true);
        }

        if (scanStatusText != null)
        {
            scanStatusText.text = "촬영 완료";
        }

         // 나중에 여기에서
        // AI 서버 업로드 실행

        if (analyzeButton != null)
        {
            analyzeButton.interactable = true;
        }
    }

    private void HandleCaptureFailed(string errorMessage)
    {
        Debug.LogError(
            "[FoodScan] 촬영 실패: " + errorMessage
        );

        if (scanStatusText != null)
        {
            scanStatusText.text = "촬영 실패";
        }
    }

    public void ShowCapture()
    {
        captureView.SetActive(true);
        candidateView.SetActive(false);
        resultView.SetActive(false);

        if (capturedPreview != null)
        {
            capturedPreview.gameObject.SetActive(false);
        }

        if (scanStatusText != null)
        {
            scanStatusText.text = "촬영 준비 완료";
        }
        if (analyzeButton != null)
        {
            analyzeButton.interactable = false;
        }

    }

    public void ShowCandidates()
    {
        captureView.SetActive(false);
        candidateView.SetActive(true);
        resultView.SetActive(false);
    }

    public void SelectChickenSalad()
    {
        ShowResult(
            "닭가슴살 샐러드",
            "420 kcal",
            "35 g",
            "28 g",
            "12 g"
        );
    }

    public void SelectChickenRice()
    {
        ShowResult(
            "닭가슴살 덮밥",
            "560 kcal",
            "32 g",
            "65 g",
            "15 g"
        );
    }

    public void SelectCaesarSalad()
    {
        ShowResult(
            "시저 샐러드",
            "380 kcal",
            "18 g",
            "22 g",
            "24 g"
        );
    }

    private void ShowResult(
        string foodName,
        string calories,
        string protein,
        string carb,
        string fat)
    {
        captureView.SetActive(false);
        candidateView.SetActive(false);
        resultView.SetActive(true);

        foodNameText.text = foodName;
        caloriesText.text = "칼로리 : " + calories;
        proteinText.text = "단백질 : " + protein;
        carbText.text = "탄수화물 : " + carb;
        fatText.text = "지방 : " + fat;
    }

    public void ConfirmFood()
    {
        Debug.Log("[Food] 음식 기록 완료: " + foodNameText.text);

        if (questPrototype != null)
        {
            questPrototype.AddFoodRecord();
        }

        ShowCapture();
    }

    public void AnalyzeFood()
    {
        if (cameraCapture == null)
        {
            Debug.LogError(
                "[FoodScan] CameraCapture 없음"
            );

            return;
        }

        if (
            cameraCapture.LastCapturedJpg == null ||
            cameraCapture.LastCapturedJpg.Length == 0
        )
        {
            Debug.LogError(
                "[FoodScan] 촬영된 이미지 없음"
            );

            if (scanStatusText != null)
            {
                scanStatusText.text =
                    "먼저 사진을 촬영해주세요.";
            }

            return;
        }

        if (apiManager == null)
        {
            Debug.LogWarning(
                "[FoodScan] API Manager가 아직 연결되지 않았습니다."
            );

            if (scanStatusText != null)
            {
                scanStatusText.text =
                    "AI 서버 연결 전 테스트 모드";
            }

            ShowCandidates();

            return;
        }

        if (scanStatusText != null)
        {
            scanStatusText.text =
                "AI가 음식을 분석 중...";
        }

        if (analyzeButton != null)
        {
            analyzeButton.interactable = false;
        }

        StartCoroutine(
            apiManager.PostImage(
                "/food/analyze",
                cameraCapture.LastCapturedJpg,
                HandleAnalysisSuccess,
                HandleAnalysisError
            )
        );
    }
    private void HandleAnalysisSuccess(string json)
    {
        Debug.Log(
            "[FoodScan AI SUCCESS] " + json
        );

        if (scanStatusText != null)
        {
            scanStatusText.text =
                "분석 완료";
        }

        // 현재는 서버 JSON 형식이 아직 없으므로
        // 기존 Mock 후보 화면을 표시한다.
        ShowCandidates();
    }
    private void HandleAnalysisError(string error)
    {
        Debug.LogError(
            "[FoodScan AI ERROR] " + error
        );

        if (scanStatusText != null)
        {
            scanStatusText.text =
                "분석 실패";
        }

        if (analyzeButton != null)
        {
            analyzeButton.interactable = true;
        }
    }

}