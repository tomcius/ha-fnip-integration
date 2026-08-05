# FutureNow FNIP — integracja Home Assistant

Integracja Home Assistant (domain `fnip`) dla sterowników **FutureNow FNIP**
(TCP, port 7078) — konfigurowana w pełni przez UI, z obsługą zarówno wyjść
(światła/przełączniki/rolety), jak i **odczytu wejść** (przyciski/czujniki
fizyczne).

Warstwa protokołu (`custom_components/fnip/fnip/`) jest przeniesiona z
`fnip_mcp_server` (prywatne repo lokalne) — asynchronicznego klienta FNIP już
przetestowanego na żywym sprzęcie (FNIP-6x2AD, FNIP-12xIO).

## Obsługiwane moduły (v1)

| Typ | Model | Wyjścia | Wejścia | Poziom |
|-----|-------|---------|---------|--------|
| REL | FNIP-8x10A / FNIP-8x16A | 8 (light/switch — wybór w UI) | 8 | — |
| IO  | FNIP-12xIO | 13 (light/switch — wybór w UI) | 12 (+ rezystancja) | — |
| DIM | FNIP-6x2AD | 6 (light, brightness) | 6 | 0–100 |
| PWM | FNIP-12xPWM | 12 (light, brightness) | 12 | 0–255 |
| SH  | FNIP-4xSH | 4 (cover) | 8 | 0–100 (pozycja) |

MZT (silniki) i RGB&010 — planowane w kolejnym etapie, gdy będzie sprzęt do
weryfikacji (protokół udokumentowany, ale brak przetestowanych komend).

## Instalacja

### HACS

HACS → ⋮ → Custom repositories → dodaj ten adres repo (kategoria: Integration)
→ zainstaluj → restart Home Assistant → Settings → Devices & Services →
Add Integration → **FutureNow FNIP**.

### Ręcznie

Skopiuj `custom_components/fnip/` do `<config>/custom_components/fnip/`,
zrestartuj HA, dodaj integrację jak wyżej.

## Konfiguracja

Kreator prosi o adres IP i port modułu (domyślnie 7078), automatycznie
wykrywa typ urządzenia (`GETMTYPE`/`GETMAC`), a następnie pozwala nazwać
każdy kanał i — dla modułów REL/IO — wybrać, czy dane wyjście ma być
`light` czy `switch`. Wszystko można później zmienić przez **Configure**
na wpisie integracji (options flow).

## Architektura

Brak pollingu — moduł FNIP sam wysyła powiadomienia push o zmianach stanu;
encje subskrybują je bezpośrednio (`iot_class: local_push`). Jedno
urządzenie HA (device registry) na fizyczny moduł FNIP.
