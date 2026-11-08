---
name: manage-domain
description: 요청자에서 자기 프로젝트의 도메인 씨앗 생성·필드 편집·온톨로지 항목 수정과 삭제·로그 태그 관리·개명 계획을 마스터에 요청한다. "새 도메인 생성", "서브도메인 만들어줘", "도메인 협력관계 수정", "이 액션/불변조건 내용 고쳐줘", "이 항목 삭제해줘", "도메인 이름 바꿔줘", "로그 태그 등록"에 사용한다. 전체 도메인 삭제와 멤버 추가·제거는 현재 요청자 도구에서 지원하지 않는다.
---

# Manage Domain — 도메인 CRUD 통합 관리

## 목차

- 개요
- 사용 예
- 목적
- 환경 확인 (필수, BLOCKING)
- 호출 방법
- 흐름
- 안전 가드

## 개요

요청자는 프로젝트 체크아웃의 `ax-client`로 관리하고, 마스터가 실제 온톨로지를 처리한다.
관리 요청은 체크아웃의 프로젝트 태그·요청자 토큰으로 인증된 8101을 거친다.
프로젝트가 마운트와 다르거나 권한이 없으면 사유를 알리고 멈춘다. 다른 프로젝트나 로컬
인덱스로 우회하지 않는다. 요청자 PC에 마스터의 온톨로지 DB·패키지가 있다고 가정하지 않는다.

## 사용 예

    「새 도메인 생성」
    「서브도메인 만들어줘」
    「도메인 협력관계 수정」
    「이 액션 설명 틀렸어 고쳐줘」
    「이 불변조건 지워줘」
    「도메인 이름 바꿔줘」
    「이 도메인 로그 태그 등록해줘」

구획은 위 목차의 제목으로 찾아 읽는다 — 절차는 「목적」부터다.

## 목적

마스터의 기존 기능과 실제 도구 인자에 맞춰 도메인·항목을 관리한다. 생성은 씨앗 MD,
필드 편집은 MD와 해당 manifest 필드, 항목 편집·삭제는 기존 YAML을 대상으로 한다.
한 번의 호출이 모든 DB·검색 인덱스·소스를 함께 갱신한다고 가정하지 않는다.
반환된 변경 목록·잠금·노트·인덱스 결과를 확인해 실제 반영 범위를 보고한다.

## 환경 확인 (필수, BLOCKING)

1. 현재 체크아웃의 `ax-client` 도구가 연결됐는지 확인한다.
2. `ax-client:list_domains()`로 도메인 목록을 읽고, 대상은 `ax-client:get_domain(name)`이나
   `ax-client:get_domain_layer(domain, layer=0)`로 확인한다.
3. 응답의 프로젝트·거절 사유·`_stale`을 확인한다. 낡은 조회 결과로 변경 대상을 확정하지 않는다.
   호출 실패는 사유와 함께 보고한다. 요청자 토큰이나 마스터 API 키를 출력하지 않는다.

## 호출 방법

- `/manage-domain list` — `ax-client:list_domains()`로 목록 확인.
- `/manage-domain create <Name>` — `ax-client:create_domain(name, tags=[], parent="", summary="")`.
- `/manage-domain edit <D>` — `ax-client:edit_domain_field(domain, parent_domain?, status?, tags?, collaborates_with?, summary?)`.
- `/manage-domain edit-item <D> <kind> <name>` — `ax-client:edit_ontology_item(domain, kind, name, patch)`.
- `/manage-domain remove-item <D> <kind> <name>` — `ax-client:remove_ontology_item(domain, kind, name, force=False)`.
- `/manage-domain rename <old> <new>` — `ax-client:rename_domain(old, new, apply=False)`로 계획.
- `/manage-domain rename-class <D> <old> <new>` — `ax-client:rename_class(domain, old, new, apply=False)`로 계획.
- `/manage-domain edit-session start|commit|discard|status <D>` — 아래 편집 세션의 반영 범위를 먼저 설명한다.
- `/manage-domain log-tags <D> list|set|remove` — 아래 로그 태그 도구를 사용한다.

전체 도메인 삭제, 도메인 멤버 추가·제거는 현재 마스터에 대응하는 실행 코어·요청자 도구가 없다.
해당 요청을 받으면 미지원 사실을 알리고 별도 구현 여부를 사용자에게 묻는다. 항목 삭제나
필드 변경을 이 기능의 대체로 실행하지 않는다.

## 흐름

### 제거 (remove)

전체 도메인 제거는 현재 지원하지 않는다. 도메인 MD·패키지·DB·색인을 일괄 지우는 것으로
안내하거나 파일을 직접 삭제하지 않는다. 기존 항목 하나의 삭제는 아래 `remove-item`이다.

### 수정 (edit)

1. 현재 도메인과 바꿀 필드를 읽어 사용자에게 보여준다.
2. 사용자가 확정한 필드만 `ax-client:edit_domain_field`에 보낸다. 생략하거나 null인 필드는 유지된다.
   `parent_domain`, `status`, `tags`, `collaborates_with`, `summary`를 지원한다.
3. `tags`와 `collaborates_with`는 전체 목록 치환이다. 기존 목록을 먼저 확인하고 최종 목록을
   합의한다. `kr_tags_removed`·`warning`이 반환되면 그대로 알린다.
4. `parent_domain`·`tags`·`collaborates_with`는 기존 manifest가 있으면 직접 패치하고 도메인
   인덱스를 갱신한다. `summary`·`status`는 MD 반영이며 다음 합성까지 패키지와 다를 수 있다.
   `manifest_patched`·`index_note`·`note`를 읽고 전 표면 반영 완료로 확대하지 않는다.

멤버 추가·제거는 지원하지 않는다. 소스 선언·도메인 책임·현재 멤버를 근거로 편입 여부를
사용자와 논의할 수는 있으나, 확정됐다는 이유로 없는 도구를 호출하거나 YAML을 임의 생성하지 않는다.

### 항목 편집 (edit-item / remove-item / edit-session)

`kind`는 `objects`·`actions`·`invariants` 중 하나다. 계층 번호와 구분한다.

- 편집: 현재 항목과 변경할 값을 보여주고 확정 후 `ax-client:edit_ontology_item(domain, kind,
  name, patch)`를 호출한다. top-level 얕은 병합이므로 중첩 값은 키 전체를 보낸다.
  `name`·`layer`는 패치로 바꿀 수 없다. 편집은 `verified_by_user: true` 잠금을 건다.
- 별칭: `ax-client:add_object_alias(class_name, term)`을 쓴다. 확인된 표현만 보내고 기존 별칭과
  병합한다. 별칭만 붙이는 일을 전체 항목 검수로 처리하거나 `aliases` 전체를 패치하지 않는다.
- 삭제: 내용을 먼저 보여주고 사용자 확정 후 `ax-client:remove_ontology_item(domain, kind,
  name, force=False)`를 호출한다. 검수 잠금으로 거절되면 보존된 것이다. `force=True`는
  잠긴 항목을 지운다는 점을 별도로 확인받은 뒤에만 쓴다.
- 잠금 확인·변경: `ax-client:list_locked(domain)`와
  `ax-client:lock_ontology_item(domain, kind, name, locked)`를 쓴다. 잠금 해제 후 다음 합성은
  그 항목을 덮을 수 있음을 설명한다.

편집 세션은 다음 도구를 제공한다.

    ax-client:staging_begin(domain)     패키지 사본 생성, 기존 사본이면 재개
    ax-client:staging_status(domain="") 세션 상태 조회, 빈 값이면 전체
    ax-client:staging_commit(domain)    사본으로 라이브 교체, 기존 라이브는 1세대 백업
    ax-client:staging_discard(domain)   사본 폐기

[중요] 세션이 있으면 위 **항목 편집·삭제·잠금 변경은 staging 사본에 반영**된다.
응답의 `domain`·`staging`을 확인한다. `ax-client:list_locked`도 작업 사본을 우선 조회하며
항목별 `staging`을 반환한다. 일반 도메인 조회·검색과 로그 태그 조회·동기화 계획은 라이브를
읽으므로 commit 전에는 사본 변경이 보이지 않는다. 편집 결과와 라이브 조회가 다르다고
세션 밖에 같은 수정을 다시 실행하지 않는다.

세션 중 해당 도메인의 필드 편집·로그 태그 등록/삭제·동기화 적용은 거절된다.
프로젝트에 열린 세션이 하나라도 있으면 별칭 등록과 도메인·클래스 개명도 거절된다.
상위 도메인에 세션이 열려 있으면 그 아래 씨앗 생성도 거절된다. 사유를 알리고 현재 사본의
변경을 검토한 뒤 commit/discard를 사용자와 결정한다. 자동으로 세션을 만들거나 교체·폐기하지 않는다.

commit은 사본으로 라이브를 교체하고 색인을 한 번 갱신한다. 결과의
`live_changed_during_session`·`index`를 확인한다. 다른 경로에서 세션 중 라이브가 바뀌어도
core는 경고만 반환하고 교체할 수 있으므로, 변경 감지가 교체를 자동 차단한다고 안내하지 않는다.

### 실증 테스트용 로그 태그/CVar 사이드카 (log-tags)

게임 코드에 실제 태깅 로그·CVar가 구현된 뒤 사람이 확인한 이름을 등록한다.

    ax-client:list_log_tags(domain)
    ax-client:set_log_tag(domain, tag, cvar, related_invariants?)
    ax-client:remove_log_tag(domain, tag)

`set`은 tag 기준 등록·갱신이다. 실제 구현과 관련 불변식을 확인하고 값을 합의한다.
`related_invariants`를 생략하거나 null로 보내면 기존 연결을 유지하고, 빈 목록은 연결을 지운다.
삭제는 현재 내용을 보여주고 확정받는다. 제안 리포트나 추측을 실제 구현으로 간주해 자동 등록하지 않는다.

### 개명 (rename)

1. `ax-client:rename_domain(old, new, apply=False)`로 현재 파일 이동·참조 변경 계획을 받는다.
2. 오류·충돌과 계획의 `moves`·`edits`·`notes`를 사용자에게 보여주고 백업 및 적용을 확인받는다.
3. 승인 후 같은 인자로 `apply=True`를 보낸다. 서버가 현재 상태로 계획을 다시 만들어 적용한다.
   예전 응답의 임의 파일 경로를 적용 인자로 보내지 않는다.

현재 코어는 패키지 이동과 MD·manifest 등의 참조를 갱신한다. 잠금·보호 표식은 이동한
파일에 남는다. 모든 DB·인덱스의 일괄 갱신을 보증하지 않는다. 반환 계획에 없는 변경을
수행했다고 보고하지 않는다. 개명 코어는 새 이름을 정규화하고 비ASCII를 거절하므로 계획의
실제 `new`를 확인받는다. 이는 아래 씨앗 생성의 한글 이름 허용과 다른 계약이다.

### 클래스 개명·이동 (rename-class)

`ax-client:rename_class(domain, old, new, apply=False)`로 지정 도메인의 YAML 참조 치환·항목 파일
개명 계획을 확인한다. 사용자 승인 후 `apply=True`로 적용한다. 현재 도구는 `new_path`를 받지
않고 소스 클래스를 개명·이동하지 않는다. DB 전체 cascade나 force-full 재합성을 수행한다고
안내하지 않는다. 계획의 변경 범위·정규화된 새 이름·충돌 사유를 먼저 확인한다.

### 생성 (create)

`ax-client:create_domain(name, tags=[], parent="", summary="")`는 **status=draft인 씨앗 MD**를 만든다.
이미 있는 MD는 덮지 않는다. 이름은 한글도 허용하며 경로 위험문자·공백은 거절한다.
상위는 `parent`로 지정하고 그 상위 MD가 먼저 있어야 한다. 패키지가 아직 없으면 계층 연결은
보류될 수 있으므로 `linked`·`notes`를 읽는다.

이 도구에는 `members`·`parent_domain`·`collaborates_with`·`status` 인자를 보내지 않는다.
생성만으로 객체·행위 패키지나 멤버 분류가 생기지 않는다. 씨앗의 도메인 경계·책임을 합의해
채우는 일과 이후 합성을 별도로 구분한다. 필드 수정은 위 `edit`의 지원 범위를 따른다.

## 안전 가드

- 생성·등록·편집·삭제·적용은 사용자가 확인한 대상과 값에 한정한다. 자동 편입·자동 승급은 없다.
- 삭제·개명·staging 교체는 현재 내용과 실제 변경 계획을 먼저 보여주고 확정받는다.
- 항목 삭제의 `force`·동기화의 적용은 기본 계획·거절을 건너뛰는 재시도 수단이 아니다.
- 요청자 도구의 스키마에 없는 인자를 추측하지 않는다. 없는 기능은 미지원으로 알린다.
- 결과의 거절·보존·경고·인덱스 실패를 성공으로 요약하지 않는다. 토큰·API 키는 출력하지 않는다.
