using UnityEditor;
using UnityEngine;

namespace BKPureNature
{
    [CustomEditor(typeof(BK_EnvironmentManager))]
    public class BK_EnvironmentManagerEditor : Editor
    {
        private Editor materialEditor;

        private SerializedProperty directionalLightProp;
        private SerializedProperty sunColorGradientProp;
        private SerializedProperty fogColorGradientProp;
        private SerializedProperty scatteringColorGradientProp;
        private SerializedProperty ambientColorGradientProp;

        private SerializedProperty overrideSunColorProp;
        private SerializedProperty overrideFogColorProp;
        private SerializedProperty overrideCloudColorProp;
        private SerializedProperty overrideAmbientColorProp;

        private SerializedProperty baseWindPowerProp;
        private SerializedProperty baseWindSpeedProp;
        private SerializedProperty burstsPowerProp;
        private SerializedProperty burstsSpeedProp;
        private SerializedProperty burstsScaleProp;
        private SerializedProperty microPowerProp;
        private SerializedProperty microSpeedProp;
        private SerializedProperty microFrequencyProp;

        private SerializedProperty renderDistanceProp;

        private SerializedProperty altitudeProp;
        private SerializedProperty volumeSamplesProp;
        private SerializedProperty volumeSizeProp;
        private SerializedProperty cloudsMaterialProp;

        private GUIStyle foldoutStyle;
        private GUIStyle boxStyle;

        private bool lightingFoldout = true;
        private bool windFoldout = true;
        private bool grassFoldout = true;
        private bool cloudsFoldout = true;

        private void OnEnable()
        {
            directionalLightProp = serializedObject.FindProperty("directionalLight");
            sunColorGradientProp = serializedObject.FindProperty("sunColorGradient");
            fogColorGradientProp = serializedObject.FindProperty("fogColorGradient");
            scatteringColorGradientProp = serializedObject.FindProperty("scatteringColorGradient");
            ambientColorGradientProp = serializedObject.FindProperty("ambientColorGradient");

            overrideSunColorProp = serializedObject.FindProperty("overrideSunColor");
            overrideFogColorProp = serializedObject.FindProperty("overrideFogColor");
            overrideCloudColorProp = serializedObject.FindProperty("overrideCloudColor");
            overrideAmbientColorProp = serializedObject.FindProperty("overrideAmbientColor");

            baseWindPowerProp = serializedObject.FindProperty("baseWindPower");
            baseWindSpeedProp = serializedObject.FindProperty("baseWindSpeed");
            burstsPowerProp = serializedObject.FindProperty("burstsPower");
            burstsSpeedProp = serializedObject.FindProperty("burstsSpeed");
            burstsScaleProp = serializedObject.FindProperty("burstsScale");
            microPowerProp = serializedObject.FindProperty("microPower");
            microSpeedProp = serializedObject.FindProperty("microSpeed");
            microFrequencyProp = serializedObject.FindProperty("microFrequency");

            renderDistanceProp = serializedObject.FindProperty("renderDistance");

            altitudeProp = serializedObject.FindProperty("Altitude");
            volumeSamplesProp = serializedObject.FindProperty("volumeSamples");
            volumeSizeProp = serializedObject.FindProperty("volumeSize");
            cloudsMaterialProp = serializedObject.FindProperty("cloudsMaterial");
        }

        private void OnDisable()
        {
            if (materialEditor != null)
            {
                DestroyImmediate(materialEditor);
                materialEditor = null;
            }
        }

        public override void OnInspectorGUI()
        {
            serializedObject.Update();
            EnsureStyles();

            DrawLightingSection();
            DrawWindSection();
            DrawGrassSection();
            DrawCloudsSection();

            serializedObject.ApplyModifiedProperties();
        }

        private void EnsureStyles()
        {
            if (foldoutStyle == null)
            {
                foldoutStyle = new GUIStyle(EditorStyles.foldout)
                {
                    fontStyle = FontStyle.Bold
                };
            }

            if (boxStyle == null)
            {
                boxStyle = new GUIStyle(GUI.skin.box)
                {
                    margin = new RectOffset(2, 2, 2, 2),
                    padding = new RectOffset(5, 5, 5, 5)
                };
            }
        }

        private void DrawLightingSection()
        {
            EditorGUILayout.Space(10);
            EditorGUILayout.BeginVertical(boxStyle);

            lightingFoldout = EditorGUILayout.Foldout(
                lightingFoldout,
                "Global Lighting",
                true,
                foldoutStyle);

            if (lightingFoldout)
            {
                EditorGUILayout.PropertyField(directionalLightProp, new GUIContent("Directional Light"));

                DrawGradientRow("Sun", overrideSunColorProp, sunColorGradientProp, out _);
                DrawGradientRow("Fog", overrideFogColorProp, fogColorGradientProp, out _);
                DrawGradientRow("Clouds", overrideCloudColorProp, scatteringColorGradientProp, out Rect gradientRect);
                DrawGradientRow("Ambient", overrideAmbientColorProp, ambientColorGradientProp, out _);

                EditorGUILayout.BeginHorizontal();
                GUILayout.Space(gradientRect.x + 77f);
                GUILayout.Label("☼", GUILayout.Width(20f));
                GUILayout.FlexibleSpace();
                GUILayout.Label("☽", GUILayout.Width(20f));
                GUILayout.Space(5f);
                EditorGUILayout.EndHorizontal();
            }

            EditorGUILayout.EndVertical();
        }

        private static void DrawGradientRow(
            string label,
            SerializedProperty enabledProperty,
            SerializedProperty gradientProperty,
            out Rect gradientRect)
        {
            EditorGUILayout.BeginHorizontal();

            enabledProperty.boolValue = EditorGUILayout.ToggleLeft(
                label,
                enabledProperty.boolValue,
                GUILayout.Width(70f));

            using (new EditorGUI.DisabledScope(!enabledProperty.boolValue))
            {
                EditorGUILayout.PropertyField(gradientProperty, GUIContent.none);
            }

            gradientRect = GUILayoutUtility.GetLastRect();
            EditorGUILayout.EndHorizontal();
        }

        private void DrawWindSection()
        {
            EditorGUILayout.Space(10);
            EditorGUILayout.BeginVertical(boxStyle);

            windFoldout = EditorGUILayout.Foldout(windFoldout, "Wind", true, foldoutStyle);

            if (windFoldout)
            {
                EditorGUILayout.PropertyField(baseWindPowerProp);
                EditorGUILayout.PropertyField(baseWindSpeedProp);
                EditorGUILayout.PropertyField(burstsPowerProp);
                EditorGUILayout.PropertyField(burstsSpeedProp);
                EditorGUILayout.PropertyField(burstsScaleProp);
                EditorGUILayout.PropertyField(microPowerProp);
                EditorGUILayout.PropertyField(microSpeedProp);
                EditorGUILayout.PropertyField(microFrequencyProp);
            }

            EditorGUILayout.EndVertical();
        }

        private void DrawGrassSection()
        {
            EditorGUILayout.Space(10);
            EditorGUILayout.BeginVertical(boxStyle);

            grassFoldout = EditorGUILayout.Foldout(grassFoldout, "Grass", true, foldoutStyle);

            if (grassFoldout)
            {
                EditorGUILayout.PropertyField(renderDistanceProp);
            }

            EditorGUILayout.EndVertical();
        }

        private void DrawCloudsSection()
        {
            EditorGUILayout.Space(10);
            EditorGUILayout.BeginVertical(boxStyle);

            cloudsFoldout = EditorGUILayout.Foldout(cloudsFoldout, "Clouds", true, foldoutStyle);

            if (cloudsFoldout)
            {
                EditorGUILayout.PropertyField(altitudeProp);
                EditorGUILayout.PropertyField(volumeSamplesProp);
                EditorGUILayout.PropertyField(volumeSizeProp);
                EditorGUILayout.PropertyField(cloudsMaterialProp);

                EditorGUILayout.Space(10);

                Material material = cloudsMaterialProp.objectReferenceValue as Material;
                if (material != null)
                {
                    Editor.CreateCachedEditor(material, null, ref materialEditor);
                    materialEditor.DrawHeader();
                    materialEditor.OnInspectorGUI();
                }
                else if (materialEditor != null)
                {
                    DestroyImmediate(materialEditor);
                    materialEditor = null;
                }
            }

            EditorGUILayout.EndVertical();
        }
    }
}
