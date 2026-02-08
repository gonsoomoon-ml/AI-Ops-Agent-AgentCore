# Distribution Portal에서 펌웨어 배포 Workflow 세부 설명

> 펌웨어 배포 Workflow, Workflow, SW PL, 빌드 권한, 배포 대상 지역, QA 권한, OTA 서버, 24시간 이내, 검증된 펌웨어, 정상 동작, 배포 포털

## 관련 질문
- 펌웨어 배포 Workflow 알려줘
- 펌웨어 배포 Workflow에 대해 설명해줘
- 펌웨어 배포 Workflow가 뭐야?
- 펌웨어 배포 Workflow 뭐야?
- Workflow이 뭐야?
- Workflow 설명해줘
- 펌웨어 배포 Workflow(Workflow) 설명해줘
- 펌웨어 배포 Workflow(Workflow)가 무엇인가요

## 답변

Distribution Portal에서의 냉장고 펌웨어 배포 운영은 크게 두 단계로 나뉩니다. 1. 개발팀에서 검증된 펌웨어 버전을 서버를 통해 배포할지 여부를 판단하는 단계 (Release) - SW PL 2. 배포된 펌웨어를 QA 테스트를 통해 확정하는 단계 (Confirm or Reject) - QA 이 과정을 거쳐 최종적으로 사용자에게 OTA 업데이트가 제공됩니다. **Release 단계 (by SW PL)** 1. 해당 모델 빌드 권한을 가진 SW PL이 Home > Version > Firmware Version > Version Workflow List에 접속합니다. 2. Version Workflow List에서 Release할 버전을 선택하여 Detail 페이지로 진입합니다. 3. 배포 대상 지역과 모델을 선택합니다. 4. Release 버튼을 눌러 Release를 진행합니다. **Confirm/Reject 단계 (by QA)** 1. QA 권한을 가진 담당자가 QA Test 제품으로 해당 펌웨어의 테스트를 완료합니다. 2. 정상 동작 확인 시 Confirm, 비정상 동작 확인 시 Reject를 진행합니다. 3. Confirm된 펌웨어는 24시간 이내에 OTA 서버에 반영되어 사용자에게 배포됩니다.

## 핵심 키워드
Confirm, Confirm or Reject, Detail, Distribution, Distribution Portal, Firmware, Firmware Version, Home, OTA, Reject, Release, Test, Version, Version Workflow List, Workflow, by QA, by SW PL, SW PL, 빌드 권한, 배포 단계
