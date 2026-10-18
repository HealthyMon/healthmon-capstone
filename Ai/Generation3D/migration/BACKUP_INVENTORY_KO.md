> 이전 조사 당시 상태를 보존한 문서입니다. 현재 실제 복사/보완 결과는 READY_REPORT_KO.md와 루트 README.md를 따릅니다.

# 별도 보존 대상과 복사 결과

모델 가중치는 코드 ZIP과 개인 에셋 ZIP 모두에 포함하지 않았다. 활성 모델은 공식 해시와 일치해 재다운로드 대상으로 분류했다. 직접 학습한 필수 LoRA/체크포인트는 현재 실행 경로에서 발견하지 못했다. 삭제된 과거 파일은 별도 조치가 필요하다.

| 구분 | 위치 | 조치 |
|---|---|---|
| B: 개인 커스텀 실행 코드 | 코드 패키지의 run_pipeline.py, src/, scripts/, configs/ | 원본 보존; SHA-256 manifest 제공 |
| B: 과거 실행 관련 코드 차이 | migration/source_variants/healthmon-evolution | 참고용 사본; 원래 경로·해시 조사표 포함 |
| B: 개인 입력/디자인 참조 | 별도 assets/ | 존재하는 파일 복사, 학습 가중치 없음 |
| B: numeric V1 이미지 입력 | 별도 web/fixed/assets/ | 보존된 PNG만 복사; 웹 서비스 코드 이식 아님 |
| B: 기존 결과 예시 | 별도 examples/ | 검증한 Qwen PNG와 Lucan rigged GLB 한 개; 새 추론에 필수인 checkpoint가 아님 |
| 파생 복구 자료 | healthmon_evolution_reference_pack_RECOVERED_PARTIAL.zip | 기존 파일로 만든 새 ZIP. Lucan/Tori용, Mongle 10파일 미확보 |
| A: 공식 모델 | migration/model_manifest.json | 약 47.51GB 필수 다운로드. 현재 source 가중치는 복사하지 않음 |
| 미확보 | 원본 UniRig 코드/체크포인트 및 참조 ZIP/몽글 누락 파일 | missing_reference_files.json 및 AUDIT_REPORT_KO.md 확인 |

개인 에셋의 각 파일 경로·바이트 크기·SHA-256은 별도 폴더의 BACKUP_MANIFEST.json과 코드 패키지의 reports/backup_manifest.json에 있다. 반출 허용은 사용자의 이번 대화 확인을 근거로 한다. 다른 사용자 파일은 복사하지 않았다.
