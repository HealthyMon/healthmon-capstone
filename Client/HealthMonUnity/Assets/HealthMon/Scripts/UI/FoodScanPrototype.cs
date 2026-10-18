using System;
using System.Globalization;
using Healthmon.Beta;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class FoodScanPrototype : MonoBehaviour
{
    [Header("Views")]
    [SerializeField] private GameObject captureView, candidateView, resultView;
    [Header("Result UI")]
    [SerializeField] private TMP_Text foodNameText, caloriesText, proteinText, carbText, fatText;
    [SerializeField] private QuestPrototype questPrototype;
    [Header("Camera")]
    [SerializeField] private ARFoodCameraCapture cameraCapture;
    [SerializeField] private RawImage capturedPreview;
    [SerializeField] private TMP_Text scanStatusText;
    [SerializeField] private Button analyzeButton;
    private DialoguePrototype dialogue;
    private byte[] capturedBytes;
    private FoodAnalysis analysis;
    private FoodCandidate selected;
    private TMP_InputField gramsInput;
    private readonly Button[] candidateButtons = new Button[3];
    private bool confirming;
    public string LastAnalysisId { get; private set; }
    public string LastRecordedSourceId { get; private set; }
    private HealthmonApiClient Api => dialogue == null ? null : dialogue.Api;

    private void Start()
    {
        dialogue = FindAnyObjectByType<DialoguePrototype>(FindObjectsInactive.Include);
        if (cameraCapture != null) { cameraCapture.OnCaptureCompleted += HandleCaptureCompleted; cameraCapture.OnCaptureFailed += HandleCaptureFailed; }
        foreach (var button in candidateView.GetComponentsInChildren<Button>(true))
            for (int i = 0; i < button.onClick.GetPersistentEventCount(); i++)
                if (button.onClick.GetPersistentTarget(i) == this)
                {
                    string method = button.onClick.GetPersistentMethodName(i);
                    int index = method == nameof(SelectChickenSalad) ? 0 : method == nameof(SelectChickenRice) ? 1 : method == nameof(SelectCaesarSalad) ? 2 : -1;
                    if (index >= 0) candidateButtons[index] = button;
                }
        // The updated team scene also has admin inputs. Clone the dialogue input explicitly.
        var template = Array.Find(FindObjectsByType<TMP_InputField>(FindObjectsInactive.Include),
            field => field.name == "MessageInput");
        if (template != null)
        {
            gramsInput = Instantiate(template, resultView.transform);
            gramsInput.name = "ConsumedGrams";
            foreach (var label in gramsInput.GetComponentsInChildren<TMP_Text>(true))
            {
                label.font = foodNameText.font;
                label.fontSize = 24;
                if (label != gramsInput.textComponent && label != gramsInput.placeholder)
                    label.gameObject.SetActive(false);
            }
            gramsInput.onValueChanged = new TMP_InputField.OnChangeEvent();
            gramsInput.onEndEdit = new TMP_InputField.SubmitEvent();
            gramsInput.onSubmit = new TMP_InputField.SubmitEvent();
            gramsInput.text = "";
            gramsInput.contentType = TMP_InputField.ContentType.DecimalNumber;
            gramsInput.characterLimit = 8;
            var rect = gramsInput.GetComponent<RectTransform>();
            rect.anchorMin = new Vector2(.58f, .38f); rect.anchorMax = new Vector2(.94f, .48f);
            rect.offsetMin = rect.offsetMax = Vector2.zero;
            if (gramsInput.placeholder is TMP_Text placeholder) placeholder.text = "먹은 양(g), 모르면 비워두세요";
            gramsInput.onValueChanged.AddListener(_ => RenderSelection());
            gramsInput.gameObject.SetActive(true);
        }
#if UNITY_EDITOR
        if (analyzeButton != null)
        {
            var desktop = Instantiate(analyzeButton, analyzeButton.transform.parent);
            desktop.name = "ChooseDesktopFoodPhoto";
            desktop.onClick = new Button.ButtonClickedEvent();
            desktop.onClick.AddListener(ChooseDesktopPhoto);
            var desktopRect = desktop.GetComponent<RectTransform>();
            desktopRect.anchorMin = new Vector2(.74f, .12f);
            desktopRect.anchorMax = new Vector2(.96f, .22f);
            desktopRect.offsetMin = desktopRect.offsetMax = Vector2.zero;
            var label = desktop.GetComponentInChildren<TMP_Text>(true);
            if (label != null) label.text = "PC 사진 선택";
            desktop.interactable = true;
        }
#endif
        ShowCapture();
    }
    private void Update()
    {
        if (analyzeButton != null) analyzeButton.interactable = capturedBytes != null && Api != null && dialogue.IsConnected && !Api.IsBusy && !Api.HasPendingChat;
    }
    public void CaptureRealPhoto()
    {
        if (cameraCapture == null) { Status("카메라가 연결되지 않았습니다."); return; }
        Status("촬영 중…"); cameraCapture.Capture();
    }
    private void HandleCaptureCompleted(Texture2D texture, byte[] bytes)
    {
        capturedBytes = bytes; analysis = null; selected = null;
        if (capturedPreview != null) { capturedPreview.texture = texture; capturedPreview.gameObject.SetActive(true); }
        Status(cameraCapture != null && cameraCapture.LastCaptureWasTestImage
            ? "PC 시연 사진입니다. 음식 분석을 눌러주세요."
            : "사진 준비 완료. 음식 분석을 눌러주세요.");
    }
    private void HandleCaptureFailed(string error) { Status("촬영 실패: " + error); }
    public void UseImage(byte[] bytes)
    {
        var texture = new Texture2D(2, 2);
        if (!texture.LoadImage(bytes)) { Destroy(texture); Status("이미지를 읽지 못했습니다."); return; }
        HandleCaptureCompleted(texture, bytes);
    }
#if UNITY_EDITOR
    public void ChooseDesktopPhoto()
    {
        string path = UnityEditor.EditorUtility.OpenFilePanelWithFilters("음식 사진 선택", "", new[] { "사진", "jpg,jpeg,png" });
        if (!string.IsNullOrEmpty(path)) UseImage(System.IO.File.ReadAllBytes(path));
    }
#endif
    public void AnalyzeFood()
    {
        if (capturedBytes == null) { Status("먼저 사진을 촬영하거나 선택해 주세요."); return; }
        if (Api == null || !dialogue.IsConnected) { Status("서버에 먼저 연결해 주세요."); return; }
        Status("음식을 분석하고 있어요…");
        Api.AnalyzeFood(capturedBytes, result =>
        {
            analysis = result; LastAnalysisId = result.analysis_id; selected = null;
            if (result.candidates == null || result.candidates.Length == 0) { Status("음식을 찾지 못했어요. 다른 사진으로 시도해 주세요."); return; }
            for (int i = 0; i < candidateButtons.Length; i++)
            {
                var button = candidateButtons[i]; if (button == null) continue;
                button.gameObject.SetActive(i < result.candidates.Length);
                if (i < result.candidates.Length)
                {
                    var label = button.GetComponentInChildren<TMP_Text>(true);
                    if (label != null) label.text = result.candidates[i].food + "  " + (result.candidates[i].confidence * 100).ToString("F0") + "%";
                }
            }
            ShowCandidates();
            Debug.Log($"[HealthMon Vision] AnalysisDisplayed id={result.analysis_id} candidates={result.candidates.Length}");
        }, Failure);
    }
    // Keep the existing scene bindings; choose actual server candidates.
    public void SelectChickenSalad() { SelectCandidate(0); }
    public void SelectChickenRice() { SelectCandidate(1); }
    public void SelectCaesarSalad() { SelectCandidate(2); }
    public void SelectCandidate(int index)
    {
        if (analysis == null || index < 0 || index >= analysis.candidates.Length) return;
        selected = analysis.candidates[index];
        captureView.SetActive(false); candidateView.SetActive(false); resultView.SetActive(true);
        if (gramsInput != null) gramsInput.SetTextWithoutNotify(selected.has_estimated_grams ? selected.estimated_grams.ToString("F1", CultureInfo.InvariantCulture) : "");
        RenderSelection();
    }
    private bool Quantity(out float? grams)
    {
        grams = null;
        if (gramsInput == null || string.IsNullOrWhiteSpace(gramsInput.text)) return true;
        float value;
        if (!float.TryParse(gramsInput.text, NumberStyles.Float, CultureInfo.InvariantCulture, out value) || float.IsNaN(value) || float.IsInfinity(value) || value <= 0 || value > 10000) return false;
        grams = value; return true;
    }
    private static string Nutrient(string label, NutrientValue value, float scale, string unit)
    { return label + " : " + (value != null && value.available ? (value.value * scale).ToString("F1") + unit : "정보 없음"); }
    private void RenderSelection()
    {
        if (selected == null) return;
        float? grams; bool valid = Quantity(out grams);
        float scale = valid && grams.HasValue ? grams.Value / 100 : 1;
        foodNameText.text = selected.food + (grams.HasValue ? "\n" + grams.Value.ToString("F1") + "g 기준" : "\n100g당 참고값 (섭취량 미입력)") + (selected.has_estimated_grams ? "\n사진 추정량은 실제 먹은 양으로 수정해 주세요." : "");
        caloriesText.text = Nutrient("열량", selected.per_100g.energy_kcal, scale, " kcal");
        proteinText.text = Nutrient("단백질", selected.per_100g.protein_g, scale, " g");
        carbText.text = Nutrient("탄수화물", selected.per_100g.carbohydrate_g, scale, " g");
        fatText.text = Nutrient("지방", selected.per_100g.fat_g, scale, " g");
    }
    public void ConfirmFood()
    {
        if (confirming || selected == null || Api == null || Api.IsBusy) return;
        float? grams;
        if (!Quantity(out grams)) { foodNameText.text = "먹은 양을 0보다 크고 10,000g 이하로 입력해 주세요."; return; }
        confirming = true;
        Api.ConfirmFood(analysis.analysis_id, selected.candidate_id, grams, result =>
        {
            confirming = false; LastRecordedSourceId = result.source_id;
            if (!result.duplicate && questPrototype != null) questPrototype.AddFoodRecord();
            ShowCapture(); Status("음식 기록 완료. 대화 화면에서 몽글이의 반응을 확인해 주세요.");
            Debug.Log($"[HealthMon Food] FoodRecorded source_id={result.source_id} duplicate={result.duplicate} state_version={result.state_version}");
        }, error => { confirming = false; Failure(error); });
    }
    public void ShowCapture()
    {
        captureView.SetActive(true); candidateView.SetActive(false); resultView.SetActive(false);
        capturedBytes = null; analysis = null; selected = null;
        if (capturedPreview != null) capturedPreview.gameObject.SetActive(false);
        Status("음식 사진을 촬영하거나 선택해 주세요.");
    }
    public void ShowCandidates() { captureView.SetActive(false); candidateView.SetActive(true); resultView.SetActive(false); }
    private void Status(string text) { if (scanStatusText != null) scanStatusText.text = text; }
    private void Failure(ApiFailure error)
    {
        string message = "분석·저장에 실패했어요 (" + error.StatusCode + "). 다시 시도해 주세요.";
        Status(message); if (selected != null) foodNameText.text = message;
        Debug.LogWarning($"[HealthMon Food] RequestFailed status={error.StatusCode}");
    }
    private void OnDestroy()
    {
        if (cameraCapture != null) { cameraCapture.OnCaptureCompleted -= HandleCaptureCompleted; cameraCapture.OnCaptureFailed -= HandleCaptureFailed; }
    }
}
