---
name: ax-deliver
description: AX 마스터의 현재 커밋을 워커(작업장)에 배포·검사한다 — `master.client update`(마운트된 프로젝트) · `update --all`(등록 전체) · 프로젝트 하나만 `deliver`/`check`. "워커에 배포해", "배달해", "동기화해", "업데이트 돌려", "워커 맞춰", "check 해봐", "/ax-deliver" 같은 발화에 발동. Claude·Codex 공용.
---

# ax-deliver — 워커 배포(배달)

## 목차

- 개요
- 0. 무엇을 하는가
- 1. 실행 전
- 2. 고르는 명령
- 3. 결과 보고
- 4. 하지 않는 것

## 개요

> 정본: `~/ax-cluster/master/skills/ax-deliver/SKILL.md` · 명령 정본 `master/client/__main__.py`
> 근거: `#655`·`#745`(마운트만 기본) · `#737`(실행 중 HEAD·dirty 감지) · `#699`(체크아웃 로컬 Codex 자산)
> 세부: `docs/8-git-authority.md` §8.4 · `docs/14-onboarding-runbook.md`

## 0. 무엇을 하는가

마스터 HEAD 의 배달물(`.ax/config.json`·스킬·MCP·체크아웃의 `.agents/skills`·`.codex/config.toml`)을
각 작업장에 쓰고, 되읽어 정본과 대조한다. **명령이 일을 하고, 이 스킬은 언제·어떻게를 정한다.**

## 1. 실행 전

**배포는 사용자 지시가 있을 때만 돌린다** (`CLAUDE.md` 「빌드·배포·데몬 재기동도 같다」 · `docs/11` §11.5).
커밋 직후라도 스스로 돌리지 않고, 「배포할까요?」로 묻는다.

작업 위치 `/home/sim/ax-cluster`, Python 은 `.venv/bin/python`. 실행 전 쓸 명령을 사용자에게 알린다.

    git status --short          비어 있어야 한다
    git log --oneline -1        배달될 HEAD

- **dirty 면 먼저 말하고 멈춘다.** 명령은 dirty 여도 경고만 하고 계속하지만, 그 배달 도장은
  `delivered_by.dirty=true`(추적 불가)로 찍히고 `check` 가 실패한다. 커밋은 사용자 승인 사항이다.
- **실행 중에는 마스터에 커밋하거나 작업 트리를 고치지 않는다** — HEAD·dirty 가 움직이면 검사가 실패한다.

## 2. 고르는 명령

    기본 (커밋 뒤 매번)
      AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.client update
        마운트된 프로젝트의 작업장만 배달 → 전부 배달한 뒤 전부 검사

    사용자가 「전부」·「모든 프로젝트」를 말했을 때만
      ... -m master.client update --all

    특정 프로젝트 하나 (프로젝트 인자 필수 — 폴백 없다)
      ... -m master.client plan    <프로젝트>    쓸 내용만 본다
      ... -m master.client deliver <프로젝트>
      ... -m master.client check   <프로젝트>    배달 상태만 대조 (쓰지 않는다)

- **비마운트 프로젝트를 맞추려고 `update --all` 이나 `deliver <그것>` 을 임의로 고르지 않는다.**
  비마운트는 마운트 전환(`set_active`, 기본 `align=True`) 때 뒤처진 기계만 다시 배달된다.
  어느 쪽인지 애매하면 묻는다.
- 신규 체크아웃 초기화(`--init`)는 온보딩 런북 절차다 — 이 스킬로 임의 실행하지 않는다.

## 3. 결과 보고

- rc 와 요약 줄을 그대로 전한다. 프로젝트·기계별 PASS/FAIL 분모를 말한다(「됐다」만 말하지 않는다).
- `rc=2` 마운트 비어 있음 · `rc=1` 레지스트리 문제/배달·검사 실패.
- 출력에 「HEAD 가 움직였다」·「dirty 해졌다」가 있으면 그 탓인 실패를 따로 말한다.
- **실패는 고치는 자리가 아니라 보고하는 자리다.** 원인은 조사해도 코드·설정·원격 파일을 손으로
  고치지 않는다. 사유와 갈래(재실행 · 커밋 후 재실행 · 기계 접근 확인 등)를 내고 멈춘다.
- [주의] 배달·검사 통과는 **파일이 정본과 같다**는 뜻이다. 서비스 재기동·워커 로그인·실제 파견
  성공은 별개이며, 배달만으로 그것들이 됐다고 말하지 않는다.

## 4. 하지 않는 것

- 워커에 파일을 손으로 복사·수정하지 않는다 — `config.json` 은 마스터가 생성한다.
- 마스터 서비스 재기동은 이 스킬의 범위가 아니다(필요하면 따로 말하고 승인받는다).
- 커밋·push 를 이 스킬이 하지 않는다.
