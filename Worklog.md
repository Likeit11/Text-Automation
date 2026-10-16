# 연결키 기반 문자 수신 분리 — 작업 인계

작성일: 2026-10-16 (한국 시간)

## 이번 세션의 범위와 운영 상태

- 사용자 요청: 휴대폰 번호 대신 사용자가 정한 공통 연결키로 휴대폰과 PC를 연결한다. 서버 한 대로 여러 사용자를 지원한다.
- PC 바로가기 형식은 **`"프로그램.exe" -- 연결키`**다. `--key` 옵션은 사용하지 않는다. `--`와 키 사이에 공백이 필요하다.
- **오늘 업무 중인 실제 서버는 변경·배포·재시작하지 않았다. 이번 변경은 소스 코드와 문서뿐이다.** 현재 사용 중인 앱과 PC 프로그램도 교체하지 않았다.
- `client/dist/`에 있는 기존 exe는 구버전이다. 이번 기능이 들어간 실행 파일로 착각하거나 배포하지 말 것.
- Android APK 및 새 Windows exe는 아직 만들지 않았다. 다음 AI는 먼저 이 문서와 사용자 지시를 읽고 빌드·실기기 검증을 진행한다. 서버 전환은 업무 종료 후 사용자가 요청한 시점에 진행한다.

## 구현된 동작

### PC

```text
"C:\Apps\TextAutomation\쇼핑몰 인증번호(PC).exe" -- YourPrivateKey_123456
```

- Python 실행도 `python pc_client.py -- YourPrivateKey_123456` 형식이다. 키를 바로 위치 인수로 전달하는 것도 허용하지만, `--` 구분자 사용을 권장한다.
- 키는 대소문자를 구분한다. 공백·제어문자 없이 UTF-8 기준 16~128바이트다. 영어·숫자는 한 글자가 1바이트이고 한글은 보통 3바이트다. 자동으로 공백을 제거하지 않으므로 양쪽에 정확히 같은 값을 입력한다.
- 긴 임의의 키를 생성해 사용한다. 위의 공개 예시 키를 실제로 사용하지 않는다. 키를 아는 사람은 같은 채널로 송수신할 수 있다. 계정 가입이나 별도 소유자 인증 기능은 없다.
- 키가 없거나 잘못되면 GUI 오류 창으로 안내한다. 기존 서버를 의도적으로 사용할 때만 `--legacy`로 실행한다.
- 키는 Socket.IO의 `auth.key`로 보내고 URL·로그에는 넣지 않는다. HTTPS 주소만 선택하므로 기존 HTTP 예비 주소로 키가 전달되지 않는다.
- 서버의 `routing_ready` 이벤트(`version=1`, `mode=keyed`) 확인 전에는 코드를 사용하지 않는다. `new_code.routing=keyed`도 확인한다. 구형 서버에 연결되어 전체 방송을 받아도 클립보드에 복사하지 않는다.
- 기존 단일 실행 제한은 유지한다. 한 PC에서 여러 키의 프로그램을 동시에 실행하는 기능은 추가하지 않았다. 같은 키를 사용하는 서로 다른 PC 여러 대는 함께 수신한다.
- 시작프로그램에는 **바로가기만** 두고 exe는 고정된 별도 폴더에 둔다. 기존 exe가 먼저 실행되지 않도록 종료 후 교체한다.

### Android

- `MainActivity` 메인 화면에 연결키 입력란을 연결했다. 서버 주소와 키는 기존 `settings` SharedPreferences에 자동 저장한다(`host_address`, `pairing_key`).
- 누락되어 있던 `activity_main.xml`을 메인 화면의 기존 바인딩과 새 연결키 입력란에 맞춰 추가했다. 기존 `SettingsFragment`에도 연결키 입력 및 저장 버튼을 추가했다.
- `SmsApi.kt`가 실제 SMS와 테스트 메시지의 공통 전송 경로다. HTTPS만 허용하고 리디렉션을 따르지 않는다.
- 민감한 문자를 구형 서버가 전체 방송하지 않도록 먼저 `GET /capabilities`에서 `key_routing_version=1`을 확인하고, 성공했을 때만 문자와 키를 `POST /`로 보낸다. 구형 서버로 자동 전환하지 않는다.
- `SmsBroadcastReceiver`는 서비스 스위치와 키를 확인하고, 분할 SMS를 합쳐 한 번 전송한다. `goAsync()` 결과는 전송 완료 시 반환한다. 두 HTTP 호출은 각각 전체 4초 제한이며 실패 메시지의 클래스명만 로그에 남긴다. 문자 내용·키는 Android 로그에 남기지 않는다.
- 예전 `SmsReceiver`도 같은 구현을 상속하게 바꿨다. 집의 매니페스트에는 **`SmsBroadcastReceiver` 하나만** 등록해 중복 수신을 피한다.
- Android 버전은 `versionCode=5`, `versionName=1.2.0`으로 올렸다.

### 서버

- Socket.IO 연결의 `auth.key`와 SMS JSON의 `key`를 같은 규칙으로 검사한다.
- 키의 SHA-256 해시로 내부 room 이름을 만들며 `socketio.emit(..., to=room)`으로 해당 room에만 전송한다. 원문 키는 DB나 서버 로그에 저장하지 않는다.
- `SMS_ALLOW_LEGACY=1`이 기본값이다. **키 필드가 없는** 기존 앱과 PC만 별도 `legacy` room을 사용한다. 키가 비었거나 잘못된 요청을 legacy로 전환하지 않는다.
- `SMS_ALLOW_LEGACY=0`이면 키 없는 업로드와 PC 연결을 모두 거절한다. 새 앱·PC 전환이 완료되면 0으로 설정한다.
- 기존 DB 테이블과 필터 형식은 그대로다. 마이그레이션이나 데이터 삭제가 없다. 인증번호 추출 규칙과 필터는 기존처럼 서버 전체에서 공유한다.
- 문자 기록에는 사용자별 식별자를 추가하지 않았다. 웹 대시보드는 **운영자 전용 전체 기록**이며 사용자별 열람 화면이 아니다.
- 기존 대시보드가 모든 문자를 노출하고 있었으므로 `SMS_ADMIN_TOKEN` 환경변수로 관리자 인증을 추가했다. `/`, `/export`, 필터 추가·삭제, 문자 삭제가 대상이다. 브라우저 HTTP Basic 사용자명은 `admin`, 비밀번호는 이 환경변수 값이다. 연결키와 별개로 생성·관리한다.
- 관리자 비밀번호 미설정 시 관리 화면은 503, 인증 실패 시 401이다. SMS 업로드와 `/capabilities`는 이 관리자 인증 대상이 아니다. 대시보드 접속에도 HTTPS를 사용한다.
- Flask 디버그 모드를 껐다. DB 마운트 보호(`SMS_REQUIRE_EXISTING_DB=1`)는 기존대로 유지한다.
- 테스트를 위해 `SMS_ASYNC_MODE=threading`을 선택할 수 있다. 운영 기본값은 기존 `eventlet` 그대로다.

## 완료한 검증

- Windows / Python 3.14, Flask 3.1.3, Flask-SocketIO 5.7.0, threading 모드에서 **unittest 14개 통과**.
- 서로 다른 키 수신 차단, 같은 키 여러 PC 동시 수신, legacy 분리, legacy 차단 옵션, 잘못된 키 거절, 재연결 후 room 변경, 기능 확인 응답, 기존 DB·필터 보존, 관리자 인증, CLI 인수 및 HTTP 예비 주소 제외를 검증했다.
- Android APK 빌드·실기기 SMS 수신, Windows 새 exe 빌드·실제 바로가기 실행, 운영 Python 3.9/eventlet 컨테이너 환경 검증은 **미완료**다.

다른 PC에서 테스트를 재현하는 예시(PowerShell, 저장소 루트):

```powershell
python -m venv .venv-tests
.\.venv-tests\Scripts\python.exe -m pip install Flask Flask-SocketIO pandas
.\.venv-tests\Scripts\python.exe -m unittest discover -s tests -v
```

테스트는 임시 DB만 사용한다. 운영 서버나 실제 문자 데이터를 사용하지 않는다.

## 집에서 이어 할 작업

### 1. Android 빌드 환경과 누락 파일 복원

이 저장소에는 `app/build.gradle.kts`는 있으나 다음 기본 파일이 없다. 단순히 SDK 설치만으로 바로 빌드할 수 있는 상태가 아니다. 집의 원본 Android 프로젝트가 있으면 먼저 복원하고 이번 코드와 합친다.

- 루트 `settings.gradle(.kts)`, `build.gradle(.kts)`, Gradle wrapper 및 관련 설정.
- `app/src/main/AndroidManifest.xml`.
- 기존 테마·문자열 등 리소스 및 서명 설정. 기존 Kotlin/XML이 참조하는 리소스도 확인한다.

JDK 17 / compileSdk 34 설정을 기준으로 Gradle과 Android Gradle Plugin 조합을 맞춘다. 매니페스트에는 기존과 동일한 앱 ID, `MainActivity`, 인터넷·SMS 수신·알림·배터리 최적화 관련 권한 및 SMS receiver를 복원한다. SMS receiver는 하나만 등록한다. 키가 앱 백업으로 복사되지 않도록 백업 설정도 검토한다.

이번에 추가한 메인 레이아웃은 기존 `MainActivity`의 바인딩을 충족하는 기본 화면이다. 집의 원본 UI를 복원할 경우 `pairingKeyInput` 입력란 및 저장 로직을 유지한다. APK 업데이트는 기존 서명키를 사용한다. 기존 앱을 삭제하기 전에 설정 보존 필요 여부를 확인한다.

### 2. Windows 새 exe 빌드

- `client/config/settings.example.py`를 `client/config/settings.py`로 복사하고 **문자 서버의 실제 HTTPS 주소**를 입력한다. 이 파일은 Git에서 제외된다.
- 이 작업 PC에는 실제 `config/settings.py`가 없으므로 서버 주소를 임의로 넣은 exe는 만들지 않았다.
- `client/requirements.txt`와 PyInstaller를 빌드용 가상환경에 설치한다.
- `client` 디렉터리에서 `python -m PyInstaller --clean "쇼핑몰 인증번호(PC).spec"` 실행. spec의 예전 개인 PC 절대 경로는 제거했다.
- 새 exe를 별도 폴더에서 검증한 뒤 배포한다. 현재 Git에 추적 중인 `client/dist`와 `client/build`의 구버전 산출물은 이번 작업에서 변경하지 않았다. 소스가 업데이트됐다고 기존 바이너리를 새 버전으로 안내하지 않는다.
- 실제 `.lnk` 바로가기를 만들어 `-- 키값` 전달, 누락·오류 키 안내, 중복 실행 방지, 클립보드 복사를 확인한다. 아직 새 서버가 아니면 keyed 수신은 준비되지 않는 것이 정상이다.

### 3. 테스트 환경에서 종단 간 확인

실제 운영 전 별도 테스트 서버에서 새 APK와 exe를 연결한다.

1. 서버 필터에 `[Test]`를 넣고, A 휴대폰/A PC에 키 A, B PC에 키 B를 설정한다.
2. A 앱의 연결 테스트에서 A PC만 `200000`을 받는지 확인한다. 같은 키의 다른 PC도 함께 수신해야 한다.
3. B 앱에서도 반대 방향을 확인한다. 키 없는 기존 PC에는 keyed 코드가 전달되면 안 된다.
4. 실제 SMS와 긴 분할 SMS, 백그라운드 상태, 네트워크 재연결, 앱 재시작 후 키 저장을 확인한다.
5. 연결 테스트 HTTP 성공은 서버 접수 성공이다. 필터 불일치나 PC 오프라인까지 성공을 보장하지 않는다.
6. 관리자 로그인 없이 기록 조회·Excel 내보내기·삭제가 불가능한지 확인한다.
7. 현재 운영과 같은 Docker/Python 3.9/eventlet 조합으로 빌드·기동 및 Socket.IO 수신을 확인한다. 로컬 threading 테스트만으로 운영 환경 검증을 대신하지 않는다.

### 4. 업무 종료 후 서버 적용

**이번 세션에서는 수행하지 않았다. 업무 종료 뒤, 후속 세션에서 사용자가 지정한 배포 시점에 진행할 작업이다.**

기존에 확인한 문자 서비스 위치:

- Proxmox LXC **CT 102**.
- 소스/빌드 컨텍스트: **`/DockerSystem/SMS-Server`**.
- Docker 컨테이너: **`my-sms-server`**, 이미지: `sms-server:latest`.
- DB bind mount: `/DockerSystem/SMS-Server/sms_data` → `/app/data`.
- 컨테이너 5000 → LXC 호스트 8312. HTTPS는 현재 프록시 설정에서 문자 서비스 도메인을 확인한다. Product Registration 서비스와 혼동하지 않는다.
- 배포 전 서버 파일이 여전히 같은지 다시 확인한다. 이전 점검 때는 `SMS_REQUIRE_EXISTING_DB=1`, DB 마운트와 DB 무결성 검사가 정상이었다.

연결은 사용자 AGENTS.md의 Vault 흐름을 따른다. `https://ssh.netras.org`는 SSH 호스트가 아니라 Vault 웹 엔드포인트다. 저장소 루트 `SSH Vault.lock`의 두 줄로 HTTP Basic 인증 후 `/access.b64` 응답을 해독하고 `access`의 정보로 Paramiko 연결한다. 개인키는 메모리 안에서만 사용한다. Vault 자격증명·해결된 SSH 접속 정보·개인키는 출력하거나 파일/Git에 저장하지 않는다. 이 작업 저장소에는 Vault 파일이 없었으므로 집의 안전한 기존 연결 설정을 준비한다.

배포 절차:

1. 현재 소스 해시, 컨테이너 상태, 이미지 ID, 포트, 마운트, 재시작 정책과 기동 설정을 확인한다. `docker inspect` 전체/환경변수에는 비밀값이 있을 수 있으므로 그대로 로그나 채팅에 출력하지 않는다.
2. 영향을 받는 소스·기동 설정 및 SQLite DB를 타임스탬프 백업한다. DB는 SQLite backup API 등 일관성 있는 방식으로 백업한다. 백업과 관리자 비밀번호 파일은 Docker 빌드 컨텍스트 **밖의 안전한 경로**에 보관한다. 기존 이미지도 롤백용 태그로 남긴다.
3. SFTP로 Proxmox 호스트 임시 경로에 업로드한 뒤 `sudo pct push 102 <임시 파일> /DockerSystem/SMS-Server/<파일>`로 반영한다. 서버 소스에서는 `main.py`가 빌드 컨텍스트 바로 아래에 있다. 저장소의 `Server` 폴더 전체를 중첩 복사하지 않는다.
4. 충분히 긴 별도 `SMS_ADMIN_TOKEN`을 안전하게 설정하고, 기존 `SMS_REQUIRE_EXISTING_DB=1`과 DB bind mount를 반드시 유지한다. 기존 앱을 잠시 유지한다면 `SMS_ALLOW_LEGACY=1`로 시작한다. 비밀값을 저장소나 명령 출력에 남기지 않는다.
5. `sudo pct exec 102 -- <command>` 흐름으로 이미지 빌드 및 필요한 컨테이너 교체를 수행한다. **DB 초기화, `init-db`, DB 삭제, 저장소 없는 새 컨테이너 실행은 하지 않는다.**
6. 컨테이너 상태, 소스 해시, 관련 로그, DB 마운트, DB 무결성을 확인한다. 실제 HTTPS 문자 서비스의 `/capabilities`, 관리자 로그인, 새 앱/PC의 키별 수신, 필요 시 기존 앱/PC 수신을 확인한다. 루트 URL은 관리자 인증 없이 401이 나오는 것이 정상이다.
7. 모두 전환한 뒤 `SMS_ALLOW_LEGACY=0`으로 변경하고 키 없는 요청 거절을 확인한다. 새 APK/PC와 구형 서버를 섞어 새 기능이 동작한다고 안내하지 않는다.

롤백: 보관한 기존 이미지·기동 설정·소스로 기존 컨테이너를 복원하고 동일한 DB 마운트를 유지한다. DB 스키마 변경이 없으므로 일반적인 코드 롤백에 DB 복원은 필요하지 않다. DB를 과거 백업으로 되돌리면 배포 후 새 문자가 사라질 수 있으니 임의로 복원하지 않는다.

## 이번 범위에 포함하지 않은 기능

사용자 계정/휴대폰 번호 인증, 사용자별 서버 필터·웹 화면·기록 분리, 오프라인 메시지 재전송, 키 분실 복구·회수, PC 한 대에서 여러 키 동시 실행은 구현하지 않았다. 현재 연결키는 공유 비밀 기반 라우팅이며, 웹 전체 기록은 운영자만 볼 수 있다. 서버 저장소의 문자 본문은 기존처럼 SQLite에 평문으로 보관된다.
