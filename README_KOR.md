# docfleet

**여러 대의 컴퓨터에서 쓰는 AI 에이전트 문서와 메모리를 동기화하는 git 기반 폴더 규약 — 그리고 의존성 없는 CLI.**

[![CI](https://github.com/oh-namgyu/docfleet/actions/workflows/ci.yml/badge.svg)](https://github.com/oh-namgyu/docfleet/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

> 이 문서는 [README.md](README.md) 의 한국어 전문입니다.

---

## 왜 필요한가

같은 AI 코딩 에이전트를 노트북에서도, 데스크톱에서도, 사무실 컴퓨터에서도 씁니다. 각각의 컴퓨터에는 시간이 지나면서 저마다의 맥락이 쌓입니다. 에이전트가 적어 둔 메모, 프로젝트 문서, 메모리 파일, 공통 지침 같은 것들입니다. 그런데 이것들은 저절로 컴퓨터 사이를 옮겨 다니지 않습니다.

그래서 임기응변이 시작됩니다. 폴더를 통째로 복사하고, 어제 적은 메모를 오늘 세션에 붙여 넣습니다. 결국 같은 메모리 디렉터리의 서로 다른 사본 세 개가 생기고 어느 것이 최신인지 알 수 없게 됩니다. 큰맘 먹고 합치려 들면, 애초에 합쳐지면 안 되는 부분(경로, 포트, 그 컴퓨터만의 사정)이 섞여 있었다는 사실을 그제야 발견합니다.

docfleet 은 이것을 **도구의 문제가 아니라 구조의 문제**로 봅니다. 성격이 다른 두 종류의 내용이 한데 섞여 있으니, 먼저 갈라놓아야 합니다.

| 내용 | 위치 | 쓰기 권한 |
| --- | --- | --- |
| "이 컴퓨터가 아는 것" — 로컬 메모리, 컴퓨터별 문서 | `machines/<이름>/` | 그 컴퓨터만 |
| "모든 컴퓨터가 쓰는 것" — 명령, 표준, 규약 | `shared/` | 모든 컴퓨터 |

일단 갈라놓고 나면, 평범한 git 저장소 하나로 둘 다 나를 수 있습니다. 아이디어는 이게 전부입니다. CLI 는 이 규약을 지키기 쉽게, 그리고 실수로 어기기 어렵게 만들기 위해 존재합니다.

## 레이아웃

fleet 저장소는 이런 모양의 평범한 git 저장소입니다.

```
fleet-repo/
├── fleet.json                   # 머신 등록부 — 누가 이 fleet 에 속하는가
├── INDEX.md                     # 생성된 목차 (docfleet index)
├── README.md                    # init 시 없으면 만들어 주는 자리표시자
│
├── machines/                    # 컴퓨터마다 폴더 하나
│   ├── laptop/
│   │   ├── machine.json         # 이 컴퓨터의 링크 선언
│   │   ├── docs/                # laptop 의 문서        ← INDEX.md 에 실림
│   │   └── memory/              # laptop 의 에이전트 메모리 ← 보통 링크의 원본
│   ├── desktop/
│   │   ├── machine.json
│   │   ├── docs/
│   │   └── memory/
│   └── office/
│       └── ...
│
└── shared/                      # 모든 컴퓨터가 읽고 쓰는 영역
    ├── commands/
    └── standards/
```

`machines/laptop/` 은 **노트북에서는** 읽기·쓰기이고 다른 모든 곳에서는 읽기 전용입니다. 그래서 이 폴더는 "지금 데스크톱은 무엇을 알고 있는가?" 에 대한 믿을 만한 답이 됩니다. 어느 컴퓨터에서든 읽을 수 있고, 내 로컬 수정이 그것을 덮어쓸 걱정은 하지 않아도 됩니다.

빈 디렉터리는 `.gitkeep` 파일로 git 에 남습니다. `docfleet` 이 `init` 때 만들어 두고, 그 밖의 모든 곳에서는 무시합니다.

전체 명세 — 모든 경로, 스키마 필드, 이름 규칙, 그리고 권장 문서 계층 규약 — 는 **[docs/structure.md](docs/structure.md)** 에 있습니다.

## 동작 방식

서버 없이, 두 가지 장치로 돌아갑니다.

**1. 복사가 아니라 디렉터리 링크.** 에이전트는 `~/.myagent/memory` 를 읽습니다. docfleet 은 그 경로를 저장소 안 `machines/<이름>/memory/` 를 가리키는 *디렉터리 링크* 로 만듭니다. macOS·리눅스에서는 심링크, 윈도우에서는 디렉터리 정션입니다. 에이전트는 늘 쓰던 경로에 그대로 쓰지만, 바이트는 git 작업 트리 안에 떨어집니다. 동기화 루프도, 파일 감시자도, 잊어버릴 복사 단계도 없습니다. 링크는 항상 디렉터리 단위이고 개별 파일은 걸지 않습니다. 디렉터리 링크는 안쪽 파일이 생기고 이름이 바뀌고 지워지는 동안에도 계속 유효하기 때문입니다.

**2. 유일한 전송 수단은 git.** `docfleet start` 는 fetch 후 rebase 하고, 다른 컴퓨터가 무엇을 바꿨는지 보고합니다. `docfleet close` 는 내 소유 영역만 스테이징해서 커밋하고, rebase 한 뒤 push 합니다. docfleet 서버도, 데몬도, 계정도, 백그라운드 프로세스도 없습니다. git 이 원격에 닿으면 docfleet 도 동작하고, 닿지 못하면 아무 일도 일어나지 않습니다. 원격은 git 이 말을 걸 수 있는 것이면 무엇이든 됩니다. 비공개 저장소도, NAS 위의 폴더도 괜찮습니다.

전부 파이썬 표준 라이브러리만으로 작성되어 있습니다. 런타임 의존성은 앞으로도 없습니다 — [ADR 0004](docs/adr/0004-stdlib-only.md) 참고.

## 빠른 시작

```bash
pip install git+https://github.com/oh-namgyu/docfleet
```

**첫 번째 컴퓨터에서 fleet 을 만듭니다.** docfleet 은 대신 `git init` 을 해 주지 않으므로 저장소를 먼저 만드세요.

```bash
mkdir ~/fleet && cd ~/fleet
git init -b main
git remote add origin git@github.com:you/fleet.git

docfleet init --new . --machine laptop
```

이렇게 하면 `fleet.json`, `machines/laptop/{docs,memory}/`, `machines/laptop/machine.json`, `shared/{commands,standards}/`, 그리고 자리표시자 `README.md` 가 만들어집니다.

**무엇을 링크할지 선언합니다.** `machines/laptop/machine.json` 을 편집하세요.

```json
{
  "machine": "laptop",
  "links": [
    { "source": "memory", "target": "~/.myagent/memory" }
  ]
}
```

`source` 는 머신 폴더 안의 디렉터리, `target` 은 이 컴퓨터의 절대 경로입니다 (`~` 는 확장됩니다).

**이미 가지고 있는 데이터를 흡수합니다.** 에이전트의 메모리 디렉터리는 이미 존재하고 내용도 들어 있습니다. `--adopt` 는 그 디렉터리를 저장소 안으로 **옮기고**, 원래 자리에 링크를 놓습니다.

```bash
docfleet link --adopt
```

`--adopt` 없이 실행하면, 타깃에 있던 디렉터리는 삭제되지 않고 타임스탬프가 붙은 백업으로 옮겨집니다. 어느 쪽이든 이동은 링크를 만들기 **전에** 매니페스트에 기록되며, `docfleet link --restore` 로 되돌릴 수 있습니다.

**공개합니다.** 첫 공개만은 순수 git 으로 합니다. `close` 는 rebase 하고 push 할 업스트림 브랜치가 있어야 하기 때문입니다.

```bash
docfleet index                      # INDEX.md 재생성
git add -A && git commit -m "create fleet"
git push -u origin main             # 업스트림 지정, 최초 1회
```

이후로는 `docfleet close` 가 커밋·rebase·push 를 대신합니다.

**두 번째 컴퓨터에서 합류합니다.**

```bash
git clone git@github.com:you/fleet.git ~/fleet && cd ~/fleet

docfleet init --join . --machine desktop
# machines/desktop/machine.json 을 편집한 뒤:
docfleet link --adopt
docfleet close
```

**매일의 루프**, 그날 앉은 컴퓨터에서:

```bash
docfleet start          # 다른 컴퓨터가 한 일을 끌어오고, 무엇이 바뀌었는지 알려 줌
# ... 작업 ...  에이전트는 평소처럼 링크를 통해 읽고 씁니다 ...
docfleet close -m "API 리팩터링 메모"
```

복사해서 붙여 넣을 수 있는 두 컴퓨터 전체 시나리오는 **[docs/quickstart-two-machines.md](docs/quickstart-two-machines.md)** 에 있습니다.

## 명령

| 명령 | 플래그 | 하는 일 |
| --- | --- | --- |
| `docfleet init --new REPO --machine NAME` | — | 기존 git 저장소에 레이아웃을 만들고 첫 머신을 등록 |
| `docfleet init --join REPO --machine NAME` | — | 클론한 fleet 에 머신을 추가 등록 |
| `docfleet link` | `--adopt`, `--restore`, `--at TS`, `--repo`, `--machine` | `machine.json` 에 선언된 링크를 설치 |
| `docfleet start` | `--repo`, `--machine` | fetch, 업스트림이 앞서 있으면 rebase, 들어온 커밋과 영역을 보고 |
| `docfleet close` | `-m/--message`, `--repo`, `--machine` | 소유 영역을 스테이징·커밋하고 rebase 후 push |
| `docfleet doctor` | `--fix`, `--repo`, `--machine` | 저장소에 7가지 구조 점검을 실행 |
| `docfleet index` | `--repo` | 레이아웃으로부터 `INDEX.md` 를 다시 생성 |

전역 플래그: `--json` (stdout 에 기계가 읽는 출력, 필드별 설명은 [docs/schema.md](docs/schema.md)) 와 `--version`.

`--repo` 의 기본값은 현재 디렉터리에서 위로 올라가며 찾은 가장 가까운 fleet 저장소입니다. `--machine` 의 기본값은 등록된 유일한 머신이며, 머신이 둘 이상이면 반드시 지정해야 합니다.

**종료 코드:**

| 코드 | 의미 |
| --- | --- |
| `0` | 성공 |
| `1` | 실행은 됐지만 끝까지 못 감 — 차단된 `close`, rebase 충돌, doctor 위반, 실패한 링크 항목, 건너뛴 복원 항목 |
| `2` | 환경 또는 설정 오류 — **아무것도 바꾸지 않음** |

`docfleet link` 는 파일시스템을 건드리기 전에 설정 **전체**를 검증합니다. 그래서 잘못된 `machine.json` 은 언제나 깔끔한 종료 코드 `2` 입니다.

## 규칙

하나의 규칙을 세 가지로 풀어 쓰면 이렇습니다.

- **내 머신 폴더** — `machines/<내 이름>/` — 는 내가 읽고 씁니다.
- **다른 모든 머신 폴더**는 나에게 읽기 전용입니다. 얼마든지 읽되, 절대 커밋하지 않습니다.
- **`shared/`** 와 루트 메타데이터 파일(`fleet.json`, `README.md`, `INDEX.md`)은 모두가 쓸 수 있습니다.

`docfleet close` 는 이것을 기억에 맡기지 않고 쓰기 경로에서 강제합니다. `git status` 를 읽어, 바뀐 경로 중 이 머신의 소유 영역 밖에 있는 것이 하나라도 있으면 **스테이징 전에** 멈춥니다.

```
close stopped: these paths are outside the areas you own
  ! machines/desktop/memory/notes.md
```

아무것도 커밋되지 않고, 종료 코드는 `1` 이며, 이를 무시하는 플래그는 없습니다. 해결책은 수정을 내 폴더나 `shared/` 로 옮기는 것입니다. `close` 는 `git add -A` 대신 명시적인 경로 목록만 스테이징하므로, 남의 폴더에 흘린 파일이 슬쩍 묻어 들어갈 일도 없습니다.

`docfleet doctor` 는 같은 상황을 `cross-machine` 점검 항목으로 미리 알려 주되, 일부러 "고치지" 않습니다. 다른 머신 폴더에 있는 커밋되지 않은 변경은 결함이 아니라 누군가의 저장하지 않은 작업이기 때문입니다. 왜 이 강제가 git 훅이 아니라 `close` 안에 있는지는 [ADR 0002](docs/adr/0002-read-only-peer-folders.md) 를 보세요.

## 안전 모델

docfleet 은 실제 디렉터리를 옮깁니다. 그러므로 분명한 약속을 해야 합니다. 그 약속은 **어떤 동작도 사용자가 넣지 않은 데이터를 지우지 않는다** 입니다.

1. **먼저 검증하고, 그다음 실행합니다.** `docfleet link` 는 선언된 모든 항목을 계획하고 검증합니다. 원본이 존재하는지, 타깃이 절대 경로인지, 중복이 없는지, 저장소 안쪽을 가리키지는 않는지 — 파일시스템 호출을 한 번도 하기 전에 확인합니다. 문제가 있으면 종료 코드 `2` 로 중단하고 디스크는 그대로입니다.

2. **밀려난 데이터는 옮겨질 뿐 지워지지 않습니다.** 타깃 경로에 이미 실제 디렉터리가 있으면 그 디렉터리는 *이동*합니다. `~/.docfleet/backup/<repo-id>/<ts>/` 아래의 타임스탬프 백업으로, 또는 `--adopt` 를 쓴 경우 머신 폴더 안으로 들어가 링크의 원본이 됩니다. 게다가 `--adopt` 는 저장소 안 원본에 이미 내용이 들어 있으면 실행을 거부하므로, 이미 추적 중인 데이터를 덮어쓸 수 없습니다.

3. **모든 이동은 링크를 만들기 전에 기록됩니다.** `~/.docfleet/backup/<repo-id>/<ts>/manifest.json` 매니페스트에 항목별 원본, 타깃, 모드(`none`/`backup`/`adopt`), 상태(`pending` → `linked`/`failed`), 백업 위치가 남습니다. 단계마다 디스크로 flush 되므로 중간에 크래시가 나도 읽을 수 있는 기록이 남습니다.

4. **모두 되돌릴 수 있습니다.** `docfleet link --restore` 는 가장 최근 실행을 거꾸로 재생합니다. 링크를 지우고 밀려났던 디렉터리를 제자리로 옮깁니다. `--at TS` 로 타임스탬프를 지정하면 더 이전 실행을 고를 수 있습니다. 그사이 타깃에 새로운 것이 생겼다면 그 항목은 `skipped` 로 보고되고 손대지 않습니다. 나중에 다시 복원하면 그때 재시도합니다. 백업은 자동으로 삭제되지 않습니다.

5. **git 조작은 보수적으로만 합니다.** docfleet 의 어떤 명령도 `git push --force` 나 `git reset --hard` 를 쓰지 않습니다. 충돌한 rebase 는 즉시 abort 되어 브랜치를 원래 상태 그대로 남기고, 손으로 해결하는 절차를 출력합니다. 거절된 push 는 새로 fetch 하고 rebase 한 뒤 정확히 한 번만 재시도합니다. 또 거절되면 커밋은 로컬 브랜치에 그대로 남고, docfleet 은 그 사실을 알려 줍니다.

## 문서

| 문서 | 내용 |
| --- | --- |
| [docs/structure.md](docs/structure.md) | 레이아웃 규약 명세: 경로, 소유권, `fleet.json`/`machine.json` 스키마, 이름 규칙, 문서 계층 |
| [docs/schema.md](docs/schema.md) | 명령별 `--json` 출력 필드, 종료 코드, git 상태 이름 |
| [docs/quickstart-two-machines.md](docs/quickstart-two-machines.md) | 붙여 넣어 따라 하는 시나리오: laptop 이 fleet 을 만들고 desktop 이 합류 |
| [docs/adr/](docs/adr/) | 왜 이렇게 만들었는가 — 4개의 아키텍처 결정 기록 |
| [README.md](README.md) | English |
| [CHANGELOG.md](CHANGELOG.md) | 릴리스 노트 |

## 라이선스

MIT — [LICENSE](LICENSE) 참고.
