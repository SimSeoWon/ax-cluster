# 17. 부분 무효화 이식 — 변경분만 다시 만든다 (2026-08-15)

> 마일스톤 4 · 대 3 미이식 자산 재검토·이식 · **중 3.2 결정적 온톨로지 장치**
> (`#151`) — 소 3.2.2 (`#153`) 완료 · 소 3.2.1 (`#152`) 재범위.
> 원전: `watcher/ontology_invalidation.py` 190줄 (Phase η.7.2/.3, 2026-05-31).

## §1 세션 시작 상태 (실측)

    세 클론        fa67c83 동일 · 작업트리 청결 (마스터 · Gitea · .43)
    유닛 7종       HTTP 3 + ax-indexer.path + timer 3 — 전부 active
    기계           .43 ✅ · .2 ✅ · .33 ✅ (지난 세션엔 꺼져 있었다)
    레드마인 M4    36/78 (version *마일스톤 4* = id 3)

**다음 작업은 사용자가 골랐다** — 후보 넷의 **입력 실재 여부를 먼저 재서** 함께 냈고
(`#153` LLM 0·입력 실재 / `#152` 태그 0건 / `#187` 도메인 15개만큼 LLM 비용 / 중 3.3 입력 0건),
사용자가 `#153` 을 지정했다.

## §2 착수 전 대조 — 무엇이 이미 있고 무엇이 없나

능력 단위로 맞췄다(이름 대조는 양방향으로 틀린다 — 마일스톤 4 함정).

| 원전 능력 | 우리 상태 |
|---|---|
| `changed_member_classes` (저장 `source_commit` ≠ 문서 `source_commit`) | ✅ **이미 있다** — `ontology/stale.py` 가 같은 판정식 |
| `L*/{actions,invariants}/*.yaml` 레이아웃 | ✅ 동일 |
| `write_domain_yaml(cleanup_stale=False)` 머지 모드 | ✅ `package.write(prune=False)` 로 있다 (⚠️ 결함 하나 — §5) |
| `determine_invalidation` · `plan_domain_refresh` | 🔴 **없다** |
| manifest `md_hash` 스탬프 | 🔴 **안 찍는다** (7개 중 3개 보유 = 전부 스냅샷 유산) |
| `_refresh_one_domain(changed_classes=set)` partial 분기 | 🔴 **없다** (full 만) |

🔴 **판정식을 다시 구현하지 않았다.** 원전 `changed_member_classes` 와 우리 `stale.compute`
는 같은 식이다. 두 벌을 두면 언젠가 갈라지고, 그때 어느 쪽이 맞는지 아무도 모른다.

## §3 🔴 신호원을 안 찍으면 판정기는 영원히 full 을 고른다

`plan_domain_refresh` 의 full 폴백 조건은 *"manifest `md_hash` 부재 또는 도메인 MD 변경"* 이다.
실측:

    md_hash 보유         7개 도메인 중 3개 — 🔴 전부 **받아온 스냅샷**이 찍은 것
    그중 현재 MD 와 일치   1개 (UiManagement) · 불일치 2개
    우리 package.write    🔴 **한 번도 안 찍었다**

즉 판정기만 옮기면 **모든 도메인이 영구히 full** 이다. 원전은 같은 사이클에서
`write_domain_yaml` 이 `md_hash` 를 찍게 했으므로(`ontology_yaml_dump.py:276`) 그 스탬프도
같은 커밋에 넣었다 — 마일스톤 4 의 *"가드를 만들면 깨울 주체를 같은 커밋에"* 와 같은 결이다.

⚠️ **해시식이 원전과 같은지 먼저 쟀다.** `UiManagement` 의 스냅샷 `md_hash` 와 우리
`domain_md.content_hash` 가 **같은 값**(`51bbaedc41ffa531`)이다. 달랐으면 안 바뀐 도메인을
*"MD 변경"* 으로 읽어 부분 갱신이 통째로 죽는다 — 조용히.

## §4 🔴 반사실 실측 — 원전 그대로 옮겼으면 스냅샷 37건이 지워졌다

원전 partial 은 무효화 yaml 을 **선삭제**한다. 우리 항목 82건을 실제로 판정해 보니:

| 도메인 | 변경 클래스 | 원전대로면 선삭제 |
|---|---|---|
| GlobalEventSystem | 1/9 | 1건 |
| MissionEditor | 3/13 | 6건 |
| MissionRuntime | 3/11 | 11건 |
| UiManagement | 8/9 | 19건 |
| | | 🔴 **합계 37건** |

**그 37건은 전부 `protected` 스냅샷이다.** `protected` 는 원전에 없는 **우리 개념**이고
(리포트 11 §20 — 우리 합성이 스냅샷보다 **얕았다**), 삭제하면 `package.write` 의
`locked_items()` 가 디스크에서 그것을 못 읽어 **잠금 보존 기제 자체가 무력화**된다.

→ **잠긴·보호 항목은 무효화 대상에서 뺀다**(`preserved` 로 센다). ⚠️ 이것은 「안 옮기는
판단」이 아니라 **기제는 그대로 옮기고 우리 잠금 규약을 끼워 넣은 것**이다.

**원전과 다르게 둔 것 하나 더**: 무효화 파일 삭제를 **추출 전 → 쓰기 직전**으로 옮겼다.
LLM 이 통째로 실패하면 원전은 대체물 없이 지워진 상태로 끝난다. 성공했을 때의 최종 상태는
같고 실패했을 때만 다르다 — 우리 규약(*"실패는 결과로 돌려준다"*)과 맞는 방향이다.

## §5 ⚠️ 이식이 옆 함수의 결함을 드러냈다 — `prune=False` 가 manifest 를 잃고 있었다

`package.write(prune=False)` 는 이번에 안 들어온 항목 **파일은 남기면서 manifest 목록은
이번 것만으로 다시 썼다.** 그러면 파일은 있는데 **색인에는 없다** — manifest 는 스스로
*"DB 인덱싱 단일 SSOT"* 라고 적어 둔 자리다. 부분 갱신이 그 인자를 처음 실제로 쓰면서 드러났다.
→ `prune=False` 일 때 디스크를 훑어 합친다(원전도 `cleanup_stale=False` 에서 디렉토리를 walk 한다).

🔴 **이 인자는 지금까지 아무도 쓰지 않았다** — 실 사용자가 생기기 전까지 결함이 조용했다는
뜻이고, 「주입은 계약을 재고 실물을 재지 않는다」의 사촌이다.

## §6 이식분과 배선 (같은 커밋 — `#123` 의 재발 방지)

    master/ontology/invalidate.py      신규 — 원전 190줄. 설계 결정 셋 그대로
                                       (scope=변경∪응집 · 보수적 무효화 · MD 해시 변경시 full)
    ontology/domain_md.content_hash    MD 원문 md5[:16] — 🔴 파서가 아니라 **원문**을 잰다
                                       (파서가 모르는 절의 변경이 해시에 안 잡히면 오판한다)
    ontology/package.write             md_hash 스탬프 + prune=False 의 manifest 보존
    ontology/synth.refresh_domain      `changed_classes=` partial 분기 (원전 `_refresh_one_domain`)
    ontology/synth.run                 stale walk 가 도메인별로 full/partial 을 정한다.
                                       🔴 사람이 도메인을 명시하면 **언제나 full** (원전 force 경로)
    ontology/__main__ status           판정과 **사유**를 사전에 보여 준다 (LLM 0 · 부작용 0)

🔴 **`#123` 은 이식이 아니라 배선이 없어서 한 마일스톤 내내 죽어 있었다.** 같은 실수를
반복하지 않으려고 판정기·스탬프·호출자·CLI 표면을 한 번에 넣었다.

## §7 실 구동 (LLM 0 — 판정만 돌렸다)

    ■ GlobalEventSystem → full (이유: 도메인 MD 변경 4d0e8d06≠17b3c0db)   변경 1 · 보존 16
    ■ MissionEditor     → full (이유: 도메인 MD 변경 8900e6da≠80cb6638)   변경 3 · 보존 22
    ■ MissionRuntime    → full (이유: manifest md_hash 부재/레거시)        변경 3 · 보존 22
    ■ UiManagement      → 🔵 partial (변경 8건: AMSHUD · UMSHUDWidget …)  변경 8 · 보존 22

🔴 **지금 데이터에서 무효화는 0 이다** — 항목 82건이 **전부 잠금·보호**라서다. 그래서 현재의
부분 갱신 이득은 **추출 scope 축소뿐**이고, 판정 출력이 그 사실을 그대로 말한다.
⚠️ **이 값을 「이식이 무의미하다」로 읽으면 틀린다** — 셋은 md_hash 가 없거나 낡아서 full 인
것이고, **이제 우리가 그 값을 찍으므로 다음 full 재합성부터 partial 이 걸린다**(원전의
레거시 폴백과 같은 성질: eventually-consistent).

## §8 테스트

    신규   master/test_invalidate.py   42/42  (원전 tests/test_eta_7_partial.py 16건 대응 +
                                              우리 것 둘: 잠금 보존 · prune=False manifest 보존)
    전체   2626 → **2668/2668 · 실패 파일 0개**

## §9 레드마인

    #153  소 3.2.2  → **완료** (이식·배선·실측 노트)
    #152  소 3.2.1  🔴 **재범위** — `@ms-contract` 태그가 미러 소스에 **0건**. 지금 이식하면
                    「입력 없는 배치」다. 전제가 바뀌면 되살린다 — **닫지 않는다**
    #194  중 3.7    한글 베이스 **머지 지점 8** 추가 — 무효화 언급 판정이 영문 식별자 토큰
                    전용이라 한글 별칭으로만 가리킨 yaml 은 무효화되지 않는다 (지금은 실해 0)

    M4  36/78 → **37/78**

## 남은 것

- 🔴 **`source_commit` 을 아무도 다시 안 찍는다 — stale 이 settle 되지 않는다.** 원전은
  재합성이 오브젝트의 `source_commit` 을 갱신해 **스스로 가라앉게**(self-settling) 했는데
  (η.7.2 제안 2), 우리에겐 그 스탬프가 **없다.** 실측: `stale._stored` 가 보는 곳은
  `class_ontology.source_commit` **하나뿐**인데 그 표는 **0행**이고 🔴 **INSERT/UPDATE 하는
  코드가 저장소에 0건**이다(스키마만 있다 — `#189` 에서 확인한 *"옮겼지만 안 쓴다"* 와 같은 자리).
  즉 `stored` 는 영원히 `-1` 이라, 컨텍스트 MD 에 실 리비전이 있는 멤버는 **재합성을 몇 번
  돌려도 계속 stale** 이다(그래서 지금 4 도메인이 stale 로 보인다).
  ⚠️ 이것은 이번 이식이 만든 문제가 아니라 **원래 있던 구멍**이고, 고치려면 `protected`
  스냅샷 오브젝트 yaml 을 다시 쓰게 되므로 **사용자 판단이 필요하다**
- 중 3.2 는 `#152` 재범위 때문에 닫지 않는다 (재범위는 닫지 않는다는 규약)
- 지난 세션에서 넘어온 결정 대기: `#141` 2단계(가드에 `selftest/*`) · 중 3.3 생산자 복각 여부 ·
  `#194` 머지(복각 후) · `_archive` 처리 · 시소러스 「미션시스템」이 레거시를 가리키는 것이 의도인지
