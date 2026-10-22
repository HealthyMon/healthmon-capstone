# Android / Unity workout integration

The watch keeps its existing Data Layer, Room, ACK and live-message behavior. Only the
phone plugin uploads completed summaries. No direct watch-to-API or permanent live
heart-rate upload is added.

## Package and signing compatibility

The existing watch application ID and phone Java namespace remain `com.healthmon.app`
and `com.healthmon.app.mobile`. The bridge is
`com.healthmon.app.mobile.unity.HealthMonUnityBridge`. Data Layer requires the watch
and phone **application IDs and signing certificate** to match.

The develop Unity project currently defaults to `com.healthmon.capstone`, while the
develop watch defaults to `com.healthmon.app`. These defaults cannot pair as installed.
Choose a coordinated test build configuration before installing either app. An existing
`com.healthmon.app` watch needs a phone test build with that application ID and matching
signing certificate. Moving the watch to `com.healthmon.capstone` is a separate package
and requires an explicit migration/install decision. This implementation does not
reinstall apps, change their IDs, or migrate their private data automatically.

PR #10 source audit: `team/feature/unity` at `e1ccf94`, compared with
`team/develop` at `8ac8555`. The histories have two merge bases (`0765093`, `3d2fb1a`).
All 94 comparable Wearable text files were compared after normalizing only the
`com.healthmon.app` / `com.healthmon.capstone` rename. Remaining differences were an
unused `Color` import and documentation whitespace. The unused import cleanup was
applied; package/action/Manifest renames were deliberately not applied because they
change installed-app identity. Existing measurement, ACK and live-message behavior
was already present in develop.

## Runtime settings and explicit ownership

Call `initialize(context)` when the phone app starts. It schedules recovery independently
of `consumedByUnity`. Existing `getPendingWorkoutResults()`, `markWorkoutConsumed()`,
`getLatestLiveWorkoutState()` and `requestLiveWorkoutState()` stay available.

New static bridge calls (invoke potentially blocking calls on a background thread):

```text
configureServerSync(baseUrl, bearerToken, petId) -> JSON status and verified identity
clearServerSync() -> boolean                  // logout; cancels queued work
requestServerSync() -> boolean                // manual pending-work recovery
getServerSyncStatus() -> JSON
confirmWorkoutUpload(workoutId) -> boolean    // only after explicit per-record confirmation
```

Configuration fetches `/server-info`, `/identity` and the authorized pet state. Runtime
credentials are encrypted with Android Keystore AES-GCM; no bearer is returned in
status, placed in WorkManager input, or written to logs/Unity scenes. HTTPS is required
for release builds. HTTP development requires a debuggable host and an explicit host
debug network policy; certificate validation is never bypassed. Redirects are refused.
Concurrent logout/reconfiguration invalidates the pending configure attempt so a late
network response cannot restore the old credentials.

The existing watch summary has no authenticated owner or pet at exercise start.
Consequently **all unbound summaries wait for explicit per-record confirmation**,
including newly received records. Login alone never claims a backlog. The panel must
show record ID, exercise and start/end time before calling `confirmWorkoutUpload`.
Once bound, a record cannot move to another owner. Changing the address for the same
server instance retains the binding. A different server DB has a different instance ID;
the same owner may explicitly confirm a separate destination binding, whose sync
success starts independently. Account IDs changed by a data migration require an
explicit administrator migration procedure; the client does not infer equivalence.

Status JSON:

```json
{
  "status": "ready",
  "server_instance_id": "server UUID",
  "owner_id": "authenticated owner UUID",
  "pet_id": "selected pet UUID",
  "environment": "development",
  "unbound_count": 1,
  "unbound": [{"id":"watch ID","exercise":"RUNNING","start_time":1000,"end_time":1801000}],
  "uploads": [{"workout_id":"bound ID","status":"pending","last_http_status":null,"synced_at":null}]
}
```

Top-level statuses also include `not_configured`, `auth_required`, `server_changed`,
`identity_changed`, `error` and `configuration_superseded`. Upload states are `pending`,
`auth_required`, `needs_correction`, `synced`. Previous accounts' bindings are not listed.
The status response never contains credentials.

## Upload contract and durability

Room database `healthmon_phone.db` upgrades from version 1 to 2 with an additive
`workout_upload` table. The existing `workout` table and `consumedByUnity` values are
preserved. There is no destructive migration fallback. A binding is keyed by workout,
server instance, owner and pet. Its original workout ID is the stable server `event_id`.

Room commit precedes WorkManager scheduling. Startup, receipt, configuration, explicit
confirmation and manual sync all schedule recovery. WorkManager uses CONNECTED and
exponential backoff (initial 30 seconds), and scans durable pending rows. A crash between
Room commit and enqueue recovers at next app initialization/manual sync. A confirmed
pending binding survives process/device restart. Unbound rows remain for confirmation.

Only a 2xx JSON response with matching `event_id`, `revision:1`, `stored:true`, and an
`evaluation_status` marks `synced_at`. The server emits that response after commit.
Network/malformed success/408/429/5xx retry. A 401 waits for fresh runtime credentials,
and a 409/422 or other permanent 4xx becomes `needs_correction` without retry loops.
The app exposes correction state; correcting the original source is an explicit action,
not a fabricated measurement or automatic revision. Watch summaries remain unchanged.

```json
{
  "event_id":"original watch workout ID",
  "revision":1,
  "occurred_at":"2026-10-22T03:30:00Z",
  "started_at":"2026-10-22T03:00:00Z",
  "workout_type":"run",
  "actual":30.0,
  "unit":"minutes",
  "target":null,
  "source":"watch",
  "synthetic":false
}
```

`occurred_at` is exercise completion, `started_at` is used by the server for the saved
goal effective at start. Run/cycle/stretch duration converts seconds to minutes. Walking
uses steps only when the watch marks that metric supported; missing and measured zero
stay distinct. The existing schema has no repetition count: squat/lunge/pushup/dumbbell
send `actual:null`, never duration-derived repetitions. Targets remain null for server
goal lookup. The watch's actual `GYMNASTICS` category remains `gymnastics`, with measured
minutes and no saved goal; it is recorded unscored, never relabelled as stretching.
Calories, distance and heart rate are not summed into exercise amount.
Source is an accepted watch report, not a cryptographically verified sensor assertion.

## Build and verification

From `Wearable/Android/HealthMonWatch` (Windows `gradlew.bat`, Linux `./gradlew`):

```text
gradlew.bat :healthmon-mobile-plugin:testDebugUnitTest :healthmon-mobile-plugin:assembleRelease :healthmon-mobile-plugin:assembleDebugAndroidTest
```

The checked-in wrapper is Gradle 9.6.0 and requests JDK 25. Android SDK 36 is required.
Do not commit `local.properties`, machine SDK paths, signing keys or Gradle caches.
Copy the built release AAR into `Wearable/Android/Artifacts` and Unity
`Assets/Plugins/Android`, preserving the existing Unity `.meta`. The artifact provenance
file records exact source and AAR hashes. A plain AAR does not bundle Maven dependencies.
Unity's template must include existing wearable 18.0.0, Room3 3.0.3, SQLite framework 2.7.1,
coroutines-play-services 1.10.2, core/core-ktx 1.17.0, plus **work-runtime-ktx 2.11.2**.
Existing appcompat/material runtime requirements remain unchanged.

After the successful Gradle build, `python scripts/plugin_artifact.py export` copies
the release artifact and records its exact source hashes. Before release, run
`python scripts/plugin_artifact.py verify --unity ../../../Client/HealthMonUnity/Assets/Plugins/Android/healthmon-mobile-plugin-release.aar`.
Verification fails if either the plugin sources or either AAR copy changes.

Host JVM tests use actual loopback HTTP for the bearer/redirect/ack contract and pure
metric/retry policy tests. Android instrumentation uses disposable test databases and
the separate test package `com.healthmon.app.mobile.test`. Run it on a selected test
emulator/device, not an existing user's production app:

```text
adb -s TEST_EMULATOR install -r healthmon-mobile-plugin/build/outputs/apk/androidTest/debug/healthmon-mobile-plugin-debug-androidTest.apk
adb -s TEST_EMULATOR shell am instrument -w -r com.healthmon.app.mobile.test/androidx.test.runner.AndroidJUnitRunner
```
