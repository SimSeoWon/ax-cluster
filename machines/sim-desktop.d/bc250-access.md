# BC-250 추론 노드 접근 — 마스터에서 원격 작업할 때

색인: [`../sim-desktop.md`](../sim-desktop.md) (= 마스터의 `~/CLAUDE.md`)

패스워드 없는 SSH 가 구성돼 있다 (`~/.ssh/id_rsa` → `sim@192.168.0.43`).

```bash
ssh sim@192.168.0.43                                    # shell
curl http://192.168.0.43:11434/api/tags                 # model list
curl http://192.168.0.43:11434/api/generate -d '{...}'  # inference
```

## 원격 작업에서 반복해서 걸리는 두 가지

### 1. 그쪽 `sudo` 는 비밀번호가 필요한데 TTY 가 없다

heredoc 을 SSH 로 파이프하면 **stdin 을 먹어버려** `sudo -S` 가 비밀번호를 못 본다.
스크립트를 먼저 원격에 **쓰고 나서** 실행할 것:

```bash
ssh sim@192.168.0.43 'cat > /tmp/x.sh' << 'EOF'
...script...
EOF
printf '%s\n' "$PW" | ssh sim@192.168.0.43 'chmod +x /tmp/x.sh && sudo -S -p "" /tmp/x.sh'
```

⚠️ 그 보드의 `~/CLAUDE.md` 에는 아직 `pkexec` + 그래픽 polkit 패턴이 적혀 있는데 **그건 낡았다.**
2026-08-05 에 헤드리스(`multi-user.target`)로 전환돼 polkit 대화상자를 띄울 데스크톱 세션이 없다.

### 2. 그쪽 Ollama 포트 11434 는 192.168.0.57 만 받는다

방화벽이 이 머신만 허용한다. 다른 클라이언트를 붙이려면 그 보드에 firewalld rich rule 을 추가해야 한다.

## 🔴 하드웨어 설정을 건드리기 전에

CU 언락 · SMU OC · 거버너 · 부팅 파라미터를 만지기 전에
`sim@192.168.0.43:~/bc250-backup-staging/reports/*.md` 를 읽을 것.
어렵게 얻은 제약이 거기 들어 있고, 그 보드의 `CLAUDE.md` 는 **grep 이 아니라 정독**을 의무화한다
(유사 표현이 걸러져 이미 기록된 걸 재조사한 사고 이력이 있다).
