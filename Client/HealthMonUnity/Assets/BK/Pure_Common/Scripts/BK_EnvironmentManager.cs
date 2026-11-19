using UnityEngine;

namespace BKPureNature
{
    [ExecuteInEditMode]
    public class BK_EnvironmentManager : MonoBehaviour
    {
        private const int MaxInstanceCount = 1023;

        private static readonly int WindPowerId = Shader.PropertyToID("WindPower");
        private static readonly int WindSpeedId = Shader.PropertyToID("WindSpeed");
        private static readonly int WindBurstsPowerId = Shader.PropertyToID("WindBurstsPower");
        private static readonly int WindBurstsSpeedId = Shader.PropertyToID("WindBurstsSpeed");
        private static readonly int WindBurstsScaleId = Shader.PropertyToID("WindBurstsScale");
        private static readonly int MicroPowerId = Shader.PropertyToID("MicroPower");
        private static readonly int MicroSpeedId = Shader.PropertyToID("MicroSpeed");
        private static readonly int MicroFrequencyId = Shader.PropertyToID("MicroFrequency");
        private static readonly int GrassRenderDistanceId = Shader.PropertyToID("GrassRenderDist");

        private static readonly int CloudsPositionId = Shader.PropertyToID("_cloudsPosition");
        private static readonly int CloudsHeightId = Shader.PropertyToID("_cloudsHeight");
        private static readonly int ScatteringColorId = Shader.PropertyToID("_ScatteringColor");

        public Light directionalLight;

        public Gradient sunColorGradient;
        public Gradient fogColorGradient;

        // Kept for backward compatibility with existing scenes and prefabs.
        public Gradient cloudColorGradient;
        public Gradient scatteringColorGradient;
        public Gradient ambientColorGradient;

        [Header("Color Gradients Enable Flags")]
        public bool overrideSunColor = true;
        public bool overrideFogColor = true;
        public bool overrideCloudColor = true;
        public bool overrideAmbientColor = true;

        [Header("Base Wind")]
        [Tooltip("Base wind animates the trunks")]
        [Range(0f, 5f)]
        public float baseWindPower = 3f;

        [Tooltip("Base wind animation speed")]
        public float baseWindSpeed = 1f;

        [Header("Wind Burst")]
        [Tooltip("Bursts are managed by a moving world-space noise that multiplies the base wind speed and power")]
        [Range(0f, 10f)]
        public float burstsPower = 0.5f;

        [Tooltip("Speed of the bursts noise")]
        public float burstsSpeed = 5f;

        [Tooltip("Size of the bursts noise in world space")]
        public float burstsScale = 10f;

        [Header("Micro Wind")]
        [Tooltip("Micro wind animates the leaves")]
        [Range(0f, 1f)]
        public float microPower = 0.1f;

        [Tooltip("Micro wind animation speed")]
        public float microSpeed = 1f;

        [Tooltip("Micro wind animation frequency")]
        public float microFrequency = 3f;

        [Space(10)]
        public float renderDistance = 30f;

        [Space(10)]
        public float Altitude = 1000f;
        public float volumeSize = 500f;

        [Min(1)]
        public int volumeSamples = 25;

        [Space(10)]
        [Tooltip("Material for the clouds")]
        public Material cloudsMaterial;

        private Mesh quadMesh;
        private Matrix4x4[] matrices;
        private MaterialPropertyBlock cloudProperties;

        private int cachedVolumeSamples = -1;
        private float cachedVolumeSize = float.NaN;
        private float cachedAltitude = float.NaN;

        private bool hasIssuedMaterialWarning;
        private bool hasIssuedMeshWarning;

        private void Awake()
        {
            EnsureInitialized();
        }

        private void OnEnable()
        {
            EnsureInitialized();
            InvalidateCloudMatrices();
        }

        private void OnValidate()
        {
            volumeSamples = Mathf.Clamp(volumeSamples, 1, MaxInstanceCount);
            volumeSize = Mathf.Max(0f, volumeSize);
            InvalidateCloudMatrices();
        }

        private void Update()
        {
            UpdateEnvironment();
            UpdateLighting();
            UpdateCloudsVolume();
        }

        private void EnsureInitialized()
        {
            if (quadMesh == null)
            {
                quadMesh = Resources.GetBuiltinResource<Mesh>("Quad.fbx");
            }

            if (cloudProperties == null)
            {
                cloudProperties = new MaterialPropertyBlock();
            }

            int sampleCount = Mathf.Clamp(volumeSamples, 1, MaxInstanceCount);
            if (matrices == null || matrices.Length != sampleCount)
            {
                matrices = new Matrix4x4[sampleCount];
            }
        }

        private void InvalidateCloudMatrices()
        {
            cachedVolumeSamples = -1;
            cachedVolumeSize = float.NaN;
            cachedAltitude = float.NaN;
        }

        private void UpdateEnvironment()
        {
            Shader.SetGlobalFloat(WindPowerId, baseWindPower);
            Shader.SetGlobalFloat(WindSpeedId, baseWindSpeed);
            Shader.SetGlobalFloat(WindBurstsPowerId, burstsPower);
            Shader.SetGlobalFloat(WindBurstsSpeedId, burstsSpeed);
            Shader.SetGlobalFloat(WindBurstsScaleId, burstsScale);
            Shader.SetGlobalFloat(MicroPowerId, microPower);
            Shader.SetGlobalFloat(MicroSpeedId, microSpeed);
            Shader.SetGlobalFloat(MicroFrequencyId, microFrequency);
            Shader.SetGlobalFloat(GrassRenderDistanceId, renderDistance);
        }

        private void UpdateCloudsVolume()
        {
            if (cloudsMaterial == null)
            {
                hasIssuedMaterialWarning = false;
                return;
            }

            EnsureInitialized();

            if (quadMesh == null)
            {
                if (!hasIssuedMeshWarning)
                {
                    Debug.LogWarning("The built-in Quad mesh could not be loaded by the EnvironmentManager.", this);
                    hasIssuedMeshWarning = true;
                }

                return;
            }

            hasIssuedMeshWarning = false;

            if (!cloudsMaterial.HasProperty(CloudsPositionId) ||
                !cloudsMaterial.HasProperty(CloudsHeightId) ||
                !cloudsMaterial.HasProperty(ScatteringColorId))
            {
                if (!hasIssuedMaterialWarning)
                {
                    Debug.LogWarning(
                        "The assigned material in the Cloud material slot of the EnvironmentManager isn't supported.",
                        this);
                    hasIssuedMaterialWarning = true;
                }

                return;
            }

            hasIssuedMaterialWarning = false;

            int sampleCount = Mathf.Clamp(volumeSamples, 1, MaxInstanceCount);
            float safeVolumeSize = Mathf.Max(0f, volumeSize);

            if (matrices == null || matrices.Length != sampleCount)
            {
                matrices = new Matrix4x4[sampleCount];
                InvalidateCloudMatrices();
            }

            RebuildCloudMatricesIfNeeded(sampleCount, safeVolumeSize);

            cloudProperties.Clear();
            cloudProperties.SetFloat(CloudsPositionId, Altitude);
            cloudProperties.SetFloat(CloudsHeightId, safeVolumeSize);

            if (overrideCloudColor && directionalLight != null)
            {
                cloudProperties.SetColor(ScatteringColorId, scatteringColorGradient.Evaluate(GetLightingTime()));
            }

            Graphics.DrawMeshInstanced(
                quadMesh,
                0,
                cloudsMaterial,
                matrices,
                sampleCount,
                cloudProperties);
        }

        private void RebuildCloudMatricesIfNeeded(int sampleCount, float safeVolumeSize)
        {
            if (cachedVolumeSamples == sampleCount &&
                Mathf.Approximately(cachedVolumeSize, safeVolumeSize) &&
                Mathf.Approximately(cachedAltitude, Altitude))
            {
                return;
            }

            // This preserves the original cloud-layer distribution so existing scenes
            // keep the same appearance and volume placement.
            float volumeOffset = safeVolumeSize / sampleCount / 2f;
            Vector3 cloudsStartPosition =
                new Vector3(0f, Altitude, 0f) + Vector3.up * (volumeOffset * sampleCount / 2f);

            Quaternion rotation = Quaternion.Euler(-90f, 0f, 0f);
            Vector3 scale = new Vector3(10000f, 10000f, 10000f);

            for (int i = 0; i < sampleCount; i++)
            {
                Vector3 position = cloudsStartPosition - Vector3.up * (volumeOffset * i);
                matrices[i] = Matrix4x4.TRS(position, rotation, scale);
            }

            cachedVolumeSamples = sampleCount;
            cachedVolumeSize = safeVolumeSize;
            cachedAltitude = Altitude;
        }

        private void UpdateLighting()
        {
            if (directionalLight == null)
            {
                return;
            }

            float time = GetLightingTime();

            if (overrideFogColor)
            {
                RenderSettings.fogColor = fogColorGradient.Evaluate(time);
            }

            if (overrideSunColor)
            {
                directionalLight.color = sunColorGradient.Evaluate(time);
            }

            if (overrideAmbientColor)
            {
                RenderSettings.ambientLight = ambientColorGradient.Evaluate(time);
            }
        }

        private float GetLightingTime()
        {
            float dot = Vector3.Dot(directionalLight.transform.forward, Vector3.up);
            return Mathf.Clamp01((dot + 1f) * 0.5f);
        }
    }
}
