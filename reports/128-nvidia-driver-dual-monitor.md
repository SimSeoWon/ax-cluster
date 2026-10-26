# 128 — 마스터(.57) NVIDIA 드라이버 복구 · 듀얼 모니터

날짜: 2026-10-23 · 사용자 승인: 「재부팅하자!」

## 증상
모니터 2대 연결, 1대만 인식.

## 진단 (실측)
- GPU GT 1030(GP108). 커널 드라이버 미사용 — 화면은 `simpledrm`(BIOS 프레임버퍼, 출력 1개)
- `nvidia-driver-530` 설치돼 있으나 모듈은 5.19.0-46 용뿐. 실행 커널 6.8.0-138 → `modinfo nvidia` not found
- nouveau 는 530 패키지가 블랙리스트 → GPU 드라이버 0

## 계획 명령 (실행 전 기록)
1. `pkexec apt-get install -y nvidia-driver-580 linux-modules-nvidia-580-generic-hwe-22.04`
   (580 = Pascal 지원 마지막 계열 · 6.8.0-138 용 사전 빌드 모듈 확인 · hwe 메타로 커널 추종)
2. `modinfo -F version nvidia` 로 6.8.0-138 모듈 존재 확인
3. `pkexec systemctl reboot`
4. 재부팅 뒤: `nvidia-smi` · `/sys/class/drm/card*-*/status` · AX 서비스 active 확인

## 복구 경로
- GUI 실패 시 SSH 는 유지. GRUB 에서 6.8.0-136 선택 가능
- 되돌리기: `apt-get purge 'nvidia-*580*'` → nouveau 블랙리스트가 같이 빠짐

## 진행 기록
- 1 완료: apt rc=0 · 오류 줄 0 · grub 재생성
- 2 완료: `modinfo -k 6.8.0-138-generic nvidia` = 580.178.04
- 3 재부팅 실행 (사용자 지시 「끝나면 바로 재부팅해」) — 이후 4 는 재부팅 뒤 기록
