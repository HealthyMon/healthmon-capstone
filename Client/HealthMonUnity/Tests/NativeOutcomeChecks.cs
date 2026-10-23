using System;
using System.Reflection;
using System.Runtime.Serialization;
using UnityEngine;

// Pure final-result policy. No native Editor APIs or license are used here.
public static class NativeOutcomeChecks
{
    private static int checks;
    private static void Check(bool condition, string name)
    { checks++; if (!condition) throw new Exception(name); }

    public static int Main()
    {
        var clean = new NativeE2EReport { status = "passed" };
        clean.ApplyRuntimeErrorPolicy();
        Check(clean.status == "passed" && clean.error_code == null && clean.assertions == 1,
            "A clean automated run changed outcome.");
        var runtime = new NativeE2EReport { status = "passed", runtime_error_count = 2 };
        runtime.ApplyRuntimeErrorPolicy();
        Check(runtime.status == "failed" && runtime.error_code == "native_runtime_errors_detected" && runtime.runtime_error_count == 2,
            "Native runtime errors did not fail an otherwise passed run.");
        var earlier = new NativeE2EReport { status = "failed", error_code = "production_api_http_503", runtime_error_count = 1 };
        earlier.ApplyRuntimeErrorPolicy();
        Check(earlier.status == "failed" && earlier.error_code == "production_api_http_503" && earlier.runtime_error_count == 1,
            "The first failure evidence was overwritten.");
        var visual = new NativeE2EReport { status = "passed", manual_visual_review_required = true,
            model_renderability_cases = 1, cases = new[] { new NativeE2ECaseResult {
                model_renderability_verified = true, manual_visual_review_required = true,
                placement_is_simulated = true, physical_ar_tracking = false } } };
        visual.ApplyRuntimeErrorPolicy();
        Check(visual.status == "passed" && visual.manual_visual_review_required && visual.cases[0].manual_visual_review_required &&
            visual.cases[0].model_renderability_verified && !visual.cases[0].physical_ar_tracking,
            "Automated renderability was confused with physical AR or manual visual approval.");
        var frames = new NativeRenderStabilityGate();
        frames.ObserveFrame(10, false, true);
        frames.ObserveFrame(10, false, true);
        Check(frames.CameraFrames == 1 && frames.StableFrames == 1 && !frames.Ready, "Duplicate callbacks were counted as separate camera frames.");
        frames.ObserveFrame(11, true, true);
        Check(frames.StableFrames == 0 && frames.ShaderPendingCameraFrames == 1 && !frames.Ready, "Compiling cyan placeholder frame was treated as stable.");
        frames.ObserveFrame(12, false, true); frames.ObserveFrame(13, false, true);
        Check(!frames.Ready && frames.StableFrames == 2, "Fewer than three actual stable camera frames passed.");
        frames.ObserveShaderPending(true);
        Check(frames.StableFrames == 0 && !frames.Ready && frames.ShaderPendingObservations == 2, "Shader work between camera callbacks did not reset stability.");
        frames.ObserveFrame(14, false, true); frames.ObserveFrame(15, false, true); frames.ObserveFrame(16, false, true);
        Check(frames.Ready && frames.StableFrames == 3, "Three stable compiled camera frames failed to qualify.");
        frames.ObserveFrame(17, false, false);
        Check(!frames.Ready && frames.StableFrames == 0, "An invisible or unrenderable frame did not reset stability.");
        var runner = (CommonServerNativeE2ERunner)FormatterServices.GetUninitializedObject(typeof(CommonServerNativeE2ERunner));
        var runnerType = typeof(CommonServerNativeE2ERunner);
        var flags = BindingFlags.Instance | BindingFlags.NonPublic;
        var authReport = new NativeE2EReport();
        var authCase = new NativeE2ECaseResult();
        runnerType.GetField("report", flags).SetValue(runner, authReport);
        runnerType.GetField("current", flags).SetValue(runner, authCase);
        var phase = runnerType.GetField("expectedAuth401Phase", flags);
        var failure = runnerType.GetField("productionFailure", flags);
        var observed = runnerType.GetMethod("ProductionApiFailed", flags);
        phase.SetValue(runner, "initial_chat");
        observed.Invoke(runner, new object[] { new Healthmon.Beta.ApiFailure(401, "expected isolated test rejection") });
        Check(failure.GetValue(runner) == null && authReport.expected_auth_401_observations == 1 && authCase.auth_expected_401_observations == 1,
            "An expected auth-smoke 401 was treated as an unrelated production failure.");
        observed.Invoke(runner, new object[] { new Healthmon.Beta.ApiFailure(403, "unexpected failure") });
        Check(((Healthmon.Beta.ApiFailure)failure.GetValue(runner)).StatusCode == 403 && authReport.expected_auth_401_observations == 1,
            "Auth smoke incorrectly suppressed an unexpected HTTP failure.");
        phase.SetValue(runner, null);
        observed.Invoke(runner, new object[] { new Healthmon.Beta.ApiFailure(401, "unexpected outside smoke") });
        Check(((Healthmon.Beta.ApiFailure)failure.GetValue(runner)).StatusCode == 401 && authReport.expected_auth_401_observations == 1,
            "A 401 outside the intentional auth-smoke phase was ignored.");
        authReport.auth_recovery_cases = 1; authReport.status = "passed"; authReport.ApplyRuntimeErrorPolicy();
        Check(authReport.status == "passed" && authReport.real_llm_cases == 0, "Server-rule authentication smoke was counted as real LLM validation.");
        foreach (var size in new[] { new Vector2(1920, 1080), new Vector2(1080, 1920), new Vector2(1280, 720), new Vector2(720, 1280), new Vector2(320, 640) })
            foreach (bool longText in new[] { false, true })
            {
                var plan = DialogueLayoutPlan.Calculate(size.x, size.y, 175, size.y - 90,
                    Math.Min(650, size.x - 60), Math.Min(760, size.x - 60), longText ? 5000 : 80, longText ? 6000 : 120);
                Check(plan.Valid && plan.User.width > 0 && plan.Response.height > 0, "Portrait/landscape dialogue has no valid geometry.");
                var nav = new Rect(25, 25, size.x - 50, 150);
                Check(!plan.User.Overlaps(plan.Response) && !plan.User.Overlaps(plan.Input) && !plan.Response.Overlaps(plan.Input) &&
                    !nav.Overlaps(plan.User) && !nav.Overlaps(plan.Response) && !nav.Overlaps(plan.Input),
                    "Long dialogue or input overlaps another control/navigation.");
                Check(plan.User.yMax <= size.y - 90 && plan.Response.yMin > plan.Input.yMax &&
                    plan.Input.xMin >= 0 && plan.Input.xMax <= size.x && plan.User.xMin >= 0 && plan.User.xMax <= size.x,
                    "Runtime dialogue is placed outside the available panel bounds.");
            }
        Check(!DialogueLayoutPlan.Calculate(0, 10, 175, 0, 1, 1, 100, 100).Valid,
            "An impossible viewport was marked safe to display.");
        var uiOnly = new NativeE2EReport { status = "passed", dialogue_layout_smoke_cases = 1, manual_visual_review_required = true,
            cases = new[] { new NativeE2ECaseResult { dialogue_layout_synthetic = true, dialogue_layout_smoke_verified = true } } };
        uiOnly.ApplyRuntimeErrorPolicy();
        Check(uiOnly.real_llm_cases == 0 && uiOnly.cases[0].dialogue_layout_synthetic && uiOnly.manual_visual_review_required,
            "Synthetic UI-only geometry was counted as real LLM or automatic pixel-quality approval.");
        var isolatedCase = new NativeE2ECase { case_id = "ui-only", pet_id = "fixture-pet", run_chat = false, run_dialogue_layout_smoke = true,
            expected_state = new Healthmon.Beta.PetState { pet_id = "fixture-pet", rule_version = "healthmon.v2.2", asset_status = "none",
                level = 1, required_exp = 100, upper_body = 50, lower_body = 50, nutrition = 50, activity = 50, affinity = 50, initiative = 50 } };
        var isolatedConfig = new NativeE2EConfig { isolated_fixture = true, api_base_url = "https://fixture.invalid",
            expected_server_instance_id = "isolated-server", expected_owner_id = "isolated-owner", cases = new[] { isolatedCase } };
        CommonServerNativeVerification.ValidateConfig(isolatedConfig);
        Check(isolatedCase.run_dialogue_layout_smoke && !isolatedCase.run_chat, "UI-only verification did not accept its isolated non-chat case.");
        isolatedCase.run_chat = true; isolatedCase.prompt = "fictional fixture prompt";
        bool mixedRejected = false;
        try { CommonServerNativeVerification.ValidateConfig(isolatedConfig); } catch (InvalidOperationException) { mixedRejected = true; }
        Check(mixedRejected, "Synthetic UI text could replace a real LLM test case.");
        Check(!NativeDialogueViewportEvidence.RequiresScrolling(500, 600) && !NativeDialogueViewportEvidence.RequiresScrolling(600, 600) &&
            !NativeDialogueViewportEvidence.RequiresScrolling(600.25f, 600), "Fitting or subpixel-rounded text incorrectly requires overflow.");
        Check(NativeDialogueViewportEvidence.RequiresScrolling(601, 600), "Actual text overflow did not require scrolling.");
        var fitting = new NativeDialogueViewportEvidence { content_height = 500, viewport_height = 600, fits_viewport = true,
            first_glyph_within_viewport = true, last_glyph_within_viewport = true, all_glyphs_within_viewport = true };
        Check(fitting.ReadabilityVerified(), "A fully visible portrait response failed because scrolling was unnecessary.");
        fitting.scroll_performed = true;
        Check(!fitting.ReadabilityVerified(), "Fitting text falsely claimed actual scrolling."); fitting.scroll_performed = false;
        fitting.first_glyph_within_viewport = false;
        Check(!fitting.ReadabilityVerified(), "A clipped first glyph in fitting text passed."); fitting.first_glyph_within_viewport = true;
        fitting.all_glyphs_within_viewport = false;
        Check(!fitting.ReadabilityVerified(), "Clipped intermediate glyphs in fitting text passed.");
        var overflow = new NativeDialogueViewportEvidence { content_height = 1200, viewport_height = 600, scroll_required = true,
            scroll_performed = true, last_glyph_within_viewport = true, vertical_normalized_position = 0 };
        Check(overflow.ReadabilityVerified(), "A scrolled long response required its offscreen first glyph to remain visible.");
        overflow.last_glyph_within_viewport = false;
        Check(!overflow.ReadabilityVerified(), "Overflow passed without a readable final glyph.");
        bool invalidViewportRejected = false;
        try { NativeDialogueViewportEvidence.RequiresScrolling(500, 0); } catch (ArgumentException) { invalidViewportRejected = true; }
        Check(invalidViewportRejected, "An invalid zero viewport was marked readable.");
        var syntheticText = runnerType.GetMethod("SyntheticUiText", BindingFlags.Static | BindingFlags.NonPublic);
        foreach (int length in new[] { 1500, 500 })
        {
            string text = (string)syntheticText.Invoke(null, new object[] { length });
            Check(text.Length == length && text.StartsWith("[합성 UI 검증 · 서버 미전송]") && text.EndsWith("[UI 끝]"),
                "UI-only text lost its exact length or visible synthetic/end markers.");
            Check(text.Contains("[001]") && text.Contains("[002]") && !text.Contains("[000]"),
                "Numbered UI-only text cannot distinguish actual scrolling movement.");
        }
        isolatedCase.run_chat = false; isolatedCase.run_dialogue_layout_smoke = false; isolatedCase.run_food_smoke = true;
        isolatedCase.food_image_path = "explicit-existing-fixture.jpg";
        CommonServerNativeVerification.ValidateConfig(isolatedConfig);
        Check(isolatedCase.run_food_smoke && !isolatedCase.run_chat && isolatedCase.food_require_real_vision,
            "Food smoke did not preserve its separate real-Vision/non-chat contract.");
        isolatedCase.run_chat = true;
        mixedRejected = false;
        try { CommonServerNativeVerification.ValidateConfig(isolatedConfig); } catch (InvalidOperationException) { mixedRejected = true; }
        Check(mixedRejected, "Synthetic consumption fixture was combined with real LLM quality validation.");
        isolatedCase.run_chat = false; isolatedCase.food_image_path = "";
        bool missingPhotoRejected = false;
        try { CommonServerNativeVerification.ValidateConfig(isolatedConfig); } catch (InvalidOperationException) { missingPhotoRejected = true; }
        Check(missingPhotoRejected, "Food smoke accepted an unspecified source photo.");
        isolatedCase.food_image_path = "explicit-existing-fixture.jpg"; isolatedCase.food_fixture_grams = 0;
        bool invalidFoodRejected = false;
        try { CommonServerNativeVerification.ValidateConfig(isolatedConfig); } catch (ArgumentException) { invalidFoodRejected = true; }
        Check(invalidFoodRejected, "Food smoke silently fabricated a valid consumed amount from zero.");
        var foodOnly = new NativeE2EReport { status = "passed", food_smoke_cases = 1, real_vision_cases = 1,
            cases = new[] { new NativeE2ECaseResult { food_smoke_verified = true, food_synthetic_consumption = true, food_real_vision_contract = true } } };
        Check(foodOnly.real_llm_cases == 0 && foodOnly.cases[0].food_synthetic_consumption && foodOnly.cases[0].food_real_vision_contract,
            "Real analysis and synthetic tester-entered consumption were conflated with LLM validation.");
        isolatedCase.run_food_smoke = false; isolatedCase.require_model_display = true;
        isolatedCase.expected_state.asset_status = "ready";
        isolatedCase.expected_state.model_reference = "/pets/fixture-pet/assets/starter-verified";
        CommonServerNativeVerification.ValidateConfig(isolatedConfig);
        Check(isolatedCase.expected_state.published_model_stage == 0 && isolatedCase.require_model_display,
            "An authenticated published starter could not enter actual native model verification.");
        isolatedCase.expected_state.model_reference = null;
        bool missingStarterRejected = false;
        try { CommonServerNativeVerification.ValidateConfig(isolatedConfig); } catch (InvalidOperationException) { missingStarterRejected = true; }
        Check(missingStarterRejected, "A stage0 placeholder without a server asset passed model verification setup.");
        Console.WriteLine("HEALTHMON_NATIVE_OUTCOME_POLICY_PASS checks=" + checks);
        return 0;
    }
}
