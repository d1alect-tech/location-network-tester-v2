# Настройка LNT силами агента

Этот файл можно передать ИИ-агенту с доступом к PowerShell на 64-битной
Windows. По умолчанию агент устанавливает готовую переносимую сборку `v0.1.0`,
проверяет её на синтетических данных и возвращает адрес локальной веб-панели.

Для этого не нужны Git, Python, uv или Node.js. Среда выполнения находится
внутри архива. Все команды ниже выполняются без прав администратора.

Проверка на синтетике не подтверждает работу на чистой машине, установку
WinUSB или связь с физическим осциллографом. LNT поддерживает только Hantek
6022BE. Подготовка устройства описана в конце файла.

## 1. Скачай и проверь релиз

Публичный релиз:
<https://github.com/d1alect-tech/location-network-tester-v2/releases/tag/v0.1.0>

В нём опубликованы четыре файла:

- `LNT-0.1.0-win64.zip`;
- `LNT-0.1.0-win64.zip.sha256`;
- `LNT-0.1.0-corresponding-source.zip`;
- `LNT-0.1.0-corresponding-source.zip.sha256`.

Для обычного запуска нужны только Windows-архив и его `.sha256`. Скачай их во
временный каталог, сверь хеш и распакуй сборку на локальный диск:

```powershell
$ErrorActionPreference = "Stop"
$base = "https://github.com/d1alect-tech/location-network-tester-v2/releases/download/v0.1.0"
$work = Join-Path $env:TEMP ("lnt-v0.1.0-" + [guid]::NewGuid().ToString("N"))
$install = Join-Path $env:LOCALAPPDATA "Programs\LNT-0.1.0"
$zip = Join-Path $work "LNT-0.1.0-win64.zip"
$sidecar = "$zip.sha256"

New-Item -ItemType Directory -Path $work | Out-Null
Invoke-WebRequest "$base/LNT-0.1.0-win64.zip" -OutFile $zip -UseBasicParsing
Invoke-WebRequest "$base/LNT-0.1.0-win64.zip.sha256" -OutFile $sidecar -UseBasicParsing

$line = (Get-Content -LiteralPath $sidecar -Raw).Trim()
if ($line -notmatch '^([0-9a-fA-F]{64})\s+LNT-0\.1\.0-win64\.zip$') {
    throw "Некорректный файл контрольной суммы"
}
$expected = $Matches[1].ToLowerInvariant()
$actual = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) {
    throw "SHA-256 не совпал: ожидался $expected, получен $actual"
}

if (Test-Path -LiteralPath $install) {
    throw "Каталог уже существует: $install"
}
New-Item -ItemType Directory -Path (Split-Path $install -Parent) -Force | Out-Null
Expand-Archive -LiteralPath $zip -DestinationPath $install
$actual
```

Команда должна завершиться с кодом `0` и вывести:

```text
272e6b4dc57ab465f843460a0215662740aed0be54c1905ed9e757566db3dc09
```

Проверь состав распакованного каталога:

```powershell
$required = @(
    "LNT.exe",
    "LNT-cli.exe",
    "_internal",
    "SOURCE.txt",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "dependency-manifest.json",
    "distribution-policy.md",
    "licenses"
)
$missing = @($required | Where-Object { -not (Test-Path -LiteralPath (Join-Path $install $_)) })
if ($missing.Count -ne 0) {
    throw "В архиве не хватает: $($missing -join ', ')"
}
```

Если каталог установки уже существует, не удаляй и не перезаписывай его без
разрешения владельца. Возьми другой путь или остановись.

## 2. Запусти встроенную самопроверку

`LNT.exe` предназначен для обычного запуска. Агент использует `LNT-cli.exe`,
потому что тот возвращает код выхода и пишет результат в консоль.

```powershell
$cli = Join-Path $install "LNT-cli.exe"
& $cli selftest
if ($LASTEXITCODE -ne 0) {
    throw "LNT selftest завершился с кодом $LASTEXITCODE"
}
```

Успех выглядит так:

```text
SELFTEST OK: пик 22385 Гц, циклов 119
```

Частота может отличаться на несколько герц. Проверяй префикс `SELFTEST OK` и
код выхода `0`, а не точное число. Эта команда проверяет встроенный тракт
синтетики и анализа, но не USB-устройство.

В некоторых консолях Windows русские строки отображаются как кракозябры. Файлы
при этом остаются корректным UTF-8. Ориентируйся на код выхода и ASCII-префиксы.

## 3. Проверь рабочий цикл без осциллографа

Создай две синтетические сессии: исходную и с тем же пиком на 12 дБ ниже.

```powershell
$demo = Join-Path $env:TEMP ("lnt-agent-check-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $demo | Out-Null

& $cli simulate --profile bad --out "$demo\syn-bad-seed6022" --seed 6022 --label "before-filter"
if ($LASTEXITCODE -ne 0) { throw "Первая симуляция не удалась" }

& $cli simulate --profile bad-damped --out "$demo\syn-bad-damped-seed6022" --seed 6022 --label "after-filter"
if ($LASTEXITCODE -ne 0) { throw "Вторая симуляция не удалась" }

& $cli analyze "$demo\syn-bad-seed6022"
if ($LASTEXITCODE -ne 0) { throw "Первый анализ не удался" }

& $cli analyze "$demo\syn-bad-damped-seed6022"
if ($LASTEXITCODE -ne 0) { throw "Второй анализ не удался" }
```

После этого в каждом каталоге должны находиться `metrics.json` и
`spectrum.csv`:

```powershell
$outputs = @(
    "$demo\syn-bad-seed6022\metrics.json",
    "$demo\syn-bad-seed6022\spectrum.csv",
    "$demo\syn-bad-damped-seed6022\metrics.json",
    "$demo\syn-bad-damped-seed6022\spectrum.csv"
)
$missing = @($outputs | Where-Object { -not (Test-Path -LiteralPath $_) })
if ($missing.Count -ne 0) {
    throw "Анализ не создал: $($missing -join ', ')"
}
```

API умеет находить сессию и по имени каталога, и по `session_id` из
`manifest.json`. Совпадение этих двух значений больше не требуется.

## 4. Запусти и проверь веб-панель

Запусти сервер отдельным процессом без автоматического открытия браузера:

```powershell
$probe = [System.Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
$probe.Start()
$port = ([Net.IPEndPoint]$probe.LocalEndpoint).Port
$probe.Stop()
$url = "http://127.0.0.1:$port/"
$stdout = Join-Path $work "lnt-ui.stdout.log"
$stderr = Join-Path $work "lnt-ui.stderr.log"
$arguments = 'ui --root "{0}" --port {1} --no-browser' -f $demo, $port
$server = Start-Process -FilePath $cli -ArgumentList $arguments `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru

$health = $null
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    if ($server.HasExited) {
        throw "LNT UI завершился с кодом $($server.ExitCode): $(Get-Content $stderr -Raw)"
    }
    try {
        $health = Invoke-RestMethod "${url}api/health" -TimeoutSec 2
        break
    } catch {
        $health = $null
    }
    Start-Sleep -Seconds 1
}
if ($null -eq $health -or $health.status -ne "ok") {
    throw "LNT UI не ответил за 60 секунд"
}
```

Проверь главную страницу, каталог и спектр:

```powershell
$page = Invoke-WebRequest $url -UseBasicParsing
$catalog = Invoke-RestMethod "${url}api/catalog/sessions?page_size=200"
$spectrum = Invoke-RestMethod "${url}api/sessions/syn-bad-seed6022/spectrum?max_points=512"

if ($page.StatusCode -ne 200) { throw "Главная страница вернула $($page.StatusCode)" }
if (@($catalog.items).Count -lt 2) { throw "В каталоге меньше двух сессий" }
if (@($spectrum.frequency_hz).Count -eq 0 -or @($spectrum.psd_v2_per_hz).Count -eq 0) {
    throw "API вернул пустой спектр"
}

"BUILD_ID=$($health.build_id)"
"URL=${url}#/inspect?a=syn-bad-seed6022&b=syn-bad-damped-seed6022"
"PID=$($server.Id)"
```

Успешная проверка даёт HTTP `200`, непустой спектр и `build_id`, который
начинается с `0.1.0+`. Передай человеку напечатанные `URL` и `PID`. Не называй
это проверкой чистой машины или физического Hantek.

PowerShell сам запрашивает свободный локальный порт. Если другой процесс успел
занять его до запуска LNT, повтори раздел. Если LNT сообщает о другом запущенном
экземпляре, не завершай чужой процесс без разрешения владельца.

## 5. Заверши работу или оставь панель запущенной

Если человек хочет открыть панель, оставь процесс работающим. Если требовалась
только проверка, останови свой процесс и удали созданные временные данные:

```powershell
if ($null -ne (Get-Variable server -ErrorAction SilentlyContinue) -and $null -ne $server) {
    if (-not $server.HasExited) {
        Stop-Process -Id $server.Id
    }
    Wait-Process -Id $server.Id -ErrorAction SilentlyContinue
}
if ($null -ne (Get-Variable demo -ErrorAction SilentlyContinue) -and
    (Test-Path -LiteralPath $demo)) {
    Remove-Item -LiteralPath $demo -Recurse -Force
}
if ($null -ne (Get-Variable demo -ErrorAction SilentlyContinue)) {
    Test-Path -LiteralPath $demo
} else {
    $false
}
```

Последняя команда должна вывести `False`. Каталог `$install` не удаляй: это
установленная программа.

## 6. Передай человеку подготовку Hantek 6022BE

Zadig работает через графическое окно, поэтому этот шаг выполняет человек:

1. Подключить Hantek 6022BE по USB.
2. Открыть Zadig, включить `Options` → `List All Devices` и установить WinUSB
   для устройства с VID `04B4`.
3. После первого захвата устройство может получить VID `04B5`. Тогда установить
   WinUSB и для него.
4. Запустить `LNT.exe`, открыть экран «Захват» и нажать «Проверить устройство».

Backend, `libusb-1.0.dll` и RAM-прошивка уже входят в portable-архив. Ничего
не нужно класть рядом с системным `python.exe`. RAM-прошивка загружается только
при явном захвате; диагностика её не меняет.

Подробнее: [руководство оператора](operator-guide.md) и
[безопасность и восстановление](safety-and-recovery.md).

## 7. Если нужно изменить или пересобрать LNT

Portable-сборка предназначена для запуска, а не разработки. Для работы с кодом
клонируй тег `v0.1.0`:

```powershell
git clone --branch v0.1.0 --depth 1 https://github.com/d1alect-tech/location-network-tester-v2.git
cd location-network-tester-v2
uv sync --locked --python 3.12 --extra ui
uv run --no-sync --python 3.12 lnt selftest
```

Node.js нужен только при изменении frontend. Для точного набора материалов
сборки скачай `LNT-0.1.0-corresponding-source.zip` и его `.sha256`. SHA-256
архива:

```text
7c60b3575aea227228c5cc04ce415dfd966a44b1375d4bbadb12fa4255925454
```

После распаковки следуй корневому `BUILDING.md`. Не заменяй Corresponding
Source обычным Git checkout: архив содержит дополнительные исходники и
материалы сборки.

## Коды выхода CLI

| Код | Значение |
|---|---|
| `0` | команда выполнена |
| `1` | встроенная самопроверка не прошла |
| `2` | неверные параметры, повреждённые данные, занятый порт или второй экземпляр |
| `3` | устройство недоступно |

Ошибка печатается одной строкой в stderr. Для диагностики не скрывай код выхода
и не заменяй его пересказом.
