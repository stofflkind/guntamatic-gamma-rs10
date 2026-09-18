# FT232R RS485 Protocol Analyzer

Softwaredefinierter, passiver RS485-Protokollanalysator für die
Guntamatic/Gamma-RS10-Kommunikation.

## Hardware

- FTDI FT232RL USB-UART
- ST3485E RS485-Transceiver
- Raspberry Pi
- passiver Betrieb am RS485-Bus

## Bus und Rohabtastung

- Bus: 9600 Baud
- FT232R Bit-Bang-Rohabtastung
- ca. 307200 Samples/s
- ca. 32 Samples pro Bit
- relevantes Eingangssignal: D1/RXD

## Integration im Repository

Die Werkzeuge des ursprünglichen FT232R-Analyzer-Projekts sind in das
Repository `guntamatic-gamma-rs10` integriert.

Wichtige Verzeichnisse:

- `tools/` – Capture-, Decoder- und Analysewerkzeuge
- `experiments/` – Vergleichs- und Versuchsskripte
- `parser/gamma_parser.py` – semantischer Gamma-Protokollparser
- `PROTOCOL.md` – aktueller Stand der Protokolldokumentation
- `tests/` – automatisierte Parser-Tests

Rohcaptures und erzeugte Binärdateien werden nicht als Bestandteil des
Quellcodes benötigt und sollten nicht unnötig in Git aufgenommen werden.

## Verarbeitungskette

    RS485
      |
      v
    ST3485E
      |
      v
    FT232RL D1/RXD
      |
      v
    ft232_capture
      |
      v
    FT232R-Rohsamples
      |
      v
    ft232_crc_frames.py
      |
      v
    CRC-gültige Gamma-Frames
      |
      v
    parser/gamma_parser.py
      |
      v
    semantisch decodierte Telegramme

## FT232R-Rohcapture

Das C-Programm `tools/ft232_capture.c` dient zur passiven Rohabtastung
des FT232R.

Zum Kompilieren wird `libftdi1-dev` benötigt.

Beispiel:

    gcc -Wall -Wextra -o ft232_capture tools/ft232_capture.c -lftdi1

Capture:

    ./ft232_capture capture.bin

Das Programm verwendet den FT232R im Bit-Bang-Modus mit allen Leitungen
als Eingänge. Dadurch ist der Analyzer für passive Beobachtung ausgelegt.

## CRC-gültige Gamma-Frames extrahieren

`tools/ft232_crc_frames.py` decodiert den 9-Bit-UART-Datenstrom eines
FT232R-Rohcaptures und extrahiert CRC-gültige Gamma-Telegramme.

Beispiel:

    python tools/ft232_crc_frames.py capture.bin gamma_frames.bin

## Semantische Auswertung

Die semantische Auswertung erfolgt mit dem gemeinsamen Parser:

    parser/gamma_parser.py

Beispiel für TYPE 2806:

    python parser/gamma_parser.py \
        gamma_frames.bin \
        --input-format binary \
        --normalize none \
        --type 2806 \
        --show

## Vergleichswerkzeuge

Für kontrollierte Experimente stehen unter `experiments/` unter anderem
folgende Werkzeuge zur Verfügung:

- `ft232_compare_2806.py`
- `ft232_compare_8001.py`
- `ft232_compare_urlaub.py`

Die Capture-Dateien werden als Kommandozeilenargumente übergeben.

Beispiel:

    python experiments/ft232_compare_2806.py capture_a.bin capture_b.bin

## Verifizierter Test

Ein kontrollierter Capture-Test mit Betriebsart Urlaub ergab:

- 40 CRC-gültige Gamma-Frames
- TYPE 2806 korrekt erkannt
- Betriebsart Urlaub: `0x24`
- aktiver Sollwert: `10.0 °C`
- Urlaubsende: `15.10.2026`

Damit wurde die komplette Verarbeitungskette

    Rohcapture -> 9-Bit-Decodierung -> CRC -> Gamma-Parser

praktisch verifiziert.

## Protokolldokumentation

Der jeweils aktuelle Wissensstand befindet sich in:

    PROTOCOL.md

Neue Feldzuordnungen und kontrollierte Experimente sollten dort
dokumentiert werden.

## Sicherheit

Der Analyzer ist für passive Beobachtung vorgesehen.

Keine Telegramme senden und den RS485-Bus nicht aktiv treiben, solange
dies nicht ausdrücklich Teil eines kontrollierten Experiments ist.
