# Guntamatic Gamma RS10 Protokoll

[English](README.md) \| **Deutsch**

Inoffizielles Reverse Engineering und Dokumentation des RS485-Protokolls
der **Gamma RS10** Raumstation in Verbindung mit einer
**Fischer/Guntamatic BIOSTAR 15** Pelletheizung.

Das Projekt basiert auf passiven Busmitschnitten, CRC-Prüfung, direktem
Vergleich mit den am RS10 angezeigten Werten, kontrollierten
A/B/A-Experimenten sowie rohen FT232R-Bitmitschnitten.

> **Projektstatus:** In Arbeit. Rahmenformat, CRC, mehrere zyklische
> Werte, Wochenprogramme, Teile des Parameterblocks und wichtige Aspekte
> der Buszugriffsschicht mit neunten Bit sind bereits entschlüsselt.
> Unbekannte Felder und noch nicht geklärte Busmechanismen werden
> bewusst von bestätigten Ergebnissen getrennt.

## Testsystem

-   Fischer/Guntamatic BIOSTAR 15 Pelletkessel
-   Installation November 1999
-   Gamma RS10 Raumstation
-   RS10 Artikelnummer `9550901000`
-   physischer RS10-Busadresswahlschalter `3`
-   Zentralregler vermutlich **Gamma 2B**; Typenschild noch zu
    bestätigen
-   RS485, 9600 Baud
-   passive Aufzeichnung mit FTDI FT232R USB/RS485-Adapter
-   zusätzliche asynchrone FT232R-Bitbang-Aufzeichnung mit etwa 307.200
    Samples/s

Bei anderen Regler- oder Firmwareversionen können die Ergebnisse
abweichen.

## Dokumentation

-   [`PROTOCOL.md`](PROTOCOL.md) --- ausführliche technische
    Protokolldokumentation, Belege, Buszustandsmodell, dekodierte Felder
    und offene Fragen
-   [`docs/experiments.md`](docs/experiments.md) --- kontrollierte
    Experimente und Nachweise
-   [`docs/ft232r-analyzer.md`](docs/ft232r-analyzer.md) --- passiver
    FT232R-Rohprotokollanalysator
-   [`tools/extract_4002_timeline.py`](tools/extract_4002_timeline.py)
    --- zeitstempelbasierte Extraktion CRC-gültiger
    Warmwasser-Temperaturtelegramme

Die Evidenz wird bewusst konservativ eingestuft:

  -----------------------------------------------------------------------
  Status                              Bedeutung
  ----------------------------------- -----------------------------------
  `CONFIRMED`                         durch kontrolliertes Experiment
                                      oder direkten Displayvergleich
                                      bestätigt

  `LIKELY`                            starke Hinweise, aber kontrollierte
                                      Bestätigung noch unvollständig

  `UNKNOWN`                           noch nicht zuverlässig
                                      identifiziert
  -----------------------------------------------------------------------

In `PROTOCOL.md` werden bei Bedarf weitere Abstufungen wie manuell
bestätigt oder stark unterstützt verwendet.

## Physikalisches Protokoll

Beobachtetes Format auf der Leitung:

``` text
RS485
9600 Baud
Startbit
8 Datenbits, LSB zuerst
protokollrelevantes neuntes Bit
Stoppbit
```

Frühere Mitschnitte wurden als gewöhnliches 8N1 behandelt.
Paritätsbewusste und rohe FT232R-Aufzeichnungen zeigen, dass dies
unvollständig ist: Das zusätzliche Bit trägt Protokollzustand.

Aktuelles Beobachtungsmodell:

``` text
Slot-/Scan-Ankündigungsbytes     Bit 9 = 1
normale 0x82 ... 0x03 Frames     Bit 9 = 0
beobachtetes 0x06 Handshakebyte  Bit 9 = 0
```

Frames beginnen mit `0x82` und enden mit `0x03`. Die Prüfsumme ist
**CRC-16/KERMIT** und wird Little-Endian übertragen. Das genaue
Rahmenformat und die CRC-Abdeckung stehen in
[`PROTOCOL.md`](PROTOCOL.md).

## Aktuelle Interpretation der Teilnehmer

Die beiden Bytes nach `0x82` werden historisch als Source und
Destination bezeichnet. Ihre exakte physische Bedeutung ist jedoch noch
nicht vollständig bewiesen.

  ----------------------------------------------------------------------------
  Adresse                 Aktuelle Interpretation      Status
  ----------------------- ---------------------------- -----------------------
  `0x23`                  RS10-Protokollteilnehmer     stark unterstützt

  `0x10`                  zentraler Gamma-Regler       stark unterstützt

  `0x20`                  logisches Datenziel bzw.     `UNKNOWN`
                          Empfängerrolle               

  `0xAA`                  service-/broadcastähnliche   `UNKNOWN`
                          Adresse                      

  `0xFF`                  spezielle/startbezogene      `UNKNOWN`
                          Adresse im beobachteten      
                          Verkehr                      
  ----------------------------------------------------------------------------

Aus einem passiven Zweidrahtmitschnitt lässt sich nicht zweifelsfrei
bestimmen, welches physische Gerät jedes einzelne Byte gesendet hat.
Insbesondere wird `0x20` derzeit **nicht** der Kesselplatine zugeordnet.

## Frame- und Request/Data-Beispiele

Vier zyklische Request/Data-Paare werden konsistent beobachtet:

``` text
23 -> 10 TYPE0101  -> ca. 27,7 ms -> 10 -> 20 TYPE8001
23 -> 10 TYPE0102  -> ca. 27,7 ms -> 10 -> 20 TYPE4002
23 -> 10 TYPE0105  -> ca. 27,7 ms -> 10 -> 20 TYPE1005
23 -> 10 TYPE0106  -> ca. 27,7 ms -> 10 -> 20 TYPE2806
```

Erfolgreiche Buszugriffszyklen zeigen außerdem reproduzierbare
Marker-/Handshake-Sequenzen mit dem neunten Bit. Die genaue
Senderzuordnung und Semantik wird noch untersucht.

## Ausgewählte dekodierte Werte

  ---------------------------------------------------------------------------------
  Feld              Bedeutung                   Kodierung         Status
  ----------------- --------------------------- ----------------- -----------------
  `2806 P2`         Raum-Isttemperatur          raw / 2 °C        `CONFIRMED`

  `2806 P4`         aktiver Raum-Sollwert       raw / 2 °C        `CONFIRMED`

  `2806 P7`         Betriebsart                 enum              `CONFIRMED`

  `2806 P10`        Warmwasser-Sollwert         raw / 2 °C        `CONFIRMED`

  `2806 P37`        Tag-Raumsollwert            raw / 2 °C        `CONFIRMED`

  `2806 P38`        Nacht-Raumsollwert          raw / 2 °C        `CONFIRMED`

  `2806 P39..P41`   Enddaten zeitbegrenzter     modusabhängig     `CONFIRMED`
                    Betriebsarten                                 

  `2004 P2`         Außentemperatur             raw / 2 - 52 °C   `CONFIRMED`

  `2004 P32`        Gamma-seitige               raw / 2 °C        `LIKELY`
                    Kessel-/Vorlauftemperatur                     

  `4002 P08`        Warmwasser-Isttemperatur    raw / 2 °C        `CONFIRMED`

  `8014 param#35`   Heizkennlinien-Steilheit    raw / 20          `CONFIRMED`

  `8014 param#81`   Legionellen-WW              0=Aus, 1..7       Feld bestätigt
                    Wochentag/Aus               Wochentag         

  `8014 param#30`   gewähltes                   1..3              `CONFIRMED`
                    Kessel-Wochenprogramm                         
  ---------------------------------------------------------------------------------

Die vollständige Dekodierungsübersicht wird in
[`PROTOCOL.md`](PROTOCOL.md) gepflegt.

## Betriebsarten

Bestätigte Werte von `2806 P7`:

``` text
0x00  Automatik
0x03  Heizen
0x04  Reduziert
0x13  Party bis zu einer bestimmten Uhrzeit
0x14  Abwesend bis zu einer bestimmten Uhrzeit
0x24  Urlaub bis zu einem bestimmten Datum
```

Die Endfelder `P39..P41` werden je nach Betriebsart unterschiedlich
verwendet. Bei Abwesend enthalten sie beispielsweise
Minute/Stunde/Wochentag, bei Urlaub Tag/Monat/Jahr.

## Wochenprogramme und Parametertransport

Beim Öffnen der RS10-Programmierebenen werden kurze Requests und
anschließend größere Datenblöcke übertragen. Bestätigte Zuordnungen:

``` text
010E / 800E   Kessel-Wochenprogramm 1
010F / 800F   Kessel-Wochenprogramm 2
0110 / 8010   Kessel-Wochenprogramm 3
0112 / 8012   Warmwasser-Wochenprogramm
0114 / 8014   RS10 Parameter-/Konfigurationsblock
```

Die Wochenprogrammblöcke enthalten sieben Tage mit jeweils bis zu drei
Zeitfenstern. Die Zeitfelder sind BCD-kodiert.

## Warmwasser-Isttemperatur und Legionellenbeobachtung

`4002 P08` ist als tatsächliche Warmwasser-/Speichertemperatur
bestätigt:

``` text
Temperatur = P08 / 2 °C
```

Bei einer kontrollierten Beobachtung mit `Legionellen-WW = 4`
(Donnerstag) am 17.09.2026 zeigte sich eine deutliche
Hochtemperaturphase ungefähr zwischen 21:00 und 22:00 Uhr. Der
Gamma-seitige Wert `2004 P32` stieg auf ungefähr 80--82 °C, während die
Speichertemperatur langsamer anstieg und ihr beobachtetes Maximum von
**69,5 °C um 22:41:19 Uhr** erreichte.

Das ist das beobachtete Maximum dieses Zyklus und **kein Nachweis für
einen fest eingestellten Legionellen-Sollwert von 69,5 °C**.

Während der Hochtemperaturphase wechselte das unbekannte Feld `2004 P17`
auf `0xA2`. Das ist derzeit nur eine starke Korrelation; die genaue
Bedeutung bleibt `UNKNOWN`.

## Wichtige Erkenntnis zur `0xFF`-Normalisierung

Der normale FTDI/RS485-Aufzeichnungspfad des Testsystems zeigt
separatorartige `0xFF`-Bytes zwischen logischen Bytes. Ein blindes
Entfernen aller `0xFF` ist nicht sicher, weil `0xFF` auch ein echtes
Nutzdatenbyte sein kann.

`TYPE 4002` lieferte den entscheidenden Nachweis: Das Telegramm enthält
an P03 ein echtes logisches `0xFF`. Eine blinde
`strip-ff`-Normalisierung zerstört dadurch den Frame und die CRC-Prüfung
schlägt fehl.

Der Parser verwendet deshalb eine **verlustfreie, framebewusste
`deinterleave-ff`-Normalisierung** und erhält echte Nutzdatenwerte. Das
Interleaving wird als Eigenschaft des verwendeten
Capture-/Interface-Pfads betrachtet, nicht als Bestandteil des
Gamma-Protokolls.

## Werkzeuge

Das Repository enthält unter anderem:

-   semantischen Gamma-Frameparser mit CRC-Prüfung
-   Werkzeuge für rohe FT232R-Bitbang-Aufzeichnung und Dekodierung des
    neunten Bits
-   Timing-Analysatoren für Slot-/Handshake-Untersuchungen
-   Skripte für kontrollierte Experimente
-   `extract_4002_timeline.py` zur zeitgestempelten Rekonstruktion
    CRC-gültiger Warmwasser-Istwerte

Der rohe FT232R-Analysator arbeitet passiv: Alle FT232R-Bitbang-Pins
sind als Eingänge konfiguriert.

## Reverse-Engineering-Methode

Wo immer möglich werden Felder durch kontrollierte A/B/A-Tests bestimmt:

``` text
Einstellung A -> Aufzeichnung
Einstellung B -> Aufzeichnung
Einstellung A -> Aufzeichnung
```

Es wird jeweils nur ein sichtbarer Parameter absichtlich verändert.
Dynamische Sensorwerte werden direkt mit der RS10-Anzeige verglichen.
Hypothesen werden ohne entsprechende Evidenz nicht als bestätigt
dokumentiert.

## Aktuelle Forschungsziele

1.  Senderzuordnung und genaue Bedeutung von `06`, `A3`, `90`, `FC`,
    `FF`, `7D` und dem beim Start einmal beobachteten `C0` bestimmen.
2.  Das passive Buszustandsmodell anhand der gemessenen
    Bit-9-Zeitabläufe weiter verfeinern.
3.  Die genaue Bedeutung des Adressfelds B, insbesondere `0x20`,
    bestimmen.
4.  Erklären, warum identische `2806`-Nutzdaten sowohl als `10 -> 20`
    als auch als `23 -> 20` auftreten.
5.  Den physischen Typ des Zentralreglers bestätigen; derzeitige
    Hinweise sprechen für Gamma 2B.
6.  Das minimale Busverhalten bestimmen, das für eine RS10-Emulation
    erforderlich ist.
7.  Unbekannte Felder in `2004`, `8014`, `4002`, `1005` und `2806`
    weiter dekodieren.

## Beiträge willkommen

Mitschnitte und kontrollierte Beobachtungen anderer
Gamma-/RS10-Installationen sind besonders willkommen.

Hilfreiche Beiträge sollten möglichst enthalten:

-   Regler- und Raumstationsmodell
-   Firmware-/Versionsinformationen
-   Busadress-/Wahlschalterstellung
-   exakt geänderten Parameter
-   Vorher-/Nachher-Werte
-   CRC-gültige Telegramme
-   Angabe, ob die Beobachtung reproduziert wurde

Vergleiche mit Gamma 2B, 23B, 233B oder anderen RS10-Installationen
könnten helfen, installationsspezifisches Verhalten von allgemeinen
Protokollregeln zu unterscheiden.

Bitte Messergebnisse und Hypothesen klar voneinander trennen.

## Sicherheit

Das Projekt basiert überwiegend auf **passivem, nur lesendem
Monitoring**.

Die 12-V-Versorgung des RS10 darf nicht mit einem Versorgungspin eines
USB-Adapters verbunden werden. Es sollten keine beliebigen Frames an
einen Heizungsregler gesendet werden, solange deren Wirkung und die
Busarbitrierung nicht verstanden sind. Heizungsanlagen sind
sicherheitsrelevante Systeme; Experimente dürfen die eigenen
Sicherheitsfunktionen des Kessels weder umgehen noch beeinträchtigen.

Aktive Experimente in diesem Projekt werden isoliert und bewusst
konservativ durchgeführt.

## Vorarbeiten

Dieses Projekt baut auf früheren Community-Arbeiten zum Reverse
Engineering der Gamma-Heizungssteuerung auf, darunter die
`bogeyman/gamma`-Protokolldokumentation und Diskussionen auf
mikrocontroller.net.

Die in diesem Repository als `CONFIRMED` gekennzeichneten Ergebnisse
beruhen auf eigenen Messungen und kontrollierten Experimenten am
beschriebenen Testsystem.

## Lizenz

Siehe [`LICENSE`](LICENSE).

## Haftungsausschluss

Dies ist ein inoffizielles Reverse-Engineering-Projekt. Es besteht keine
Verbindung zu oder Unterstützung durch Guntamatic, Fischer oder den
Hersteller der Gamma RS10.

Die Dokumentation kann Fehler enthalten und muss nicht auf andere
Regler- oder Firmwareversionen übertragbar sein. Nutzung der
Informationen, Software und Hardwareanschlüsse erfolgt auf eigenes
Risiko.
