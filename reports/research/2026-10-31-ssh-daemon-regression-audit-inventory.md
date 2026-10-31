# SSH·데몬 회귀 조사 — 파일별 검색 목록

기준 HEAD 1366e08의 자료 사본 711개와 Redmine 스냅샷 7개. 총 718개를 대소문자 구분 정규식으로 검색. 매칭 467개 파일. 매칭은 결함 판정이 아니며 정상 SSH 코드·모델 상주·역사 기록도 포함한다. 각 번호는 사본의 원본 줄번호다. 보고서 자체와 본 산출물은 검색에서 제외했다.

| 검색군 | 패턴 | 매칭 줄 | 매칭 파일 |
|---|---|---:|---:|
| daemon | 아래 검색군 정의 참조 | 386 | 108 |
| worker_daemon | 아래 검색군 정의 참조 | 93 | 23 |
| claimer | 아래 검색군 정의 참조 | 212 | 56 |
| AxWorker | 아래 검색군 정의 참조 | 21 | 15 |
| residency | 아래 검색군 정의 참조 | 759 | 156 |
| buildjob | 아래 검색군 정의 참조 | 55 | 18 |
| poll | 아래 검색군 정의 참조 | 262 | 92 |
| pull | 아래 검색군 정의 참조 | 695 | 231 |
| claim | 아래 검색군 정의 참조 | 1095 | 158 |
| heartbeat | 아래 검색군 정의 참조 | 157 | 56 |
| directive | 아래 검색군 정의 참조 | 878 | 223 |
| integrator | 아래 검색군 정의 참조 | 216 | 71 |
| BUILD_CALLERS_ALLOWED | 아래 검색군 정의 참조 | 5 | 4 |
| step5 | 아래 검색군 정의 참조 | 414 | 142 |

검색군: daemon/데몬, worker_daemon, claimer, AxWorker, residency/상주, buildjob, poll/폴링, pull/풀, claim/클레임, heartbeat/하트비트, directive/지시, integrator/통합자, BUILD_CALLERS_ALLOWED, ⑤/정본\s*7단계/다음\s*작업. 각 군의 표현은 OR로 검색했다. 줄별 일치 수이며 출현 횟수와 다르다.

## 전체 파일 목록

| 파일 | 매칭 군과 줄번호 (없음은 무매칭) |
|---|---|
| AGENTS.md | directive:5,21,63; step5:6 |
| AXCluster/context/master/client/bundle.md | residency:10 |
| AXCluster/context/master/test_residency.md | daemon:2,8,14; worker_daemon:2,8,14; residency:2,5,7,14 |
| AXCluster/context/master/work/runner.md | claim:2,22; heartbeat:2,22 |
| AXCluster/context/master/work/worker_daemon.md | daemon:2,5,11; worker_daemon:5,11; residency:15; poll:2,11; claim:11 |
| AXCluster/history/2026-10-31_1825_워커·요청자_상주_데몬_폐기,_서버_SSH_주관_확정_—_#404_복원_철회,_#857.md | daemon:11,13,21,24,26,28,30; AxWorker:30; residency:14,21,24,26,28,30; buildjob:28,30; pull:10; step5:10,28 |
| AXCluster/history/2026-10-31_1829_정본_7단계_⑤_를_「서버가_다음_조각을_배정한다」로_변경_—_pull_모델_폐기.md | daemon:13,21; residency:21; pull:19,21; step5:16,19,21 |
| CLAUDE.md | daemon:49,181,383; AxWorker:388; residency:365,383,384,387; pull:68,70,229,404; claim:69,272; directive:93,193,194; integrator:134,135; step5:59,63,126,263,289,381,384,391 |
| PLAN.md | daemon:16,48,56,119; poll:119,125; pull:45; claim:51; heartbeat:90; directive:97 |
| README.md | residency:317; pull:73,119,182,301,398,430; claim:215; heartbeat:126; directive:84; integrator:14,399 |
| client/README.md | daemon:74,89; worker_daemon:89; claimer:15,88; residency:15,19,55,74,88,89; claim:15,88; integrator:16 |
| client/init/__init__.py | 없음 |
| client/init/bootstrap.py | pull:14,104 |
| client/init/residency.py | daemon:1,15,73,74,80,83,163,267,294,314,315; worker_daemon:73,74,315; claimer:15,18,38,43,47,49,59,138,153,255,285,374,419,430; AxWorker:13,71; residency:1,5,20,24,47,50,63,87,100,145,163,239,250,252,267,272,288,296,302,304,306,308,313,320,326,327,343,347,348,372,383,420,430,437,452,455,459,466; poll:15; pull:169,213; claim:15,18,38,43,47,49,59,61,138,153,255,284,285,325,336,337,349,374,419,430 |
| client/linux/README.md | daemon:9,17; residency:4; step5:10 |
| client/runtime/__init__.py | 없음 |
| client/runtime/client_mcp.py | claim:256; directive:292,293,543,544,1385,1509 |
| client/runtime/fix_flow.py | pull:23,344,485,491; step5:8,9,375 |
| client/runtime/ontology_cache.py | 없음 |
| client/runtime/session1_conductor.py | daemon:361,643; poll:433,463,619; pull:66,338; directive:163,175,187 |
| client/runtime/winsession.py | pull:6 |
| client/windows/README.md | daemon:7,31; residency:9,18 |
| docs/1-background.md | 없음 |
| docs/10-references.md | 없음 |
| docs/11-agent-conduct.md | daemon:106,114,121; directive:15,16,22,33 |
| docs/12-multi-project.md | daemon:312; claimer:9,48,49,109,129,143,249,255,269,373,423,454,465,466,467,470,471,479,480,602,682,684,685,699,700; residency:9,10,11,14,49,129,150,423,456,480,682,684; buildjob:215; poll:10,47; pull:47,262,273,489; claim:9,48,49,75,109,129,143,249,255,269,356,373,423,454,465,466,467,470,471,479,480,493,602,603,682,684,685,699,700; directive:360,650 |
| docs/13-request-tagging.md | claimer:73,82,128; residency:98,101,105,106,109,128,131,132; buildjob:80,88,115; poll:51; pull:53; claim:16,50,73,82,122,128,129,130 |
| docs/14-onboarding-runbook.md | AxWorker:214; residency:208,210,211,213,215,216,220,221,228,240; pull:35; claim:216,241; directive:192,236; integrator:227 |
| docs/15-orchestrator-handoff.md | directive:134; step5:89,100,102,124,130 |
| docs/16-worker-orchestrator-mode.md | pull:211; directive:40,86,105,138,277; step5:275 |
| docs/17-review-queue.md | pull:74,149; directive:176,184,190; step5:17,58 |
| docs/2-architecture.md | residency:207,211; pull:78,108,136,156,157; claim:23,49,84,86,133,169; directive:32,188,207; step5:111 |
| docs/3-open-items.md | daemon:305,307; residency:30,33,83,84,89,173,260; poll:88,162,263,264,305; pull:96,104,132,144; claim:106,199; heartbeat:53,279; directive:36,181,227,269,333; integrator:102 |
| docs/4-work-loop.md | daemon:27,270; residency:115,116; poll:270; pull:145,221,224,229,231; claim:27,28,65,69,222,268,280; directive:246; integrator:233; step5:48,64 |
| docs/5-master-orchestration.md | daemon:199,254,330,337,392,401; residency:199,392,394; poll:283,330,341,342,348,350,353,355,392,396,397,417,447,449,457,460,473,490,491,640,647,651; pull:150,235,341,386,387,389,497,518; claim:52,73,76,82,87,105,238,393,475,476,483,486,513,582,588,591,639; directive:109; step5:262,529,542,547,551,561 |
| docs/5_5-project-isolation.md | daemon:407,426,428,432,436,437,448,449; claimer:37,44,45; residency:45,47,49; poll:31,281,283,428,429,432,578; pull:31,241,245,275,360,429,518; claim:37,43,44,45,47,532; directive:51,63,80,138; step5:400,529,680 |
| docs/6-node-failover.md | residency:127; claim:9,12; heartbeat:6,8,12,16,22,32; directive:8 |
| docs/7-master-gpu.md | 없음 |
| docs/8-git-authority.md | daemon:10; residency:297; pull:21,100,115,146,154,295,422; claim:240; directive:8,23,27,44; integrator:96,125,153; step5:93,162,210,440 |
| docs/9-gajae-code.md | residency:144,146,155,157,177,179,197; pull:178; directive:71,122,125,216,235 |
| docs/9_5-task-queue.md | poll:66; claim:7,35,40,41,46; directive:88 |
| docs/document-registry.json | step5:63 |
| docs/document-sync.md | 없음 |
| docs/milestones/1-infrastructure.md | daemon:11,20; poll:20 |
| docs/milestones/2-twin-restoration.md | pull:79; heartbeat:94 |
| docs/milestones/3-work-pipeline.md | pull:24,98,109,122,145,155; integrator:42,48,59,108,109,114,147,222 |
| docs/milestones/4-origin-reconciliation.md | daemon:81,84,85,206,243,404; claimer:553; residency:206,243; poll:206,310,468,552,554; pull:127,142,145,266,326; claim:86,154,399,470,553,554; directive:15,492; integrator:121,131,156,167,499; step5:318 |
| docs/milestones/5-version-reconcile.md | daemon:16,32; poll:32 |
| docs/milestones/6-improvements.md | daemon:133,152,161,199,305,307,853; claimer:109,112,125,279,597,603,757,852; residency:13,69,88,123,258,394,398,403,597,600,603,604,754,761,763,769,771,773,776,780,781,786,791,795,796,799,852; buildjob:121; poll:36,44,108,199,853; pull:44,113,116,127,133,151,245,790,807,809,925,978,1004,1081,1175,1212; claim:109,111,112,125,152,279,597,600,603,755,757,766,781,852,853,892,1068; directive:59,74,80,85,114,124,128,435,457,501,524,571,574,653,699,703,837,839,986,995,1165,1219; integrator:25,187,872,928,932,933,980,982,983,1045,1049; step5:915,958,1121 |
| docs/milestones/7-improvements.md | pull:33 |
| docs/milestones/README.md | 없음 |
| docs/orchestrator-handoff-history.md | daemon:247,416,1162; worker_daemon:416,1162; residency:21,410,416,421,422,426,564,570,688,690,693,850,920,985,1006,1019,1022,1051,1054,1059,1062,1063,1171,1175,1551,2362,2373; poll:787; pull:248,276,425,438,447,466,1055,1414,1549,1793,1796,1806,1917,1992,2148,2384,2392; claim:402,520,1367,1380,1418,1798,2386,2392,2428; heartbeat:204,284,1307; directive:9,40,78,83,137,156,204,209,219,226,232,238,244,250,256,263,271,279,297,363,390,391,397,421,422,424,425,444,482,506,558,560,577,592,601,604,607,609,616,617,629,631,637,651,664,666,667,673,681,688,693,743,754,767,770,838,859,898,940,1013,1235,1272,1340,1398,1404,1588,1597,1627,1645,1678,1740,1743,1791,1812,1840,1911,2195,2281,2300,2405,2474; integrator:329,2462; step5:3,28,32,35,71,139,144,152,172,225,226,228,232,238,244,250,256,263,271,279,302,310,338,374,422,515,572,593,624,657,697,733,1011,1484,1495,1768,2197,2263,2377,2381 |
| docs/orchestrator-handoff.md | daemon:17,21,25,26,29,31,46,49,57; claimer:31; AxWorker:17,32,57; residency:17,21,23,24,29,31,32,56; buildjob:25,29,46,58; pull:23,72; claim:31; directive:12,31; integrator:30; BUILD_CALLERS_ALLOWED:30; step5:23,26,62,64 |
| docs/orchestrator-rules.md | directive:27,29; integrator:70; step5:52,187,221 |
| docs/settled-decisions.md | daemon:165; poll:30; pull:80,226; claim:19,20,167,170,238; heartbeat:29,167,169; integrator:247,251,262 |
| docs/windows-codex-remote.md | residency:35,81,87; pull:81; directive:3 |
| evidence/redmine-259.json | claimer:4; residency:4; pull:4; claim:4; directive:4; step5:4 |
| evidence/redmine-320.json | daemon:4; claimer:4; residency:4; pull:4; claim:4; heartbeat:4; directive:4; integrator:4; step5:4 |
| evidence/redmine-344.json | daemon:4; residency:4; poll:4; claim:4; heartbeat:4; directive:4 |
| evidence/redmine-404.json | daemon:4; worker_daemon:4; claimer:4; residency:4; poll:4; pull:4; claim:4; step5:4 |
| evidence/redmine-406.json | daemon:4; claimer:4; residency:4; poll:4; pull:4; claim:4; directive:4 |
| evidence/redmine-857.json | daemon:4; residency:4; buildjob:4; integrator:4; step5:4 |
| evidence/redmine-860.json | daemon:4; worker_daemon:4; claimer:4; AxWorker:4; residency:4; buildjob:4; poll:4; pull:4; claim:4; heartbeat:4; directive:4; integrator:4; BUILD_CALLERS_ALLOWED:4; step5:4 |
| machines/README.md | pull:67,74,75 |
| machines/bc250-1.md | daemon:18,168; claimer:69,71,77; residency:49,69,72,74; poll:71; pull:81; claim:69,71,77,101,106,115; step5:49 |
| machines/llm-fitness.md | residency:29,30,42,43,46,125; directive:26,47 |
| machines/sim-desktop-agents.md | directive:5,77; step5:6 |
| machines/sim-desktop.d/bc250-access.md | 없음 |
| machines/sim-desktop.d/environment.md | 없음 |
| machines/sim-desktop.d/services.md | 없음 |
| machines/sim-desktop.md | daemon:91,167,407,409; residency:167,169,264,409; poll:282,329; pull:79,82,167,234,383,415; claim:80,395; directive:102,116,189,192,204,233,256,343,358; integrator:85,86,226; step5:97,167,227 |
| machines/win-main-33.md | daemon:44; residency:98; poll:44; pull:89,114,185; claim:160 |
| machines/win-worker-2.md | daemon:37,38,86,109,111; claimer:46; AxWorker:111,118; poll:38; claim:46 |
| master/README.md | daemon:67,102,241; worker_daemon:67,102; claimer:55,67,102; residency:49,67,102,242; buildjob:68,115; poll:48,71,80; pull:48,55,57,80; claim:42,55,65,67,102,123,176,230,237,240,252; heartbeat:65,240; directive:258,265; integrator:50,56,259; step5:50,62,234 |
| master/agy_models.py | pull:216 |
| master/agy_probe.py | 없음 |
| master/audit_issues_codex.py | directive:1 |
| master/auth.py | claimer:241; residency:268,272; claim:241,246; heartbeat:241,247; directive:204,206,216,230,259 |
| master/batch/__init__.py | poll:3,4 |
| master/batch/gates.py | residency:18; poll:13,17; step5:136 |
| master/batch/run.py | 없음 |
| master/bench.py | directive:147 |
| master/bench_kr.py | 없음 |
| master/bench_lane_codex.py | 없음 |
| master/bench_layer2.py | pull:229 |
| master/bench_skeleton.py | residency:28,48 |
| master/bench_skeleton_codex.py | directive:16,119 |
| master/broker/__init__.py | 없음 |
| master/broker/__main__.py | 없음 |
| master/broker/config.py | residency:6,8,22,27,28,29,30; pull:7 |
| master/broker/health.py | residency:1,5,7,34,57,66,79,88,108; pull:5,8 |
| master/broker/routing.py | residency:7,10,23,28,50,53,69,70 |
| master/broker/server.py | residency:9,139,141; pull:134,141 |
| master/canary.py | 없음 |
| master/census.py | 없음 |
| master/client/__main__.py | daemon:538,541,737; worker_daemon:538,737; residency:14,197,202,207,228,229,302,304,307,309,312,315,318,320,338,339,533,537,549,552,554,664,729 |
| master/client/bundle.py | daemon:161,163,164,169,2068,2069,2075,2190,2192,2193,2199,2206,2208,2263,2275,2278,2279,2282,2340,2343; worker_daemon:161,169,2069,2192,2206,2208,2275,2282,2340; claimer:87,153,2065,2160; residency:88,152,161,162,165,366,2064,2065,2070,2071,2072,2073,2074,2079,2080,2173,2174,2175,2188,2191,2203,2204,2211,2214,2216,2220,2221,2222,2223,2227,2229,2230,2231,2235,2237,2244,2245,2256,2258,2264,2266,2267,2276,2278,2284,2285,2288,2290,2292,2324,2325,2331,2333,2347,2358,2360,2368,2375,2376,2390,2396; poll:152,2195; pull:25,438,594,2069; claim:87,153,2065,2160,2193,2209; directive:22,732,832,854,934,943,955,1892,2031; step5:152 |
| master/client/master_local.py | 없음 |
| master/client/payload/claude_md/ModularStage.md | 없음 |
| master/client/payload/claude_md/MotionForge.md | heartbeat:57 |
| master/client/payload/claude_md/NS.md | directive:17,61 |
| master/client/payload/claude_md/_skeleton.md | directive:17 |
| master/client/payload/profile/AXCluster.yaml | 없음 |
| master/client/payload/profile/KimodoMotion_WebUI.yaml | 없음 |
| master/client/payload/profile/ModularStage.yaml | 없음 |
| master/client/payload/profile/MotionForge.yaml | 없음 |
| master/client/payload/profile/NS.yaml | 없음 |
| master/client/setup_host.py | AxWorker:6; residency:1,6,10,11,16,90,139,156,158 |
| master/client/skills/ax-advance/SKILL.md | directive:12,101,139,166 |
| master/client/skills/ax-fix/SKILL.md | pull:140; directive:21; step5:30,75,94 |
| master/client/skills/ax-gemini/SKILL.md | poll:71; heartbeat:91; directive:41,44,62,91,119 |
| master/client/skills/ax-infer/SKILL.md | pull:186; claim:53; heartbeat:53; directive:3,26,27,36,39,48,207; integrator:18,81,120,145,192; step5:13 |
| master/client/skills/ax-ontology/SKILL.md | pull:79 |
| master/client/skills/ax-request/SKILL.md | claimer:534; residency:133,534; poll:534; pull:185,260,476; claim:17,534,570; heartbeat:533,535,536,537; directive:56,175,273,284,289,301,305,344,367,462,505,529,531,533,534,537,539; integrator:260 |
| master/client/skills/ax-review/SKILL.md | pull:116 |
| master/client/skills/ax-work/SKILL.md | daemon:23,229; pull:73,123,253; claim:41; heartbeat:70; directive:3,48,60,63,116,164,165,272,276; step5:11,232 |
| master/client/spec.py | residency:154; poll:80; directive:147,161,168,380,413,420; step5:150 |
| master/client/uproject.py | 없음 |
| master/client/workshop/CLAUDE.code.md | step5:12 |
| master/client/workshop/CLAUDE.index_only.md | 없음 |
| master/client/workshop/CLAUDE.md | daemon:203,212; poll:203; step5:166 |
| master/client/workshop/README.md | daemon:12,21; worker_daemon:12,21; claimer:12; AxWorker:12; residency:12,21; pull:8; claim:12; integrator:22; step5:121 |
| master/client/workshop/agents/SKILL_INDEX.md | 없음 |
| master/client/workshop/agents/asset-validator.md | 없음 |
| master/client/workshop/agents/build-integration.md | 없음 |
| master/client/workshop/agents/code-convention.md | 없음 |
| master/client/workshop/agents/code-manager.md | 없음 |
| master/client/workshop/agents/code-validator.md | directive:32 |
| master/client/workshop/agents/code-writer.md | step5:41,116 |
| master/client/workshop/agents/crash-diagnoser.md | 없음 |
| master/client/workshop/agents/log-reviewer.md | 없음 |
| master/client/workshop/agents/project-analyzer.md | 없음 |
| master/client/workshop/agents/review-consultant.md | 없음 |
| master/client/workshop/agents/source-analyzer.md | 없음 |
| master/client/workshop/agents/ue-editor-operator.md | 없음 |
| master/client/workshop/hooks/domain_hint.py | directive:59 |
| master/client/workshop/hooks/editor_mcp.py | directive:95 |
| master/client/workshop/hooks/hook_paths.py | 없음 |
| master/client/workshop/hooks/pending_works.py | residency:37; pull:11,185; claim:156; directive:155,182,183,188,215 |
| master/client/workshop/hooks/work_completion.py | poll:385,393,397,444; pull:5,6; heartbeat:240; directive:1,172 |
| master/client/workshop/mcp.json | 없음 |
| master/client/workshop/rules/async-loading.md | 없음 |
| master/client/workshop/rules/code-style.md | 없음 |
| master/client/workshop/rules/unreal-architecture.md | 없음 |
| master/client/workshop/skills/audit-context/SKILL.md | poll:26,69,73,87,93 |
| master/client/workshop/skills/cleanup-drift/SKILL.md | poll:64,75,90 |
| master/client/workshop/skills/debate/SKILL.md | 없음 |
| master/client/workshop/skills/generate-contract-test/SKILL.md | 없음 |
| master/client/workshop/skills/manage-domain/SKILL.md | 없음 |
| master/client/workshop/skills/manage-task/SKILL.md | 없음 |
| master/client/workshop/skills/ontology-register/SKILL.md | poll:110 |
| master/client/workshop/skills/refresh-ontology/SKILL.md | poll:95 |
| master/client/workshop_by_project/ModularStage/rules/mission-editor-mcp.md | 없음 |
| master/client/workshop_by_project/ModularStage/rules/session-management.md | 없음 |
| master/context_search/__init__.py | 없음 |
| master/context_search/bm25.py | residency:370 |
| master/context_search/context_audit.py | 없음 |
| master/context_search/documents.py | 없음 |
| master/context_search/domain_index.py | 없음 |
| master/context_search/embedding.py | 없음 |
| master/context_search/expand.py | 없음 |
| master/context_search/generation.py | daemon:6; residency:6 |
| master/context_search/index.py | 없음 |
| master/context_search/infer.py | 없음 |
| master/context_search/paths.py | pull:17,139; directive:12; integrator:142 |
| master/context_search/rebuild.py | 없음 |
| master/context_search/search.py | 없음 |
| master/context_search/search_log.py | 없음 |
| master/context_search/search_log_analyzer.py | 없음 |
| master/context_search/thesaurus.py | directive:300,304 |
| master/context_search/vector_fallback.py | 없음 |
| master/context_synth/__init__.py | 없음 |
| master/context_synth/__main__.py | 없음 |
| master/context_synth/dismissal_candidates.py | directive:121 |
| master/context_synth/fix_index.py | directive:3,270 |
| master/context_synth/history_gen.py | 없음 |
| master/context_synth/history_harvest.py | 없음 |
| master/context_synth/issue_classifier.py | 없음 |
| master/context_synth/md.py | directive:237 |
| master/context_synth/pending.py | pull:32 |
| master/context_synth/pinned_tree.py | 없음 |
| master/context_synth/plan_archive.py | 없음 |
| master/context_synth/plan_dedup.py | 없음 |
| master/context_synth/plan_generator.py | 없음 |
| master/context_synth/plan_register.py | 없음 |
| master/context_synth/planner.py | 없음 |
| master/context_synth/prompt.py | directive:52,61,157,189 |
| master/context_synth/pydigest.py | 없음 |
| master/context_synth/recipes_read.py | daemon:14; pull:75 |
| master/context_synth/recipes_synthesizer.py | 없음 |
| master/context_synth/related.py | pull:34 |
| master/context_synth/review_collector.py | directive:7,44,63,164,169 |
| master/context_synth/review_gen.py | directive:83,84,85,91,93,134,140,142,143,144,146,148,150,151,155,471,502,512 |
| master/context_synth/review_queue.py | pull:37; claim:33,201,264 |
| master/context_synth/review_runner.py | pull:29; claim:46,120,130,342,345,576; directive:90,93,108,110,111,112,113; step5:50 |
| master/context_synth/signals.py | integrator:12; step5:9 |
| master/context_synth/synth.py | residency:907,928,929,941,969; pull:850; directive:58 |
| master/context_synth/verify.py | pull:67; claim:415,479 |
| master/doc_sync/__init__.py | 없음 |
| master/doc_sync/__main__.py | 없음 |
| master/doc_sync/apply.py | 없음 |
| master/doc_sync/draft.py | directive:31 |
| master/doc_sync/registry.py | 없음 |
| master/events/__init__.py | pull:1 |
| master/events/consumer.py | daemon:5; poll:5,190,193,1341,1343; pull:1,6,719,940,942,1090,1233,1249,1276,1317,1352; claim:184,205,1198,1276,1287,1292; directive:653,976,1007,1075 |
| master/events/gate.py | pull:21; directive:109 |
| master/events/install_hook.py | pull:11,34,37,57,115,151,154,155; claim:11 |
| master/events/post_receive_hook.py | pull:2,14,28,34,61,134,157,177; claim:158; step5:134 |
| master/events/spool.py | pull:1,131; claim:10,13,39,131,145,194,196,203,266; step5:48,78,79,114 |
| master/gitea_group.py | pull:18 |
| master/graph/__init__.py | pull:7 |
| master/graph/__main__.py | daemon:9; residency:9; pull:3,8 |
| master/graph/class_graph.py | pull:1,178,180,181 |
| master/graph/db.py | pull:119 |
| master/graph/dependency.py | pull:176 |
| master/graph/parse.py | 없음 |
| master/graph/pyparse.py | pull:5 |
| master/integration_checks.py | 없음 |
| master/layer2_verify.py | pull:638,748; claim:771,773; directive:87,189,207 |
| master/layer3_verify.py | pull:296,298,303,306,307,325 |
| master/ontology/__init__.py | poll:14 |
| master/ontology/__main__.py | pull:248 |
| master/ontology/collect.py | directive:14 |
| master/ontology/contexts.py | residency:10; pull:496; directive:491 |
| master/ontology/create.py | 없음 |
| master/ontology/descriptions.py | 없음 |
| master/ontology/domain_md.py | 없음 |
| master/ontology/drift.py | pull:91 |
| master/ontology/edit.py | pull:27,122,198,292 |
| master/ontology/edit_field.py | 없음 |
| master/ontology/hierarchy.py | pull:8,16 |
| master/ontology/invalidate.py | 없음 |
| master/ontology/layers.py | 없음 |
| master/ontology/log_candidates.py | 없음 |
| master/ontology/log_tags.py | 없음 |
| master/ontology/package.py | 없음 |
| master/ontology/parse.py | 없음 |
| master/ontology/pkg_audit.py | 없음 |
| master/ontology/prompt.py | directive:10 |
| master/ontology/rename.py | 없음 |
| master/ontology/staging.py | 없음 |
| master/ontology/stale.py | 없음 |
| master/ontology/sync.py | 없음 |
| master/ontology/synth.py | residency:26,53,55,56,57,59,61,62,73,80,308; pull:668; directive:84,486 |
| master/ontology/tasks.py | 없음 |
| master/ontology/unassigned.py | 없음 |
| master/ontology/verify_facts.py | 없음 |
| master/ontology/view.py | 없음 |
| master/ontology/yaml_io.py | poll:226 |
| master/plan_block.py | 없음 |
| master/plan_build.py | daemon:4; residency:4; buildjob:4,11,19,29,53,58,65,70,78; integrator:3; BUILD_CALLERS_ALLOWED:3 |
| master/plan_start.py | 없음 |
| master/plan_state.py | pull:17 |
| master/plan_steps.py | 없음 |
| master/plan_tools.py | 없음 |
| master/projects/__init__.py | 없음 |
| master/projects/__main__.py | directive:70 |
| master/projects/config.py | claim:94,138; directive:254 |
| master/projects/control_route.py | 없음 |
| master/projects/logic.py | daemon:315 |
| master/projects/mcp_server.py | pull:877; step5:516 |
| master/projects/onboard.py | claimer:17,33,36,38; residency:17,33,34,39; pull:144,158,206,422,524,565,759; claim:17,33,35,36,38; directive:265,360,622 |
| master/projects/profile.py | residency:46,173; step5:46 |
| master/projects/register_route.py | directive:8 |
| master/projects/workshop_check.py | pull:68 |
| master/provision.py | residency:1,4,6,7,34,36,44,50,94,108,110,114,197; pull:10,21,151,154,161,163,165,170,189,200,207,213 |
| master/redmine.py | integrator:5 |
| master/requirements.txt | 없음 |
| master/service_freshness.py | daemon:19,20; claimer:12; residency:12,22,43,45,118; claim:12 |
| master/service_restart.py | 없음 |
| master/sigma_audit.py | poll:19 |
| master/skills/ax-deliver/SKILL.md | daemon:19; directive:19 |
| master/skills/ax-docsync/SKILL.md | 없음 |
| master/skills/ax-handoff/SKILL.md | directive:47,48,51; step5:66 |
| master/skills/ax-mode/SKILL.md | 없음 |
| master/skills/ax-plan/SKILL.md | 없음 |
| master/skills/ax-redmine/SKILL.md | 없음 |
| master/skills/ax-worker-setup/SKILL.md | AxWorker:17; residency:3,9,17,18,51 |
| master/skills/debate/SKILL.md | residency:47,49 |
| master/skills/distribute/SKILL.md | directive:84; integrator:62; step5:100,108 |
| master/source_text.py | 없음 |
| master/sqlite_util.py | 없음 |
| master/status.py | daemon:834,835,838; claimer:419,610,835; residency:141,419,835,1168,1211; poll:12,1095; pull:422,840,1365; claim:346,352,355,419,610,679,707,709,729,737,738,835,899,979,1190; heartbeat:347,350,355; integrator:710,935; step5:418 |
| master/systemd/ax-batch.service | daemon:4; residency:9; poll:4 |
| master/systemd/ax-batch.timer | 없음 |
| master/systemd/ax-broker.service | residency:16 |
| master/systemd/ax-dispatch-catchup.service | 없음 |
| master/systemd/ax-dispatch.path | poll:6; pull:8,9; claim:9 |
| master/systemd/ax-dispatch.service | residency:12; poll:13 |
| master/systemd/ax-dispatch.timer | 없음 |
| master/systemd/ax-followup.service | daemon:4; poll:4; integrator:11 |
| master/systemd/ax-followup.timer | 없음 |
| master/systemd/ax-indexer.path | poll:6; pull:2 |
| master/systemd/ax-indexer.service | daemon:4; residency:9; poll:4; pull:2,9 |
| master/systemd/ax-indexer.timer | pull:5,7; integrator:15 |
| master/systemd/ax-projects.service | 없음 |
| master/systemd/ax-review-queue.service | daemon:4; poll:4 |
| master/systemd/ax-review-queue.timer | 없음 |
| master/systemd/ax-status.service | residency:9 |
| master/systemd/ax-status.timer | 없음 |
| master/systemd/ax-task-queue.service | poll:27; claim:2 |
| master/task_queue/__init__.py | 없음 |
| master/task_queue/__main__.py | 없음 |
| master/task_queue/logic.py | daemon:553,557; poll:31; pull:100,149,151,377,410; claim:26,28,30,307,361,365,374,376,388,565; heartbeat:31,360,375; directive:30 |
| master/task_queue/logic_claim.py | claimer:157,192; poll:22,275,315,323; pull:22,103,140,205; claim:1,18,20,30,31,46,47,57,78,98,122,125,127,139,151,157,173,189,192,218,223,227,230,232,236,240,242,246,251,252,257,259,292,293,316; heartbeat:54,57,123,243,275,287,298,300,307,311; directive:1,265,266,267,269,273,274,276,277,281,282,283,284,309,310,311,312,316,321,322,323,324 |
| master/task_queue/logic_cleanup.py | daemon:298,676,815; pull:375,481,486; directive:528,530,533,555,579,820; integrator:820 |
| master/task_queue/logic_lifecycle.py | daemon:73,74,75; worker_daemon:73; claimer:72,80; residency:72,73,80; pull:124,204,228,322; claim:18,72,80,119,120,200,201,204,219,252,258,302,332,343; heartbeat:220,253,333 |
| master/task_queue/logic_persist.py | 없음 |
| master/task_queue/mcp_server.py | claim:18,24,85,86,90 |
| master/task_queue/models.py | daemon:45; claimer:112; pull:58,102,195; claim:15,16,101,105,112; directive:12,215 |
| master/task_queue/persistence.py | daemon:98; poll:555; pull:32,47; claim:549,550,559,562,563; heartbeat:266,555; directive:555,556,557 |
| master/task_queue/reclaim.py | poll:10; pull:21,43,46,49,50; claim:10,15,22,127,142,159,164,165,168,172,176,184,191,195,201,204,206,208,210,213,214,221,222,224; heartbeat:167,172,186,202,219 |
| master/task_queue/server.py | daemon:60,65,86,89,91,155,1061,1071,1075,1083,1092,1096,1104,1118,1119,1140,1203,1218; claimer:338,339; poll:16,41,473,474,481,483,724; pull:155,724; claim:41,48,85,86,88,134,334,335,338,339,345,430,478,724,1013,1019,1055; heartbeat:41,352,353,354,356; directive:43,428,486,487,488,490,1005,1017,1103,1104,1105,1106,1110,1111,1119,1138,1228,1230,1231,1234,1240,1250; integrator:691 |
| master/task_queue/tagging.py | claimer:77; poll:80,152; pull:148; claim:10,76,77,79,151,176,177; heartbeat:69; directive:49 |
| master/test_agy_models.py | 없음 |
| master/test_agy_probe.py | 없음 |
| master/test_attempt.py | integrator:108,179; step5:12 |
| master/test_auth.py | claim:205,206,230 |
| master/test_autodispatch.py | pull:56,147,150,151,157,295; claim:110,147,148,151,156,157,162,163,178,179,193,221,311 |
| master/test_batch.py | step5:9,135,194,196,197,202,203 |
| master/test_batching.py | 없음 |
| master/test_bm25_diagnose.py | residency:4 |
| master/test_board.py | step5:296,316 |
| master/test_bootstrap.py | pull:80 |
| master/test_branch_prune.py | pull:402,629; claim:156; step5:10,280,464 |
| master/test_broker_health.py | residency:1,82,90,112 |
| master/test_broker_routing.py | residency:45,51,54,84,89,90; pull:111 |
| master/test_build_local.py | 없음 |
| master/test_canary.py | 없음 |
| master/test_capability_routing.py | claim:18,66,70,77,81,84,92,93,99,109,113,117,119,138,144,151,160 |
| master/test_census.py | 없음 |
| master/test_cleanup.py | claim:154 |
| master/test_client_bundle.py | daemon:255,260,269,270,364; worker_daemon:255,260,270,364; claimer:248,249,255,266,267,343; residency:250,251,253,257,269,344,358,1452,1476,1502,2426,2431,2554; pull:253,1048; claim:248,249,255,266,267,343; directive:190,705,828,943,951,985,1006,1205; step5:700,835 |
| master/test_client_cache.py | step5:10,122,123,125,126,129 |
| master/test_client_editor_mcp.py | daemon:62; step5:9,152,154 |
| master/test_client_master_local.py | 없음 |
| master/test_client_mcp.py | claim:409 |
| master/test_client_spec.py | directive:233,1008; step5:197 |
| master/test_commit_flow_page.py | residency:57,67; step5:9,84,86,87,93,94,95 |
| master/test_conductor_metrics.py | 없음 |
| master/test_context_audit.py | step5:10,152,165,171,172 |
| master/test_context_doc_view.py | 없음 |
| master/test_context_search.py | 없음 |
| master/test_context_synth.py | directive:469,470,472,473,474,484,488,493,494 |
| master/test_conventions.py | 없음 |
| master/test_coordinator.py | step5:11,169,170 |
| master/test_declarations.py | directive:72 |
| master/test_decompose.py | directive:200 |
| master/test_descriptions.py | 없음 |
| master/test_dismissal_candidates.py | 없음 |
| master/test_dispatch_axis.py | 없음 |
| master/test_dispatch_records.py | daemon:96; claimer:5,10; residency:5; pull:1,7,13,88; claim:5,10,135,140; heartbeat:137 |
| master/test_distribute.py | 없음 |
| master/test_doc_sync_apply.py | 없음 |
| master/test_doc_sync_cli.py | 없음 |
| master/test_doc_sync_draft.py | 없음 |
| master/test_doc_sync_registry.py | 없음 |
| master/test_domain_index.py | 없음 |
| master/test_drift.py | 없음 |
| master/test_edit_field.py | step5:8,156 |
| master/test_events.py | poll:78,154,159; pull:163; claim:68,78,85,91,95,100,112,122,129,144,154,293,296,304,322,324,325,327,335,352,367,377,385,412 |
| master/test_expand.py | 없음 |
| master/test_failed_work_terminal.py | claim:72,73,98,101,123,129,137,165,166,176,180,191,208,217,220,225,240,247,263,299,311,314,333,345,347,357,358,369,375,392,400 |
| master/test_fix_index.py | pull:8,139; directive:14,233,234,251,256,257; step5:9,147,148,149,151,153,155,157,159 |
| master/test_fixes_surface.py | pull:15,466; step5:11,338,397,399,400,402,403,404,406,407,409,414,416,516,523,525,529,531,536,539,540,545,551,553,555,556,559,561,562,568,570,588,589,592,594 |
| master/test_followup.py | poll:832,837,851,893,925,962,1029,1101,1130,1279,1297,1435,1446; claim:81,84,825,952,1021,1022,1025,1026,1056,1060,1116,1121,1175,1253; heartbeat:509; step5:273 |
| master/test_gate.py | 없음 |
| master/test_gemini_report.py | 없음 |
| master/test_gitea_group.py | 없음 |
| master/test_graph.py | pull:9,173,245 |
| master/test_handoff_size.py | step5:10,26,50,69,71 |
| master/test_handover.py | pull:3,66,263,264,265; claim:78 |
| master/test_heuristic_loop.py | residency:11 |
| master/test_heuristics.py | poll:105,173 |
| master/test_history_gen.py | 없음 |
| master/test_history_harvest.py | step5:9,192 |
| master/test_id_typing.py | claim:29,58,81; heartbeat:8 |
| master/test_indexer.py | pull:1,166,167; directive:873,1018 |
| master/test_infer.py | poll:221,222,230; pull:7,109,321,329,347; claim:45,382,383,384,385,394,402,403,404,477,478,480,536,537,669,671,682,698,699,701,718,762,763,782,807,808,1639,1641,1662,1666; heartbeat:410,1058,1233,1276,1293,1296,1319,1673; directive:46,274; integrator:480,499,500,610,622; step5:555 |
| master/test_infra_undecided.py | pull:17,21,293,365,381,391,396; claim:111,112,193,213,222,233,234,240,241,242,246,247,251,281,282,300,301; step5:19,310 |
| master/test_integration_checks.py | 없음 |
| master/test_invalidate.py | 없음 |
| master/test_lanes.py | directive:64,68,69,191,193,199 |
| master/test_layer1.py | pull:182; directive:66,212; integrator:199 |
| master/test_layer2_grounding.py | directive:118 |
| master/test_layer3_verify.py | 없음 |
| master/test_llm_policy.py | 없음 |
| master/test_log_tags.py | 없음 |
| master/test_mcp_boundary.py | 없음 |
| master/test_mcp_servers.py | claim:73 |
| master/test_mount_gate.py | poll:94,95,105,308; pull:95,101 |
| master/test_no_integrator.py | claim:149,173; directive:1; integrator:1,8,15,67,69,73,80,84,169,176; BUILD_CALLERS_ALLOWED:100,114 |
| master/test_norms.py | 없음 |
| master/test_nowork.py | daemon:155; claim:11,16,34,66,67 |
| master/test_onboard.py | pull:324,422; directive:294 |
| master/test_ontology.py | 없음 |
| master/test_ontology_create.py | 없음 |
| master/test_ontology_edit.py | pull:119,121,125 |
| master/test_ontology_python.py | 없음 |
| master/test_ontology_sync.py | 없음 |
| master/test_ontology_synth.py | pull:339 |
| master/test_orchestration_control.py | daemon:154; worker_daemon:154 |
| master/test_pending.py | pull:10; step5:10,90 |
| master/test_pinned_tree.py | 없음 |
| master/test_pkg_audit.py | step5:9,151,174,175,176 |
| master/test_plan_block.py | 없음 |
| master/test_plan_build.py | buildjob:29,80; claim:45 |
| master/test_plan_start.py | 없음 |
| master/test_plan_state.py | 없음 |
| master/test_plan_steps.py | 없음 |
| master/test_plan_tools.py | 없음 |
| master/test_planner.py | step5:9,339 |
| master/test_porting.py | 없음 |
| master/test_project_affinity.py | 없음 |
| master/test_project_profile.py | step5:9,88 |
| master/test_projects.py | 없음 |
| master/test_protect.py | pull:60,71 |
| master/test_provision.py | residency:8,67,77,82,85,87,93,98,109,135; pull:7,24,69,167,174,176,180,186,188,198,201,213,229 |
| master/test_pydigest.py | 없음 |
| master/test_pyparse.py | 없음 |
| master/test_pystatic.py | 없음 |
| master/test_python_commit_review.py | 없음 |
| master/test_rag_callers.py | 없음 |
| master/test_rag_logs_page.py | 없음 |
| master/test_rag_request_flow.py | 없음 |
| master/test_rag_routes.py | 없음 |
| master/test_rag_trace.py | 없음 |
| master/test_recipes.py | step5:8,170 |
| master/test_recipes_read.py | 없음 |
| master/test_redmine.py | 없음 |
| master/test_redmine_live_guard.py | 없음 |
| master/test_redmine_wiki.py | daemon:135 |
| master/test_related.py | pull:5,60; step5:9,97 |
| master/test_rename.py | 없음 |
| master/test_requester_handoff.py | claim:81; step5:16 |
| master/test_residency.py | daemon:44,54,71,236,252,293,305,339,356,409,479,501,517,529,567,568,617; worker_daemon:71,236,252,293,305,339,356,409,501,517,529; claimer:1,54,91,228,304,419,620; AxWorker:57,58,488; residency:1,12,22,68,136,204,208,252,283,299,311,317,319,334,354,361,376,384,388,406,424,433,448,453,459,466,479,482,543,563,584,592,593,596,622,627,629; pull:442,486,540; claim:1,54,90,91,92,113,116,123,124,125,127,228,304,307,308,419,611,620 |
| master/test_revalidation.py | 없음 |
| master/test_review.py | pull:360,565; integrator:370 |
| master/test_review_collect.py | 없음 |
| master/test_review_enqueue.py | step5:9,111,112 |
| master/test_review_gen.py | directive:268,432,481,489,492,495,507,522,528,530,539; step5:318,432 |
| master/test_review_queue.py | claim:87,102,103,109,118,124,126,132,134,141,149,160,161,166,169,175,203,211,220,226,231,232,233,237,244,249,251,272,274; step5:9,85,109 |
| master/test_review_runner.py | claim:468; directive:18,516,520,532,542,544,545,549,568,671; step5:9,147,148 |
| master/test_revise.py | claim:163,167,174,175,187; directive:149 |
| master/test_rounds.py | pull:404,418; claim:27,52,525,526,527,546,548,551,552,554; directive:324 |
| master/test_runbook.py | residency:124 |
| master/test_runner.py | poll:606,616,617,895,905,1144,1180; pull:1188; claim:306,323,324,325,326,327,359,360,386,389; heartbeat:188,248,250,256; directive:111,116,500,518,520,532,536,549,550,577,733,738,1062,1070,1083,1396,1570,1582,1587 |
| master/test_sandbox.py | directive:46,47,58,66,70,78,79,102,114,146 |
| master/test_search_log.py | step5:9,166,177,179,180 |
| master/test_selftest.py | poll:102,105,117,120,125,126,129,209; directive:80 |
| master/test_service_freshness.py | residency:147,151,171 |
| master/test_service_restart.py | step5:85 |
| master/test_session_usage.py | step5:5 |
| master/test_session_usage_dedupe.py | 없음 |
| master/test_setup_host.py | residency:1,3 |
| master/test_sigma_audit.py | 없음 |
| master/test_signals.py | integrator:7,128,130,131 |
| master/test_skeleton.py | pull:294,356; directive:208,209,212,225 |
| master/test_skeleton_gate.py | directive:110 |
| master/test_source_scope.py | step5:160 |
| master/test_sqlite_util.py | 없음 |
| master/test_staging.py | step5:9,105,116,119,121,122,123,126,128,142,145,173,174,176 |
| master/test_stale_index.py | 없음 |
| master/test_stale_unknown.py | 없음 |
| master/test_status.py | claim:64,127,131; step5:9,72 |
| master/test_status_live.py | pull:170; claim:40,46,47,139,141,176,202 |
| master/test_stepper.py | claim:37,38,45,53,63,71,78,86,99,114,115,133 |
| master/test_subbranch.py | 없음 |
| master/test_submit_gates.py | residency:135; pull:134; claim:26,43,44,49,60,64,78,81,87,97,99,102,104,105,113,114,122,125,141,142,143,144,149,150; heartbeat:101 |
| master/test_synth_parallel.py | step5:220 |
| master/test_tagging.py | claimer:239; residency:239,243; buildjob:249,250,252; poll:134,144,215; claim:5,60,133,144,160,161,162,164,165,166,211,221,222,239,240,364; directive:97 |
| master/test_task_data.py | claim:1,4,6,24,61,63,68,69,70,74,78,93,94,100,101,106,108,139,158 |
| master/test_task_submission.py | claim:17,34,39,48,63,69,85,108 |
| master/test_task_templates.py | 없음 |
| master/test_tdd_dryrun.py | 없음 |
| master/test_thesaurus_guard.py | pull:46; directive:1 |
| master/test_transfer.py | 없음 |
| master/test_twin_base.py | 없음 |
| master/test_unassigned.py | 없음 |
| master/test_uproject.py | 없음 |
| master/test_usage_accounting.py | pull:38 |
| master/test_usage_cli_paths.py | directive:347; step5:9 |
| master/test_usage_dashboard.py | 없음 |
| master/test_usage_nav.py | 없음 |
| master/test_usage_page.py | 없음 |
| master/test_usage_routes.py | 없음 |
| master/test_usage_sink.py | pull:9,126; step5:223 |
| master/test_utf8.py | 없음 |
| master/test_verdict.py | directive:94 |
| master/test_verify_filetypes.py | pull:79 |
| master/test_verify_gate.py | pull:94,96 |
| master/test_version.py | step5:11,50,58 |
| master/test_view.py | 없음 |
| master/test_viewer.py | poll:117; directive:334; step5:10,293 |
| master/test_wcommit.py | step5:10 |
| master/test_webui_side_nav.py | 없음 |
| master/test_webui_write_routes.py | step5:10 |
| master/test_winsession.py | 없음 |
| master/test_work.py | pull:10,434; directive:8,491 |
| master/test_work_claim_scope.py | claim:8,36,37,39,40,45,50,53,55,59,62,64,65,74,80,86 |
| master/test_work_completion.py | poll:246; claim:74,224,254 |
| master/test_work_mode_override.py | 없음 |
| master/test_work_mode_patch.py | 없음 |
| master/test_work_mode_stamp.py | 없음 |
| master/test_worker_daemon.py | daemon:9,21,38,129,147,155,237,239,264,266,268,284,344,345,346,347,348,354,357,360,368,378,388,408,434,437; worker_daemon:21,38,129,147,155,237,239,264,266,268,284,344,345,346,347,348,354,357,360,368,378,388,408,437; claimer:11,14,16,42,101,369,370,376; residency:258,261,340,344,348,404,434; buildjob:11,17,38,161,181,187,220,227; pull:11,17,18,163,169,231; claim:11,14,16,36,42,55,64,71,86,87,101,326,329,341,369,370,376; heartbeat:86,88,111,112,136,322,324,326,331,333,335,386; directive:5,245; step5:18,231 |
| master/test_worker_mode_transport.py | 없음 |
| master/test_workmodel.py | claim:3,53,69,125,165,196,288,337,338,339,343,344,346,360,367,368,381,382,395 |
| master/test_workshop_check.py | 없음 |
| master/transfer.py | pull:33,281 |
| master/utf8.py | 없음 |
| master/verdict.py | directive:52,94 |
| master/version.py | 없음 |
| master/viewer.py | poll:46,152; pull:134,285; directive:17,272 |
| master/webui/app.py | directive:1,307 |
| master/webui/board.py | 없음 |
| master/webui/commit_flow.py | residency:23,25,203,206; step5:70 |
| master/webui/fixes_page.py | 없음 |
| master/webui/loaders.py | directive:3 |
| master/webui/nav.py | 없음 |
| master/webui/onboarding.py | directive:71; step5:61,102,139,159,160 |
| master/webui/orchestration.py | 없음 |
| master/webui/rag_logs.py | 없음 |
| master/webui/routes.py | claimer:227; residency:227; pull:226,228; claim:227; directive:1; step5:36,40,55 |
| master/webui/usage_page.py | 없음 |
| master/webui/web_ui_original.py | 없음 |
| master/work/__init__.py | 없음 |
| master/work/attempt.py | pull:4,11,43,99,100,101; integrator:81,91 |
| master/work/autodispatch.py | daemon:5,12,17; residency:6; poll:5,18,503; pull:35,76,77,168,188,231,259,276,372,381,391,393,397,483,509,514,534,589,591,616; claim:5,6,18,20,45,46,259,369,371,395,403,501,503,514; directive:169,172,189,493; integrator:18,88,359,504,517; step5:366 |
| master/work/ax_safety.py | daemon:1,3,29,34,81; worker_daemon:29,34; claimer:3,107; residency:1,3; claim:3,9,107; heartbeat:8 |
| master/work/batching.py | 없음 |
| master/work/branch_names.py | pull:29; directive:45 |
| master/work/build_local.py | 없음 |
| master/work/buildjob.py | claimer:12; buildjob:7,8,9,11,69,114; pull:72; claim:12,105 |
| master/work/cleanup.py | 없음 |
| master/work/conductor.py | residency:18 |
| master/work/conductor_auth.py | 없음 |
| master/work/conventions.py | pull:11,15; directive:7,15 |
| master/work/coordinator.py | claim:122; integrator:10 |
| master/work/declarations.py | directive:5 |
| master/work/decompose.py | 없음 |
| master/work/distribute.py | pull:7,73; integrator:8,72 |
| master/work/failures.py | pull:93; step5:42 |
| master/work/followup.py | daemon:900; poll:1374,1460,1468,1472; heartbeat:811,812,865,867,884,895,900; integrator:11,16,17; step5:86,187 |
| master/work/gemini_report.py | daemon:141; pull:35; heartbeat:8,121; directive:12,77,422 |
| master/work/generate.py | directive:78,113; step5:11 |
| master/work/handover.py | claimer:8; pull:160,165,241,247,283,308,339,347; claim:8 |
| master/work/heuristics.py | directive:1,65; step5:36,106 |
| master/work/infer.py | daemon:1558,1578; residency:1567,1578,1616; pull:5,32,33,110,118,147,302,375,387,390,399,413,433,490,491,712,715,729,859,895,896,1225,1377,1566,1576,1583,1586; claim:25,117,432,490,560,567,570,620,632,642,719,812,814,817,832,833,837,860,1030,1032,1151,1154,1448,1452,1470,1474,1475,1480,1506,1508,1528,1615,1621,1622; heartbeat:320,361,714,1027,1053,1152,1153,1154,1168; directive:10,15,62,63,66,166,167,198,203,204,288,322,323,333,335,538,728,731,733,1077,1081; integrator:28,117,132,302,303,327,387,408,432,436,450,462,484,489,715,1031,1284; step5:6,37,1440 |
| master/work/lanes.py | residency:13; directive:8,43,44,94,96,103,152 |
| master/work/layer1.py | directive:36,77; integrator:12,13,37 |
| master/work/llm_policy.py | 없음 |
| master/work/logs.py | claimer:5,6,19; residency:5,23; pull:10,15,39,49,55,67,92; claim:5,6,19 |
| master/work/mode.py | 없음 |
| master/work/norms.py | pull:22 |
| master/work/porting.py | 없음 |
| master/work/pre_push_hook.sh | pull:48 |
| master/work/pyskel.py | 없음 |
| master/work/pystatic.py | 없음 |
| master/work/register.py | pull:792,859,879; integrator:553; step5:298,367 |
| master/work/revalidation.py | pull:3 |
| master/work/review.py | pull:195,200,881,1172; claim:145; directive:1060,1184; integrator:212,336 |
| master/work/revise.py | claim:23,61; directive:36,96 |
| master/work/runner.py | daemon:14,81,1074,1376; residency:894,1181,1376; pull:20,29,1127,1179; claim:5,1110,1112,1167,1172,1176,1178,1180,1184,1187,1199,1201,1267,1317,1321,1328,1336; heartbeat:18,20,944,1054,1087,1104,1209,1210,1346; directive:6,31,77,78,81,109,130,132,167,495,510,511,677,678,692,1089,1339; integrator:1246 |
| master/work/selftest.py | daemon:23,163,165,569,570,606,806; residency:165; poll:156,159,160,162,163,179,180,182,285,603,606,610,611,613,614,806,808,818,826,827; pull:40,531; claim:166,170,209,614,669,683,694,696,700,704,708,712,714,715,716,726,728,732,771,772,773,805,812; heartbeat:165,166; directive:148 |
| master/work/session_usage.py | daemon:625,636,1034,1054; pull:147 |
| master/work/skeleton.py | residency:568; directive:38,49,413,469,688 |
| master/work/skeleton_gate.py | pull:245,252; directive:286,289; integrator:13,15,20 |
| master/work/subbranch.py | 없음 |
| master/work/tdd_dryrun.py | directive:86; step5:11 |
| master/work/twin_base.py | pull:97; directive:96; integrator:221,222 |
| master/work/usage.py | pull:565,643 |
| master/work/usage_dashboard.py | 없음 |
| master/work/wcommit.py | daemon:16,20,22; residency:20; pull:86,195,215; claim:10,39,287; directive:353,485,488; step5:3,4,440 |
| master/work/worker_daemon.py | daemon:8,27,28,32,34,36,68,69,70,71,186,276,399,411,490,515,520,553,564,620,640,700,734,799,801; worker_daemon:27,28,32,36,68,69,70,71,276,399,411,515,520,700,734,799,801; claimer:1,187,210,212,219,258,262,348,457,548,695,728,747; residency:31,34,36,62,64,156,185,187,233,251,304,321,345,347,352,356,365,368,375,429,468,489,502,515,516,702,719,724,727,734,737,751; poll:1,36,160,748; pull:15,152,172,310,455,516,565,566,638,690,730; claim:1,4,13,22,71,137,138,152,165,172,187,210,212,219,258,262,318,348,457,489,548,645,695,725,728,747,762,769; heartbeat:175,178,572,576,649,650,651; directive:555; integrator:21; step5:565 |
| master/work/workmodel.py | claim:12,15,16,61,304; directive:429 |
| reports/06-master-execution-model-and-task-queue-port.md | residency:16,238,240,255; claim:54,275,379; directive:62,163,183,217,218,299,322,323,394,410 |
| reports/07-capability-routing-second-endpoint-broker.md | residency:111,122,140,148,168,169,178,180,194,266; pull:9,50,106,174,178,180,264; claim:33,40,57,61,263 |
| reports/08-project-registry-mcp-and-doc-split.md | daemon:41,325,331,338,340,812,1094; residency:106,1094,1384; poll:338,340,429; pull:179,198,295,400,549,899,1256,1365,1404; claim:233,894,922,938,953,1206,1233,1236,1292,1327,1351; directive:74,76,121,123,203,252,320,465,508,613,690,768,813,867,960,1011,1029,1192,1367; step5:903,1155 |
| reports/09-project-analysis-and-agenttest-backport.md | daemon:63,67,195; residency:29,63,67,83,92,181,183,195; pull:24,50,79,112,116,170; claim:19,113; directive:3,113,154,190; step5:97,189 |
| reports/10-milestone2-restructure-and-relation-graphs.md | poll:56; pull:97; directive:3,42,202 |
| reports/100-motionforge-onboarding-and-plugin-scope.md | pull:86 |
| reports/101-redmine-wiki-mcp.md | 없음 |
| reports/102-gemini-delegation-and-usage-dedupe.md | residency:104; poll:24; pull:116; heartbeat:22; directive:33,38,44,113 |
| reports/103-projects-shutdown-listen-stream.md | directive:3 |
| reports/105-788-policy-and-main-merge-dryrun.md | 없음 |
| reports/106-layer2-live-b-verdict.json | 없음 |
| reports/106-layer2-live-fallback-verdict.json | 없음 |
| reports/106-layer2-orchestrator-recheck.md | pull:17,34 |
| reports/107-788-distributed-retry-and-cancellation.md | residency:26; pull:22; directive:1,20 |
| reports/108-worker-job-lifecycle-796.md | daemon:11; worker_daemon:11; residency:21,45; heartbeat:19 |
| reports/109-requester-followup-798.md | 없음 |
| reports/11-ontology-llm-synthesis-and-worker-wiring-gap.md | daemon:549,575; residency:15,16,19,145,146,205; pull:135,405,431,584,704,709,762,1219; heartbeat:499,576,618; directive:21,34,71,104,128,150,174,233,260,333,498,512,784,974,982,992,1265,1356; step5:357,744,827 |
| reports/110-work-task-wrapper-stage2.md | claim:11,115,139; directive:155,158,164,180; integrator:127,128,150; step5:120 |
| reports/111-retry-feedback-806-809.md | pull:52 |
| reports/112-handoff-restore-824-823-818-821.md | pull:68; heartbeat:53 |
| reports/113-823-first-collection-cloud-budget-codex-path.md | daemon:42,82; directive:41 |
| reports/114-bug-batch-798-814-799-763.md | residency:11 |
| reports/115-825-pinned-worktree-direct-read.md | directive:29 |
| reports/116-815-two-stale-failures-cleared.md | daemon:29; step5:8,39 |
| reports/117-815-mypy-measurement-distribute-defects.md | residency:54; step5:55 |
| reports/118-815-mypy-step7-gate-redmine-cleanup.md | directive:8,77; step5:88,96 |
| reports/119-815-step7-regression-selection.md | pull:44; step5:1,9,64,78 |
| reports/12-milestone3-skeleton-and-freeze.md | pull:110,151,184,405; directive:10,41,42,43,278; integrator:94,125,146,147,162,336,386,404; step5:311,365 |
| reports/120-815-official-list-expansion.md | step5:41,58,59,64 |
| reports/121-815-intent-axis-measurement-agy-quota.md | directive:8,19,27,46,56 |
| reports/122-agy-model-alias-argon-review-queue.md | directive:10,11 |
| reports/123-agy-explicit-model-policy.md | heartbeat:43; directive:70; step5:47 |
| reports/124-windows-session0-guard.md | directive:3,22,37 |
| reports/125-layer2-deepcopy-thread-race.md | 없음 |
| reports/126-document-sync.md | directive:7 |
| reports/127-doc-sync-cloud-policy-local.md | pull:110; directive:7,9 |
| reports/128-nvidia-driver-dual-monitor.md | directive:27 |
| reports/129-nodejs-brotli-cve-sweep.md | pull:47,49; directive:3,32,39,42,51,55 |
| reports/13-milestone3-inference-dispatch.md | residency:301,317,323,540,582; poll:667; pull:18,133,141,145,147,244,267,405,408,450; claim:136,153,267; directive:45,46,55,77,101,106,220,412,682,754,766; integrator:31,120,135,144,148,203,269,311,325,413,454,520; step5:497,906 |
| reports/130-worker2-board-swap-setup-host-ollama.md | AxWorker:18; residency:18,26,27,28,45,64,72,241; directive:157,233 |
| reports/131-849-ontology-pinned-tree.md | 없음 |
| reports/132-826-plan-block-phase-a.md | 없음 |
| reports/14-origin-citation-audit.md | daemon:4,75,490,1189,1190; claimer:1385; residency:639,1178,1190; poll:194,260,315,899,936,1028,1385,1386; pull:70,219,449,459,661,677,734,802,1020,1025; claim:178,179,436,473,601,735,802,915,919,1355,1385; directive:4,497,499,645,811,1049,1274; integrator:61,228,316,460,477,593,600,1414; step5:392,1445 |
| reports/16-master-write-surface.md | daemon:433; residency:305; poll:304,310,372,663,668,669,824; pull:175,178,196,199,796; claim:670,795; directive:229,235,258,261,276,313,465,763; integrator:681; step5:95,105,376,498,843 |
| reports/17-partial-invalidation.md | residency:233,363,408,436,437,448,457; step5:20,314,366,502 |
| reports/18-selftest-stage2.md | daemon:70,71,86,88,175,176,207,208,517,518,536; residency:11,88,809; poll:64,78,86,96,113,160,175,183,208,350,629; pull:255,296,310,316,325,528; claim:89,92,112,126,128,134,138,148,152,158,184,546; heartbeat:88,89; directive:655,842; integrator:174,675,705; step5:51,180,201,206,255,296,300,310 |
| reports/19-m5-version-judgments.md | daemon:44,51,52; residency:210,214,238,240,273,283,285,290; poll:44,51,52; pull:44,52; directive:5,136,316 |
| reports/20-carryover-and-korean-tags.md | residency:121,127,131; poll:160; directive:3,27,29,53,55,56,84,118,168; step5:24 |
| reports/21-buildjob-claimer.md | daemon:15,19,66,81,130,133,135,155,177,181,186,198; claimer:1,5,15,19,26,29,38,49,52,66,87,103,130,139,140,149,182,194; residency:19,66,130,131,133,139,145,154,171,197; buildjob:13,37,52,67,114,116,118; poll:15,123,139,153,171,181; pull:1,5,65,69,74,81,96,102,106,131,145,167,181,188,195,197,198; claim:1,5,10,15,19,21,25,26,29,38,45,49,52,66,81,87,91,94,103,130,139,140,149,155,177,181,182,187,194; heartbeat:21; directive:3,65,69,97,105,130,133,167; integrator:92,96 |
| reports/22-log-tagging.md | residency:7; pull:7; directive:3 |
| reports/23-first-production-distribute.md | daemon:4,26; pull:4; claim:4,26; directive:3,5,31,70; integrator:41 |
| reports/24-claimer-task-logs.md | daemon:15,62; claimer:1,21,30,32,64,71,156; residency:33; pull:65,79; claim:1,21,30,32,63,64,71,156; heartbeat:16,19,30; directive:108,136; step5:123 |
| reports/25-cluster-work-view.md | daemon:61,72,78,92; claimer:58,60,70,72,83,95; residency:72,76,102; buildjob:91; poll:73,95; pull:92; claim:58,60,70,72,76,83,92,95; heartbeat:58,98; directive:4,50,86 |
| reports/26-pipeline-stepper.md | buildjob:40; claim:8,12; integrator:16,18,67,68 |
| reports/27-requester-console-and-legacy-fleet.md | daemon:34,169,419; claimer:375,441; poll:34; pull:488; claim:135,375,441; directive:446,489; step5:296,344,506 |
| reports/28-false-completion-audit.md | daemon:20,22,27,102; claimer:48,100,101,196; residency:101; poll:102; pull:228; claim:48,100,101,196 |
| reports/29-multi-project-axis.md | claimer:34,78,79,91,104; residency:34,67,78,120; pull:69,134; claim:34,78,79,91,104 |
| reports/30-init-spec.md | pull:160 |
| reports/31-ns-onboarding-live.md | claimer:26,30,31; residency:26,30; claim:26,30,31 |
| reports/32-false-completion-and-hooks.md | claimer:176,178,188; residency:176,206; poll:35; pull:44,63,108; claim:176,178,181,188,190,193; directive:86 |
| reports/33-tagging-and-sandbox.md | claimer:10,14,77,78; residency:12,61,68,69,72; buildjob:79,82; claim:10,14,36,77,78; directive:120 |
| reports/34-mount-round-trip.md | claimer:22,36,39,43; residency:7,20,26,45,76,80,93; pull:23,69,94; claim:22,36,39,43,79; step5:27,30,31 |
| reports/35-runbook-and-convention-loop.md | daemon:39; directive:94 |
| reports/36-analysis-cursor.md | directive:138,157; step5:154 |
| reports/37-project-axis-and-silent-failures.md | claimer:223,224,227,232,252; residency:226,227,232,234,235; claim:45,223,224,227,232,252; directive:91,151,247 |
| reports/38-history-loop-closed.md | claimer:156; residency:153,157; claim:155,156,157; directive:25,99,153 |
| reports/39-ns-pipeline-first-run-and-my-judgment.md | claimer:88; residency:19,22,115,136; poll:29; claim:29,88,136; directive:48,72; step5:46,48,138 |
| reports/40-pipeline-redesign-decisions.md | daemon:69; claimer:61,118,130,136,171; residency:23,58,69,131,136,160,165,167,171; pull:21,31,38,157; claim:61,118,130,136,171; heartbeat:144,159; integrator:61; step5:23,58,67,145,165,166,167,171 |
| reports/41-live-run-prep-and-refusal-gate.md | pull:27,98; directive:231; integrator:9,33,38,40 |
| reports/42-hooks-delivered-but-dead.md | residency:126,190 |
| reports/43-first-full-run-attempt.md | daemon:84; residency:85; pull:96; claim:84,94; directive:35,37,38; integrator:118 |
| reports/44-dispatch-trigger-and-the-next-gap.md | residency:62; poll:94; pull:133,169; claim:38,39,66,86,94,100,131; heartbeat:65,66,69,185; directive:66,115,185; integrator:91 |
| reports/45-first-full-pipeline-run.md | pull:14; heartbeat:151; directive:13,69 |
| reports/46-canonical-seven-steps.md | residency:154; pull:28,32,131,154,157; integrator:37,39,43,48,49; step5:1,10,92 |
| reports/47-integrator-removed-notice-lives.md | pull:121,251,262,268; directive:85,183,199,291; integrator:1,4,17,24,27,30,39,40,47,62,168,174,188,201,341 |
| reports/48-rounds-triggers-and-the-notice-that-was-already-there.md | pull:117,138; claim:54,57,60; directive:86 |
| reports/49-round-branches-are-never-cleaned.md | 없음 |
| reports/50-first-end-to-end-run.md | pull:87; directive:52; step5:59,206 |
| reports/51-idle-loop-and-the-audit.md | directive:48 |
| reports/52-editor-mcp-notice.md | directive:105,176 |
| reports/53-issues-closed-index-stalled-two-divergences.md | pull:58; directive:26 |
| reports/54-orchestrator-handoff-claude-side-survey.md | pull:213; directive:33,101,184,216; step5:99,167,191 |
| reports/55-orchestrator-handoff-codex-side-probes.md | 없음 |
| reports/56-codex-as-worker-orchestrator.md | directive:15,36,50,58,82 |
| reports/57-codex-to-claude-handover-and-control-surface.md | directive:12; step5:3,16 |
| reports/58-revise-loop-and-work-mode-stamp.md | claim:38,60,87; directive:52 |
| reports/59-live-run-codex-worker-and-revise-loop.md | pull:86,88,110; claim:88,111,122; directive:139 |
| reports/60-async-rewake-and-injection-boundary.md | poll:120; pull:28,31; claim:204; directive:19,70,100,105,119,138,198 |
| reports/61-codex-session0-readiness-and-fallback.md | pull:29; directive:6,7 |
| reports/62-codex-session0-root-cause-and-scope.md | daemon:125,127,129; poll:126; pull:40; claim:126; step5:108,119 |
| reports/63-worker-residency-restored.md | daemon:7,8,39,65,76,82,102,125; worker_daemon:125; claimer:39,41,79; AxWorker:117; residency:1,36,38,42,43,76,79,87,92,106,117,118,119,125,130,136; poll:39; claim:12,39,41,79,102; integrator:126; step5:9 |
| reports/64-dispatch-is-not-a-consent-prompt.md | daemon:76; residency:132; directive:39,54,65,99,125,131,140 |
| reports/65-context-docs-stalled-three-days.md | pull:10,47,58; directive:102 |
| reports/66-live-test-session1-logs-worker-build.md | daemon:53; residency:53,91,130,140,142; claim:18; directive:1,9,32,47,76,89,113 |
| reports/67-codex-finalize-guidance-divergence.md | pull:99,124; step5:24,127 |
| reports/68-review-plan-fix-workflow.md | pull:109; directive:30,96 |
| reports/69-bc250-shutdown-20260919.md | residency:39; claim:39; directive:3,14,57,74,80,84 |
| reports/70-antigravity-review-deploy.md | daemon:23; directive:20 |
| reports/71-r34-verification-close-640.md | residency:13 |
| reports/72-hook-cwd-decoupling.md | residency:119 |
| reports/73-permanent-service-restart-and-codex-redmine.md | residency:22 |
| reports/74-redmine-milestone-management.md | buildjob:194; pull:237; directive:30; step5:320 |
| reports/75-dispatch-unit-recovery.md | pull:48 |
| reports/76-index-only-kimodo-onboarding.md | AxWorker:92; residency:16; pull:92 |
| reports/77-kimodo-followups-and-shadow-skill.md | AxWorker:51; pull:44,49,51; directive:78,79 |
| reports/78-kimodo-code-worker-skill-and-cleanup.md | directive:15 |
| reports/79-worker-failure-notice.md | claim:13 |
| reports/80-failed-work-and-session1-retry.md | 없음 |
| reports/81-worker-file-read-diagnosis.md | residency:157; pull:128; directive:175,177 |
| reports/82-axcluster-workers-and-codex-remote.md | residency:1,4,55,63,65,97; pull:61 |
| reports/83-python-commit-review.md | directive:3 |
| reports/84-r1-python-review-validation.md | claim:16,18,38 |
| reports/85-ns-requester-workflow-reference.md | step5:65 |
| reports/86-master-rag-distributed-readiness.md | directive:7; integrator:29; step5:38 |
| reports/87-axcluster-integration-checks.md | 없음 |
| reports/88-axcluster-first-distributed-work.md | directive:3,46,56; step5:9,22 |
| reports/89-codex-worker-readiness-and-write-probes.md | residency:8 |
| reports/90-r5-indexer-test-isolation-and-deployment.md | step5:89 |
| reports/91-r9-quota-notice-fix.md | directive:28 |
| reports/92-r19-named-xml-helper.md | residency:16 |
| reports/93-spool-recovery-and-frontmatter-repair.md | poll:22; pull:24; claim:19,59; directive:14 |
| reports/94-session-usage-preliminary-findings.md | directive:81 |
| reports/95-layer2-worker-verification-restoration.md | heartbeat:19 |
| reports/96-worker-claude-auth-cache.md | daemon:13; worker_daemon:13 |
| reports/97-codex-quota-event-preservation.md | 없음 |
| reports/98-provision-model-residency-policy.md | residency:1,9,19,39,41,42,53,54; pull:26 |
| reports/99-redmine-update-readback.md | 없음 |
| reports/README.md | daemon:47,52,67,86; claimer:45,48,86; residency:43,45,57,62,64,86,105,121; pull:45,47,67,72,77,85; claim:45,47,48,61,68,82,83,86; heartbeat:68; directive:68,80,87,89; integrator:38,50,65,67,68,70,71; step5:70,81,85 |
| reports/debates/2026-08-18_0040_debate_33_third_endpoint.md | residency:15,54,71,105,118,126; pull:32,77,123 |
| reports/research/2026-10-09-lane-chain-behavior.md | residency:43 |
| reports/research/2026-10-09-worker-agy-delegation-gap.md | directive:10,13,17,19,20,21,25,26,63,64,75,81,83 |
| reports/research/2026-10-11-py-static-verification-804.md | pull:112; integrator:16 |
| reports/research/2026-10-20-837-fix-plan.md | 없음 |
| reports/research/2026-10-21-context-pruning.md | daemon:270,287; pull:116,139; directive:10,12,46,82,84,85,90,97,134,178,179,182,191,290,294; step5:67,69,265,283,284 |
| reports/research/2026-10-31-211-rag-usage-validation-codex-verification.md | 없음 |
| reports/research/2026-10-31-211-rag-usage-validation.md | daemon:64; worker_daemon:64; residency:64; claim:68; directive:20 |
| reports/research/2026-10-31-code-factory-sdd-verification.md | 없음 |
| reports/research/2026-10-31-code-factory-sdd.md | daemon:326; directive:103,120,411,440 |
| scripts/reset-live-test.sh | pull:91,95,96 |
| scripts/sync-clones.sh | pull:9,70,72,74,77 |
| tests/integration/checks.json | daemon:828; worker_daemon:828; residency:148,149; claim:803; integrator:473,474 |
| tests/integration/test_axcluster.py | 없음 |
| worker/README.md | residency:63,70,73,79,81,127,132; heartbeat:29; directive:99 |
