using System.Collections;
using TMPro;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.Events;

namespace HealthMon.Evolution
{
    /// <summary>
    /// Evolution visual states only. The game/server owns eligibility, model generation,
    /// model download, and actual model replacement. Never interprets elapsed time as success.
    /// Place this manager OUTSIDE EvolutionOverlay so it remains active when the UI is hidden.
    /// </summary>
    public class EvolutionUIController : MonoBehaviour
    {
        [Header("Screen references")]
        public GameObject evolutionOverlay;
        public GameObject evolvingContent;
        public GameObject completedContent;
        public GameObject errorContent;
        public CanvasGroup flashCanvasGroup;

        [Header("Status")]
        public TMP_Text statusText;
        public TMP_Text elapsedText;
        public TMP_Text tipText;
        public TMP_Text errorText;

        [Header("Pet in sphere - sprite fallback / optional live 3D RenderTexture")]
        public Image petPreview2D;
        public Graphic petPreviewFallback;
        public RawImage petPreview3D;
        public Image resultPreview2D;
        public Graphic resultPreviewFallback;
        public RawImage resultPreview3D;
        public RenderTexture petRenderTexture;

        [Header("Optional UI callbacks")]
        public UnityEvent onEvolutionOpened;
        public UnityEvent onEvolutionClosed;
        public UnityEvent onEvolutionCompleted;

        private bool _isEvolving;
        private float _startTime;
        private int _lastTipIndex = -1;
        private Coroutine _transitionRoutine;

        private static readonly string[] Tips = {
            "성장 기록을 새로운 힘으로!",
            "진화 에너지 집중!",
            "다음 형태, 각성 준비!",
            "변신 완료까지 진화 기록 유지"
        };

        private void Awake()
        {
            if (evolutionOverlay != null) evolutionOverlay.SetActive(false);
            if (flashCanvasGroup != null)
            {
                flashCanvasGroup.alpha = 0;
                flashCanvasGroup.blocksRaycasts = false;
                flashCanvasGroup.interactable = false;
            }
            if (petRenderTexture != null) SetPetRenderTexture(petRenderTexture);
            SetLabel(evolvingContent, "Brand", "H E A L T H M O N");
            SetLabel(evolvingContent, "SubtitleText", "한계를 넘어, 다음 형태로!");
            SetLabel(completedContent, "SuccessSubtitle", "새로운 힘, 각성 완료!");
            SetLabel(completedContent, "SuccessMessage", "새로운 모습으로 다음 모험에 출전!");
            SetLabel(errorContent, "ErrorTitle", "진화 일시 중단");
        }

        private void Update()
        {
            if (!_isEvolving) return;
            float elapsed = Mathf.Max(0, Time.unscaledTime - _startTime);
            int totalSeconds = Mathf.FloorToInt(elapsed);
            if (elapsedText != null)
                elapsedText.text = string.Format("경과 시간  {0:00}:{1:00}", totalSeconds / 60, totalSeconds % 60);
            int tipIndex = (totalSeconds / 8) % Tips.Length;
            if (tipIndex != _lastTipIndex)
            {
                _lastTipIndex = tipIndex;
                if (tipText != null) tipText.text = Tips[tipIndex];
            }
        }

        /// <summary>Call when the game logic confirms evolution eligibility, before sending the AI request.</summary>
        public void StartEvolution()
        {
            StopTransition();
            _isEvolving = true;
            _startTime = Time.unscaledTime;
            _lastTipIndex = -1;
            if (evolutionOverlay != null) evolutionOverlay.SetActive(true);
            ShowPart(evolvingContent, true);
            ShowPart(completedContent, false);
            ShowPart(errorContent, false);
            if (flashCanvasGroup != null) flashCanvasGroup.alpha = 0f;
            if (statusText != null) statusText.text = "에너지 동기화 진행 중";
            if (elapsedText != null) elapsedText.text = "경과 시간  00:00";
            if (tipText != null) tipText.text = Tips[0];
            onEvolutionOpened?.Invoke();
        }

        public void MarkModelGenerating()
        {
            SetProgress("새로운 형태 각성 중");
        }

        public void SetProgress(string message)
        {
            if (_isEvolving && statusText != null) statusText.text = message;
        }

        public void MarkModelDownloading()
        {
            if (_isEvolving && statusText != null) statusText.text = "진화 모델을 내려받는 중";
        }

        public void MarkModelApplying()
        {
            if (_isEvolving && statusText != null) statusText.text = "새로운 모습을 적용하는 중";
        }

        /// <summary>Call ONLY after the new model has actually loaded and been applied successfully.</summary>
        public void CompleteEvolution()
        {
            if (!_isEvolving) return;
            StopTransition();
            _transitionRoutine = StartCoroutine(CompleteSequence());
        }

        private IEnumerator CompleteSequence()
        {
            _isEvolving = false;
            if (flashCanvasGroup != null)
            {
                float elapsed = 0f;
                while (elapsed < .25f)
                {
                    elapsed += Time.unscaledDeltaTime;
                    flashCanvasGroup.alpha = Mathf.Clamp01(elapsed / .25f);
                    yield return null;
                }
                flashCanvasGroup.alpha = 1f;
            }

            ShowPart(evolvingContent, false);
            ShowPart(completedContent, true);
            ShowPart(errorContent, false);
            onEvolutionCompleted?.Invoke();

            if (flashCanvasGroup != null)
            {
                float elapsed = 0f;
                while (elapsed < .55f)
                {
                    elapsed += Time.unscaledDeltaTime;
                    flashCanvasGroup.alpha = 1f - Mathf.Clamp01(elapsed / .55f);
                    yield return null;
                }
                flashCanvasGroup.alpha = 0f;
            }
            _transitionRoutine = null;
        }

        public void ShowEvolutionError(string message)
        {
            StopTransition();
            _isEvolving = false;
            if (evolutionOverlay != null) evolutionOverlay.SetActive(true);
            ShowPart(evolvingContent, false);
            ShowPart(completedContent, false);
            ShowPart(errorContent, true);
            if (flashCanvasGroup != null) flashCanvasGroup.alpha = 0f;
            if (errorText != null)
                errorText.text = string.IsNullOrWhiteSpace(message) ? "진화 중단 · 홈에서 다시 도전" : message;
        }

        public void ShowTestError()
        {
            ShowEvolutionError("진화 중단 · 홈에서 다시 도전");
        }

        /// <summary>Optional: preview current pet from a dedicated camera / RenderTexture.</summary>
        public void SetPetRenderTexture(RenderTexture texture)
        {
            petRenderTexture = texture;
            bool hasTexture = texture != null;
            if (petPreview3D != null)
            {
                petPreview3D.rectTransform.localScale = Vector3.one;
                petPreview3D.texture = hasTexture ? (Texture)texture : Texture2D.whiteTexture;
                petPreview3D.enabled = hasTexture;
            }
            if (petPreview2D != null) petPreview2D.enabled = !hasTexture;
            if (petPreviewFallback != null) petPreviewFallback.enabled = !hasTexture;
            if (resultPreview3D != null)
            {
                resultPreview3D.rectTransform.localScale = Vector3.one;
                resultPreview3D.texture = hasTexture ? (Texture)texture : Texture2D.whiteTexture;
                resultPreview3D.enabled = hasTexture;
            }
            if (resultPreview2D != null) resultPreview2D.enabled = !hasTexture;
            if (resultPreviewFallback != null) resultPreviewFallback.enabled = !hasTexture;
        }

        public void CloseEvolution()
        {
            StopTransition();
            _isEvolving = false;
            if (evolutionOverlay != null) evolutionOverlay.SetActive(false);
            onEvolutionClosed?.Invoke();
        }

        private void StopTransition()
        {
            if (_transitionRoutine != null)
            {
                StopCoroutine(_transitionRoutine);
                _transitionRoutine = null;
            }
        }

        private static void ShowPart(GameObject go, bool visible)
        {
            if (go != null) go.SetActive(visible);
        }

        private static void SetLabel(GameObject root, string name, string text)
        {
            if (root == null) return;
            foreach (var label in root.GetComponentsInChildren<TMP_Text>(true))
                if (label.name == name) label.text = text;
        }
    }
}
