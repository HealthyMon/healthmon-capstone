using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using TMPro;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.UI;

// 기존 씬을 저장/수정하지 않고 FoodScanPrototype의 버튼만 런타임에 연결한다.
public class FoodScanLiveUI : MonoBehaviour
{
    private FoodApiSender api;
    private FoodScanPrototype legacy;
    private ARFoodCameraCapture cameraCapture;
    private GameObject captureView, candidateView, resultView;
    private TMP_Text status, title, foodName, calories, protein, carb, fat;
    private Button captureButton, analyzeButton;
    private readonly Button[] choices = new Button[3];
    private readonly TMP_Text[] choiceLabels = new TMP_Text[3];
    private readonly Dictionary<Button, Button.ButtonClickedEvent> originalClicks = new Dictionary<Button, Button.ButtonClickedEvent>();
    private bool ready, waitingForNutrition, capturing;
    private int captureVersion;

    public void Initialize(FoodApiSender sender) { api = sender; }

    private IEnumerator Start()
    {
        // 기존 UI의 Start/촬영 이벤트 구독이 완료된 뒤 연결한다.
        yield return null;
        if (api == null) api = GetComponent<FoodApiSender>();
        var prototypes = FindObjectsByType<FoodScanPrototype>(FindObjectsInactive.Include)
            .Where(x => x.gameObject.scene == gameObject.scene).ToArray();
        if (prototypes.Length == 0) yield break;
        try
        {
            if (prototypes.Length != 1) throw new InvalidOperationException("FoodScanPrototype은 씬에 하나만 있어야 합니다.");
            legacy = prototypes[0];
            var cameras = FindObjectsByType<ARFoodCameraCapture>(FindObjectsInactive.Include)
                .Where(x => x.gameObject.scene == gameObject.scene).ToArray();
            if (cameras.Length != 1) throw new InvalidOperationException("ARFoodCameraCapture 연결 대상을 확인하세요.");
            cameraCapture = cameras[0];
            Transform panel = FindObjectsByType<Transform>(FindObjectsInactive.Include)
                .Single(x => x.gameObject.scene == gameObject.scene && x.name == "FoodScanPanel");
            Transform[] nodes = panel.GetComponentsInChildren<Transform>(true);
            captureView = Node(nodes, "CaptureView").gameObject;
            candidateView = Node(nodes, "CandidateView").gameObject;
            resultView = Node(nodes, "ResultView").gameObject;
            status = Node(nodes, "ScanStatusText").GetComponent<TMP_Text>();
            title = Node(nodes, "CandidateTitle").GetComponent<TMP_Text>();
            foodName = Node(nodes, "FoodNameText").GetComponent<TMP_Text>();
            calories = Node(nodes, "CaloriesText").GetComponent<TMP_Text>();
            protein = Node(nodes, "ProteinText").GetComponent<TMP_Text>();
            carb = Node(nodes, "CarbText").GetComponent<TMP_Text>();
            fat = Node(nodes, "FatText").GetComponent<TMP_Text>();
            captureButton = Node(nodes, "CaptureButton").GetComponent<Button>();
            analyzeButton = Node(nodes, "AnalyzeButton").GetComponent<Button>();
            string[] names = { "CandidateButton", "Candidate2Button (1)", "Candidate3Button (2)" };
            for (int i = 0; i < 3; i++)
            {
                choices[i] = Node(nodes, names[i]).GetComponent<Button>();
                choiceLabels[i] = choices[i].GetComponentInChildren<TMP_Text>(true);
            }
            if (new TMP_Text[] { status, title, foodName, calories, protein, carb, fat }.Any(x => x == null)
                || choiceLabels.Any(x => x == null)) throw new InvalidOperationException("음식 UI 텍스트 연결이 누락되었습니다.");
            Button retake = Node(nodes, "RetakeButton").GetComponent<Button>();
            Button confirm = Node(nodes, "ConfirmButton").GetComponent<Button>();
            if (captureButton == null || analyzeButton == null || retake == null || confirm == null)
                throw new InvalidOperationException("음식 UI 버튼 연결이 누락되었습니다.");

            api.UseManualCapture();
            Replace(captureButton, Capture);
            Replace(analyzeButton, Analyze);
            Replace(retake, ResetCapture);
            Replace(confirm, () => { legacy.ConfirmFood(); ResetCapture(); });
            for (int i = 0; i < 3; i++)
            {
                int index = i;
                Replace(choices[i], () => Select(index));
            }
            cameraCapture.OnCaptureCompleted += Captured;
            cameraCapture.OnCaptureFailed += Failed;
            api.OnAnalysisCompleted += Analyzed;
            api.OnNutritionCompleted += NutritionReceived;
            api.OnRequestFailed += Failed;
            ready = true;
            ResetCapture();
        }
        catch (Exception ex) { Debug.LogError("[FoodUI] 자동 연결 실패: " + ex.Message); }
    }

    private static Transform Node(Transform[] nodes, string name) { return nodes.Single(x => x.name == name); }
    private void Replace(Button button, UnityAction action)
    {
        originalClicks.Add(button, button.onClick);
        button.onClick = new Button.ButtonClickedEvent();
        button.onClick.AddListener(action);
    }
    private void SetChoices(bool enabled) { foreach (Button b in choices) b.interactable = enabled; }
    private void ResetCapture()
    {
        api.CancelRequests();
        captureVersion++;
        capturing = false;
        waitingForNutrition = false;
        legacy.ShowCapture();
        captureButton.interactable = true;
        analyzeButton.interactable = false;
        SetChoices(false);
        foreach (TMP_Text label in choiceLabels) label.text = "분석 대기";
    }
    private void Capture()
    {
        if (capturing || api.IsBusy) return;
        capturing = true;
        captureButton.interactable = false;
        analyzeButton.interactable = false;
        status.text = "촬영 중...";
        cameraCapture.Capture();
    }
    private void Captured(Texture2D texture, byte[] jpg)
    {
        capturing = false;
        StartCoroutine(AnalyzeAfterCapture(jpg, ++captureVersion));
    }
    private IEnumerator AnalyzeAfterCapture(byte[] jpg, int version)
    {
        // 기존 UI 촬영 완료 콜백이 상태를 덮어쓰지 않도록 다음 프레임에 요청한다.
        yield return null;
        if (version != captureVersion) yield break;
        BeginAnalysis(jpg);
    }
    private void Analyze()
    {
        if (capturing || api.IsBusy) return;
        BeginAnalysis(cameraCapture.LastCapturedJpg);
    }
    private void BeginAnalysis(byte[] jpg)
    {
        waitingForNutrition = false;
        captureView.SetActive(true); candidateView.SetActive(false); resultView.SetActive(false);
        status.text = cameraCapture.LastCaptureWasTestImage
            ? "테스트 사진(food.jpg)의 음식 후보와 중량을 분석 중..."
            : "AI가 음식 후보와 중량을 분석 중...";
        captureButton.interactable = false;
        analyzeButton.interactable = false;
        SetChoices(false);
        api.SendImageBytes(jpg);
    }
    private void Analyzed(FoodResult result)
    {
        for (int i = 0; i < 3; i++)
            choiceLabels[i].text = result.candidates[i].food + "  " + result.candidates[i].confidence.ToString("P1");
        title.text = "음식을 선택해주세요 · 예측 " + result.weight.predicted_g.ToString("0.0") + " g";
        SetChoices(true);
        legacy.ShowCandidates();
    }
    private void Select(int index)
    {
        if (api.IsBusy) return;
        waitingForNutrition = true;
        SetChoices(false);
        title.text = "선택한 음식의 영양소를 계산 중...";
        api.SelectCandidate(index);
    }
    private void NutritionReceived(FoodNutritionResult result)
    {
        waitingForNutrition = false;
        foodName.text = result.food + " (" + result.display_basis + ")";
        calories.text = "칼로리 : " + Value(result, "energy_kcal");
        protein.text = "단백질 : " + Value(result, "protein_g");
        carb.text = "탄수화물 : " + Value(result, "carbohydrate_g");
        fat.text = "지방 : " + Value(result, "fat_g");
        captureView.SetActive(false); candidateView.SetActive(false); resultView.SetActive(true);
    }
    public static string Value(FoodNutritionResult result, string key)
    {
        FoodNutrient item = result.nutrients == null ? null : Array.Find(result.nutrients, x => x != null && x.key == key);
        return item != null && item.has_value ? item.value.ToString("0.##") + " " + item.unit : "데이터 없음";
    }
    private void Failed(string error)
    {
        capturing = false;
        if (waitingForNutrition)
        {
            title.text = "영양소 조회 실패. 다시 선택해주세요.\n" + error;
            SetChoices(true);
        }
        else
        {
            status.text = "분석 실패. 다시 촬영하거나 분석해주세요.\n" + error;
            captureButton.interactable = true;
            analyzeButton.interactable = cameraCapture.LastCapturedJpg != null;
        }
    }
    private void OnDestroy()
    {
        if (ready)
        {
            cameraCapture.OnCaptureCompleted -= Captured;
            cameraCapture.OnCaptureFailed -= Failed;
            api.OnAnalysisCompleted -= Analyzed;
            api.OnNutritionCompleted -= NutritionReceived;
            api.OnRequestFailed -= Failed;
        }
        foreach (var entry in originalClicks) if (entry.Key != null) entry.Key.onClick = entry.Value;
    }
}

