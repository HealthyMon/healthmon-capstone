plugin 사용법
1. healthmon-mobile-plugin-release.aar 생성
2. Unity의 Assets/Plugins/Android에 배치
3. Unity Application Identifier = com.healthmon.app
4. 동일한 signing key 사용
5. 필요한 Android 의존성 설정
6. HealthMonUnityBridge.initialize()
7. getPendingWorkoutResults()
8. markWorkoutConsumed()