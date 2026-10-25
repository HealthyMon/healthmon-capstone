Shader "BK/Sky"
{
    Properties
    {
        [Header(Sun)]
        _SunSize("Sun Size", Range(0, 1)) = 0
        _SunSizeConvergence("Sun Size Convergence", Range(1, 10)) = 10

        [Header(Day)]
        _AtmosphereThickness("Atmosphere Thickness", Range(0, 5)) = 1
        _SkyTint("Day Sky Tint", Color) = (0, 0.298039, 0.576471, 1)
        _GroundColor("Day Ground Color", Color) = (0.611765, 0.792157, 1, 1)

        [Header(Night)]
        _NightSkyColor("Night Sky Color", Color) = (0, 0.388235, 0.643137, 1)
        _NightGroundColor("Night Ground Color", Color) = (0.184314, 0.356863, 0.529412, 1)
        _NightTransition("Night Transition", Range(0.01, 0.5)) = 0.5

        [Header(Stars)]
        _StarDensity("Star Density", Range(8, 512)) = 512
        _StarSize("Star Size", Range(0, 1)) = 0
        _StarIntensity("Star Intensity", Range(0, 10)) = 10
        _StarColorVariation("Star Color Variation", Range(0, 1)) = 1

        _StarHorizonFade("Star Horizon Fade", Range(0, 0.5)) = 0.1

        _StarRotationOffset("Star Rotation Offset", Range(-180, 180)) = 0
        _SunOrbitYaw("Sun Orbit Yaw", Range(-180, 180)) = 0

        [HideInInspector]
        [Toggle]
        _UseStarRotationMatrix("Use Script Star Rotation", Float) = 0

        [Header(General)]
        _Exposure("Exposure", Range(0, 8)) = 1
    }

    SubShader
    {
        Tags
        {
            "Queue" = "Background"
            "RenderType" = "Background"
            "PreviewType" = "Skybox"
            "RenderPipeline" = "UniversalPipeline"
        }

        Cull Off
        ZWrite Off

        Pass
        {
            CGPROGRAM

            #pragma target 3.0
            #pragma vertex Vert
            #pragma fragment Frag

            #include "UnityCG.cginc"
            #include "Lighting.cginc"

            #define BK_PI 3.14159265359
            #define BK_TWO_PI 6.28318530718

            half _Exposure;

            half _SunSize;
            half _SunSizeConvergence;
            half _AtmosphereThickness;

            half3 _SkyTint;
            half3 _GroundColor;

            half3 _NightSkyColor;
            half3 _NightGroundColor;
            half _NightTransition;

            half _StarDensity;
            float _StarSize;
            half _StarIntensity;
            half _StarColorVariation;
            half _StarHorizonFade;
            float _StarRotationOffset;
            float _SunOrbitYaw;

            float4x4 _StarRotation;
            float _UseStarRotationMatrix;

            #if defined(UNITY_COLORSPACE_GAMMA)
                #define BK_COLOR_TO_LINEAR(value) ((value) * (value))
                #define BK_LINEAR_TO_OUTPUT(value) sqrt(max(value, 0.0))
                #define BK_COLOR_TO_GAMMA(value) (value)
            #else
                #define BK_COLOR_TO_LINEAR(value) (value)
                #define BK_LINEAR_TO_OUTPUT(value) (value)
                #define BK_COLOR_TO_GAMMA(value) \
                    ((unity_ColorSpaceDouble.r > 2.0) \
                    ? pow(value, 1.0 / 2.2) \
                    : value)
            #endif

            static const float3 BK_DefaultWavelength =
                float3(0.65, 0.57, 0.475);

            static const float3 BK_WavelengthRange =
                float3(0.15, 0.15, 0.15);

            static const float BK_OuterRadius = 1.025;
            static const float BK_OuterRadiusSquared = 1.050625;

            static const float BK_InnerRadius = 1.0;
            static const float BK_InnerRadiusSquared = 1.0;

            static const float BK_CameraHeight = 0.0001;

            static const float BK_MieConstant = 0.001;
            static const float BK_SunBrightness = 20.0;
            static const float BK_MaxScatter = 50.0;

            static const float BK_Scale = 40.0;
            static const float BK_ScaleDepth = 0.25;
            static const float BK_ScaleOverDepth = 160.0;

            static const float BK_MieSun =
                BK_MieConstant * BK_SunBrightness;

            static const float BK_MieFourPi =
                BK_MieConstant * 4.0 * BK_PI;

            static const half BK_HighQualitySunIntensity = 15.0;

            #define BK_MIE_G (-0.990)
            #define BK_MIE_G_SQUARED 0.9801
            #define BK_SKY_GROUND_THRESHOLD 0.02

            struct AppData
            {
                float4 vertex : POSITION;

                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Interpolators
            {
                float4 position : SV_POSITION;

                float3 ray : TEXCOORD0;

                half3 groundColor : TEXCOORD1;
                half3 skyColor : TEXCOORD2;
                half3 sunColor : TEXCOORD3;

                UNITY_VERTEX_OUTPUT_STEREO
            };

            float AtmosphereScale(float angleCosine)
            {
                float x = 1.0 - angleCosine;

                return 0.25 * exp(
                    -0.00287 +
                    x * (
                        0.459 +
                        x * (
                            3.83 +
                            x * (
                                -6.80 +
                                x * 5.25
                            )
                        )
                    )
                );
            }

            half RayleighPhase(half cosineSquared)
            {
                return 0.75 + 0.75 * cosineSquared;
            }

            half RayleighPhase(half3 lightDirection, half3 rayDirection)
            {
                half cosine = dot(lightDirection, rayDirection);

                return RayleighPhase(cosine * cosine);
            }

            float Hash12(float2 value)
            {
                float3 p = frac(
                    float3(value.x, value.y, value.x) * 0.1031
                );

                p += dot(p, p.yzx + 33.33);

                return frac((p.x + p.y) * p.z);
            }

            float2 Hash22(float2 value)
            {
                float3 p = frac(
                    float3(value.x, value.y, value.x) *
                    float3(0.1031, 0.1030, 0.0973)
                );

                p += dot(p, p.yzx + 33.33);

                return frac(
                    (p.xx + p.yz) * p.zy
                );
            }

            float2 DirectionToEqualAreaUV(float3 direction)
            {
                direction = normalize(direction);

                float longitude =
                    atan2(direction.z, direction.y) /
                    BK_TWO_PI +
                    0.5;

                float axisHeight =
                    direction.x * 0.5 +
                    0.5;

                return float2(
                    longitude,
                    axisHeight
                );
            }

            float3 EqualAreaUVToDirection(float2 uv)
            {
                uv.x = frac(uv.x);

                float x = clamp(
                    uv.y * 2.0 - 1.0,
                    -1.0,
                    1.0
                );

                float longitude =
                    (uv.x - 0.5) *
                    BK_TWO_PI;

                float radius = sqrt(
                    max(
                        1.0 - x * x,
                        0.0
                    )
                );

                float sine;
                float cosine;

                sincos(
                    longitude,
                    sine,
                    cosine
                );

                return float3(
                    x,
                    cosine * radius,
                    sine * radius
                );
            }

            float3 RotateAroundX(float3 direction, float angle)
            {
                float sine;
                float cosine;

                sincos(
                    angle,
                    sine,
                    cosine
                );

                return float3(
                    direction.x,
                    direction.y * cosine -
                    direction.z * sine,
                    direction.y * sine +
                    direction.z * cosine
                );
            }

            float3 GetRotatedStarDirection(
                float3 viewDirection,
                float3 sunDirection
            )
            {
                if (_UseStarRotationMatrix > 0.5)
                {
                    return normalize(
                        mul(
                            (float3x3)_StarRotation,
                            viewDirection
                        )
                    );
                }

                float yaw =
                    radians(_SunOrbitYaw);

                float yawSine;
                float yawCosine;

                sincos(
                    yaw,
                    yawSine,
                    yawCosine
                );

                float3 sunWithoutYaw = float3(
                    sunDirection.x * yawCosine -
                    sunDirection.z * yawSine,

                    sunDirection.y,

                    sunDirection.x * yawSine +
                    sunDirection.z * yawCosine
                );

                float orbitAngle = atan2(
                    sunWithoutYaw.y,
                    -sunWithoutYaw.z
                );

                float starAngle =
                    -orbitAngle +
                    radians(_StarRotationOffset);

                return normalize(
                    RotateAroundX(
                        viewDirection,
                        starAngle
                    )
                );
            }

            float3 GetRandomStarColor(float seed)
            {
                float3 neutral =
                    float3(1.0, 0.96, 0.88);

                float3 randomColor;

                if (seed < 0.18)
                {
                    randomColor =
                        float3(0.15, 0.32, 1.0);
                }
                else if (seed < 0.38)
                {
                    randomColor =
                        float3(0.30, 0.65, 1.0);
                }
                else if (seed < 0.58)
                {
                    randomColor =
                        float3(1.0, 0.90, 0.48);
                }
                else if (seed < 0.78)
                {
                    randomColor =
                        float3(1.0, 0.52, 0.15);
                }
                else if (seed < 0.92)
                {
                    randomColor =
                        float3(1.0, 0.22, 0.10);
                }
                else
                {
                    randomColor =
                        float3(0.62, 0.15, 1.0);
                }

                float variation =
                    saturate(_StarColorVariation);

                variation =
                    1.0 -
                    (1.0 - variation) *
                    (1.0 - variation);

                return lerp(
                    neutral,
                    randomColor,
                    variation
                );
            }

            float3 ProceduralStars(float3 direction)
            {
                direction = normalize(direction);

                float densityValue = saturate(
                    (_StarDensity - 8.0) /
                    (512.0 - 8.0)
                );

                float verticalCells = floor(
                    lerp(
                        28.0,
                        180.0,
                        densityValue
                    ) +
                    0.5
                );

                float horizontalCells =
                    verticalCells * 2.0;

                float2 gridSize = float2(
                    horizontalCells,
                    verticalCells
                );

                float2 uv =
                    DirectionToEqualAreaUV(direction);

                float2 gridPosition =
                    uv * gridSize;

                float2 baseCell =
                    floor(gridPosition);

                float baseProbability = lerp(
                    0.09,
                    0.045,
                    densityValue
                );

                float probability =
                    saturate(baseProbability);

                float pixelAngularSize = max(
                    length(fwidth(direction)),
                    0.000001
                );

                float antialiasWidth =
                    pixelAngularSize * 0.65;

                float3 result =
                    float3(0.0, 0.0, 0.0);

                [unroll]
                for (int y = -1; y <= 1; y++)
                {
                    [unroll]
                    for (int x = -2; x <= 2; x++)
                    {
                        float2 rawCell =
                            baseCell +
                            float2(x, y);

                        float validY =
                            step(0.0, rawCell.y) *
                            step(
                                rawCell.y,
                                verticalCells - 1.0
                            );

                        float wrappedX =
                            rawCell.x -
                            floor(
                                rawCell.x /
                                horizontalCells
                            ) *
                            horizontalCells;

                        float2 cell = float2(
                            wrappedX,
                            clamp(
                                rawCell.y,
                                0.0,
                                verticalCells - 1.0
                            )
                        );

                        float randomExistence =
                            Hash12(
                                cell +
                                19.17
                            );

                        float exists =
                            step(
                                randomExistence,
                                probability
                            ) *
                            validY;

                        float2 randomPosition =
                            Hash22(
                                cell +
                                5.71
                            );

                        float2 starUV =
                            (cell + randomPosition) /
                            gridSize;

                        float3 starDirection =
                            EqualAreaUVToDirection(
                                starUV
                            );

                        float sizeRandom =
                            Hash12(
                                cell +
                                73.41
                            );

                        float radius =
                            lerp(
                                0.0001,
                                0.001,
                                saturate(_StarSize)
                            ) *
                            lerp(
                                0.45,
                                1.65,
                                sizeRandom
                            );

                        float distanceToStar =
                            length(
                                direction -
                                starDirection
                            );

                        float star = 1.0 - smoothstep(
                            max(
                                radius -
                                antialiasWidth,
                                0.0
                            ),
                            radius +
                            antialiasWidth,
                            distanceToStar
                        );

                        float brightnessRandom =
                            Hash12(
                                cell +
                                41.81
                            );

                        float brightness = lerp(
                            0.25,
                            1.65,
                            pow(
                                brightnessRandom,
                                4.0
                            )
                        );

                        float colorSeed =
                            Hash12(
                                cell +
                                97.23
                            );

                        result +=
                            GetRandomStarColor(colorSeed) *
                            star *
                            exists *
                            brightness;
                    }
                }

                return result;
            }

            Interpolators Vert(AppData input)
            {
                Interpolators output;

                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);

                output.position =
                    UnityObjectToClipPos(input.vertex);

                float3 sunDirection =
                    normalize(_WorldSpaceLightPos0.xyz);

                float3 tintGamma =
                    BK_COLOR_TO_GAMMA(_SkyTint);

                float3 wavelength = lerp(
                    BK_DefaultWavelength -
                    BK_WavelengthRange,

                    BK_DefaultWavelength +
                    BK_WavelengthRange,

                    float3(1.0, 1.0, 1.0) -
                    tintGamma
                );

                float3 inverseWavelength =
                    1.0 /
                    pow(wavelength, 4.0);

                float rayleighConstant = lerp(
                    0.0,
                    0.0025,
                    pow(
                        _AtmosphereThickness,
                        2.5
                    )
                );

                float rayleighSun =
                    rayleighConstant *
                    BK_SunBrightness;

                float rayleighFourPi =
                    rayleighConstant *
                    4.0 *
                    BK_PI;

                float3 cameraPosition = float3(
                    0.0,
                    BK_InnerRadius +
                    BK_CameraHeight,
                    0.0
                );

                float3 eyeRay = normalize(
                    mul(
                        (float3x3)unity_ObjectToWorld,
                        input.vertex.xyz
                    )
                );

                float3 incomingScatter;
                float3 outgoingScatter;

                if (eyeRay.y >= 0.0)
                {
                    float atmosphereDistance =
                        sqrt(
                            BK_OuterRadiusSquared +
                            BK_InnerRadiusSquared *
                            eyeRay.y *
                            eyeRay.y -
                            BK_InnerRadiusSquared
                        ) -
                        BK_InnerRadius *
                        eyeRay.y;

                    float cameraRadius =
                        BK_InnerRadius +
                        BK_CameraHeight;

                    float startDepth = exp(
                        BK_ScaleOverDepth *
                        -BK_CameraHeight
                    );

                    float startAngle =
                        dot(
                            eyeRay,
                            cameraPosition
                        ) /
                        cameraRadius;

                    float startOffset =
                        startDepth *
                        AtmosphereScale(startAngle);

                    float sampleLength =
                        atmosphereDistance * 0.5;

                    float scaledLength =
                        sampleLength *
                        BK_Scale;

                    float3 sampleRay =
                        eyeRay *
                        sampleLength;

                    float3 samplePosition =
                        cameraPosition +
                        sampleRay * 0.5;

                    float3 frontColor =
                        float3(0.0, 0.0, 0.0);

                    [unroll]
                    for (int sampleIndex = 0;
                         sampleIndex < 2;
                         sampleIndex++)
                    {
                        float sampleHeight =
                            length(samplePosition);

                        float sampleDepth = exp(
                            BK_ScaleOverDepth *
                            (
                                BK_InnerRadius -
                                sampleHeight
                            )
                        );

                        float lightAngle =
                            dot(
                                sunDirection,
                                samplePosition
                            ) /
                            sampleHeight;

                        float cameraAngle =
                            dot(
                                eyeRay,
                                samplePosition
                            ) /
                            sampleHeight;

                        float scatter =
                            startOffset +
                            sampleDepth *
                            (
                                AtmosphereScale(lightAngle) -
                                AtmosphereScale(cameraAngle)
                            );

                        float3 attenuation = exp(
                            -clamp(
                                scatter,
                                0.0,
                                BK_MaxScatter
                            ) *
                            (
                                inverseWavelength *
                                rayleighFourPi +
                                BK_MieFourPi
                            )
                        );

                        frontColor +=
                            attenuation *
                            sampleDepth *
                            scaledLength;

                        samplePosition +=
                            sampleRay;
                    }

                    incomingScatter =
                        frontColor *
                        inverseWavelength *
                        rayleighSun;

                    outgoingScatter =
                        frontColor *
                        BK_MieSun;
                }
                else
                {
                    float groundDistance =
                        -BK_CameraHeight /
                        min(
                            -0.001,
                            eyeRay.y
                        );

                    float3 groundPosition =
                        cameraPosition +
                        groundDistance *
                        eyeRay;

                    float depth = exp(
                        -BK_CameraHeight /
                        BK_ScaleDepth
                    );

                    float cameraAngle =
                        dot(
                            -eyeRay,
                            groundPosition
                        );

                    float lightAngle =
                        dot(
                            sunDirection,
                            groundPosition
                        );

                    float cameraScale =
                        AtmosphereScale(cameraAngle);

                    float lightScale =
                        AtmosphereScale(lightAngle);

                    float cameraOffset =
                        depth *
                        cameraScale;

                    float angleSum =
                        lightScale +
                        cameraScale;

                    float sampleLength =
                        groundDistance * 0.5;

                    float scaledLength =
                        sampleLength *
                        BK_Scale;

                    float3 sampleRay =
                        eyeRay *
                        sampleLength;

                    float3 samplePosition =
                        cameraPosition +
                        sampleRay * 0.5;

                    float sampleHeight =
                        length(samplePosition);

                    float sampleDepth = exp(
                        BK_ScaleOverDepth *
                        (
                            BK_InnerRadius -
                            sampleHeight
                        )
                    );

                    float scatter =
                        sampleDepth *
                        angleSum -
                        cameraOffset;

                    float3 attenuation = exp(
                        -clamp(
                            scatter,
                            0.0,
                            BK_MaxScatter
                        ) *
                        (
                            inverseWavelength *
                            rayleighFourPi +
                            BK_MieFourPi
                        )
                    );

                    float3 frontColor =
                        attenuation *
                        sampleDepth *
                        scaledLength;

                    incomingScatter =
                        frontColor *
                        (
                            inverseWavelength *
                            rayleighSun +
                            BK_MieSun
                        );

                    outgoingScatter =
                        saturate(attenuation);
                }

                output.ray =
                    -eyeRay;

                output.groundColor =
                    _Exposure *
                    (
                        incomingScatter +
                        BK_COLOR_TO_LINEAR(
                            _GroundColor
                        ) *
                        outgoingScatter
                    );

                output.skyColor =
                    _Exposure *
                    (
                        incomingScatter *
                        RayleighPhase(
                            sunDirection,
                            -eyeRay
                        )
                    );

                half lightIntensity = clamp(
                    length(_LightColor0.xyz),
                    0.25,
                    1.0
                );

                output.sunColor =
                    BK_HighQualitySunIntensity *
                    saturate(
                        outgoingScatter
                    ) *
                    _LightColor0.xyz /
                    lightIntensity;

                return output;
            }

            half MiePhase(
                half cosine,
                half cosineSquared
            )
            {
                half denominator =
                    1.0 +
                    BK_MIE_G_SQUARED -
                    2.0 *
                    BK_MIE_G *
                    cosine;

                denominator = pow(
                    denominator,
                    pow(
                        _SunSize,
                        0.65
                    ) *
                    10.0
                );

                denominator =
                    max(
                        denominator,
                        0.0001
                    );

                return
                    1.5 *
                    (
                        (1.0 - BK_MIE_G_SQUARED) /
                        (2.0 + BK_MIE_G_SQUARED)
                    ) *
                    (
                        1.0 +
                        cosineSquared
                    ) /
                    denominator;
            }

            half SunAttenuation(
                half3 lightDirection,
                half3 viewDirection
            )
            {
                half focusedCosine = pow(
                    saturate(
                        dot(
                            lightDirection,
                            viewDirection
                        )
                    ),
                    _SunSizeConvergence
                );

                return MiePhase(
                    -focusedCosine,
                    focusedCosine *
                    focusedCosine
                );
            }

            half4 Frag(Interpolators input) : SV_Target
            {
                half3 inverseViewRay =
                    normalize(input.ray);

                half3 viewDirection =
                    -inverseViewRay;

                half skyGroundFactor =
                    inverseViewRay.y /
                    BK_SKY_GROUND_THRESHOLD;

                half3 color = lerp(
                    input.skyColor,
                    input.groundColor,
                    saturate(
                        skyGroundFactor
                    )
                );

                if (skyGroundFactor < 0.0)
                {
                    color +=
                        input.sunColor *
                        SunAttenuation(
                            normalize(
                                _WorldSpaceLightPos0.xyz
                            ),
                            viewDirection
                        );
                }

                float3 sunDirection =
                    normalize(
                        _WorldSpaceLightPos0.xyz
                    );

                half nightAmount =
                    1.0 -
                    smoothstep(
                        -max(
                            _NightTransition,
                            0.001
                        ),
                        0.05,
                        sunDirection.y
                    );

                half3 nightColor =
                    _Exposure *
                    lerp(
                        BK_COLOR_TO_LINEAR(
                            _NightSkyColor
                        ),
                        BK_COLOR_TO_LINEAR(
                            _NightGroundColor
                        ),
                        saturate(
                            skyGroundFactor
                        )
                    );

                color = lerp(
                    color,
                    nightColor,
                    nightAmount
                );

                half starVisibility =
                    smoothstep(
                        0.35,
                        0.95,
                        nightAmount
                    );

                half horizonVisibility =
                    smoothstep(
                        _StarHorizonFade,
                        _StarHorizonFade +
                        0.16,
                        viewDirection.y
                    );

                float3 starDirection =
                    GetRotatedStarDirection(
                        viewDirection,
                        sunDirection
                    );

                float3 stars =
                    ProceduralStars(
                        starDirection
                    );

                color +=
                    stars *
                    starVisibility *
                    horizonVisibility *
                    max(
                        _StarIntensity,
                        0.0
                    ) *
                    max(
                        _Exposure,
                        0.0
                    );

                color =
                    BK_LINEAR_TO_OUTPUT(color);

                return half4(
                    color,
                    1.0
                );
            }

            ENDCG
        }
    }

    Fallback Off
}
