# Gamma RS10 -- Reverse Engineering Experiments

This document records controlled experiments used to reverse engineer
the RS485 protocol of the Gamma RS10.

It serves as the evidence log for fields marked `CONFIRMED` in
`PROTOCOL.md`.

## 1. Test system

-   Boiler: Fischer/Guntamatic BIOSTAR 15
-   Installation: November 1999
-   Room station: Gamma RS10
-   Article number: 9550901000
-   Physical bus address: 3
-   Protocol address: `0x23`
-   Interface: RS485
-   Serial parameters: 9600 8N1
-   Capture interface: FTDI FT232R USB UART / RS485 adapter
-   Experiment date: 2026-09-11

## 2. Methodology

Preferred method: controlled A/B/A testing.

1.  Set parameter to value A.
2.  Capture traffic.
3.  Change exactly one parameter to B.
4.  Capture traffic.
5.  Restore A.
6.  Capture traffic.
7.  Compare normalized CRC-valid frames.
8.  Identify fields following the A/B/A pattern.

For dynamic sensor values, direct comparison against the simultaneously
displayed RS10 value is used.

## 3. Capture processing

The capture setup inserts many `0xFF` bytes. Captures are normalized
before frame extraction.

Raw:

    82 FF 10 FF 20 FF 28 FF 06 ...

Normalized:

    82 10 20 28 06 ...

Only CRC-16/KERMIT-valid frames are used for semantic analysis.

# 4. Day room setpoint

Captures:

    test-21.bin
    test-22.bin
    test-22-2.bin

Setting:

    21 °C -> 22 °C -> 21 °C

Result in `2806`:

    P37: 0x2A -> 0x2C -> 0x2A
          21.0 -> 22.0 -> 21.0 °C

Conclusion:

    2806 P37 = Day room setpoint
    temperature = P37 / 2

Status: `CONFIRMED`.

# 5. Night room setpoint

Captures:

    test-Nacht-16.bin
    test-Nacht-17.bin
    test-Nacht-16-2.bin

Setting:

    16 °C -> 17 °C -> 16 °C

Result:

    P38: 0x20 -> 0x22 -> 0x20
          16.0 -> 17.0 -> 16.0 °C

Conclusion:

    2806 P38 = Night room setpoint
    temperature = P38 / 2

Status: `CONFIRMED`.

# 6. Domestic hot-water setpoint

Captures:

    test-Warmwasser-50.bin
    test-Warmwasser-51.bin
    test-Warmwasser-50-2.bin

Setting:

    50 °C -> 51 °C -> 50 °C

Result:

    P10: 0x64 -> 0x66 -> 0x64
          50.0 -> 51.0 -> 50.0 °C

Conclusion:

    2806 P10 = Domestic hot-water setpoint
    temperature = P10 / 2

Status: `CONFIRMED`.

# 7. Room actual temperature

This value was confirmed by repeated direct comparison with the RS10
display.

Observed:

    RS10 21.5 °C -> P2 = 0x2B -> 21.5 °C
    RS10 22.0 °C -> P2 = 0x2C -> 22.0 °C
    RS10 22.5 °C -> P2 = 0x2D -> 22.5 °C

Relevant capture:

    test-temp.bin
    p4-korrektur-sollwert.bin

Conclusion:

    2806 P2 = Room actual temperature
    temperature = P2 / 2

Status: `CONFIRMED`.

# 8. P4 investigation and active room setpoint

Early experiments showed that P4 changed with room-related settings, but
it was not a duplicate of the stored day setpoint.

Captures:

    p4-tag.bin
    p4-nacht.bin
    p4-tag-2.bin
    p4-korrektur-sollwert.bin

Observed mode-dependent values included:

    Heating/day    P4 = 0x2E -> 23.0 °C in the earlier test state
    Reduced/night  P4 = 0x20 -> 16.0 °C

A later controlled change of the RS10 setting displayed as
`Korrektur Sollwert` from 23 °C to 24 °C produced:

    P4 = 0x2E -> 0x30

while:

    P37 = 0x2A = 21.0 °C

remained the stored day setpoint.

Subsequent explicit operating-mode tests showed:

    Heating  P4 = 0x2A -> 21.0 °C
    Reduced  P4 = 0x20 -> 16.0 °C
    Party    P4 = 0x2A -> 21.0 °C
    Away     P4 = 0x20 -> 16.0 °C

Conclusion:

    2806 P4 = currently effective room setpoint
    temperature = P4 / 2

Status: `CONFIRMED`.

# 9. Basic operating modes

Captures:

    modus-automatik.bin
    modus-absenken.bin
    modus-heizen.bin

Result in `2806 P7`:

    Automatic  = 0x00
    Heating    = 0x03
    Reduced    = 0x04

Values appeared consistently in the relevant `2806` frames.

Conclusion:

    2806 P7 = Operating mode

Status: `CONFIRMED`.

# 10. Party mode

Capture:

    modus-party-bis-23:29.bin

Setting on Friday 2026-09-11:

    Party until 23:29

Observed:

    P7  = 0x13
    P39 = 0x29
    P40 = 0x23
    P41 = 0x05
    P4  = 0x2A -> 21.0 °C

Conclusion:

    P7 = 0x13 -> Party
    P39/P40/P41 encode the timed-mode end.

# 11. Away mode

Capture:

    modus-abwesend-bis-23:31.bin

Setting on Friday 2026-09-11:

    Away until 23:31

Observed:

    P7  = 0x14
    P39 = 0x31
    P40 = 0x23
    P41 = 0x05
    P4  = 0x20 -> 16.0 °C

Conclusion:

    P7 = 0x14 -> Away

Status: `CONFIRMED`.

# 12. Timed mode across midnight

Capture:

    modus-party-bis-00:35.bin

Experiment date:

    Friday 2026-09-11

Setting:

    Party until Saturday 00:35

Observed:

    P7  = 0x13
    P39 = 0x35
    P40 = 0x00
    P41 = 0x06

Earlier same-day Party capture:

    Friday 23:29
    P39 = 0x29
    P40 = 0x23
    P41 = 0x05

Conclusion:

    P39 = end minute
    P40 = end hour
    P41 = end weekday

The transition `0x05 -> 0x06` exactly followed Friday -\> Saturday.

Directly observed weekday values:

    0x05 = Friday
    0x06 = Saturday

The expected full mapping is 1=Monday through 7=Sunday, but the
remaining values have not yet been individually observed.

Status: field function `CONFIRMED`.

# 13. Complete operating-mode mapping

  P7       RS10 mode          Status
  -------- ------------------ -------------
  `0x00`   Automatic          `CONFIRMED`
  `0x03`   Heating            `CONFIRMED`
  `0x04`   Reduced            `CONFIRMED`
  `0x13`   Party until time   `CONFIRMED`
  `0x14`   Away until time    `CONFIRMED`

# 14. Current 2806 field map

  Position   Meaning                       Encoding     Status
  ---------- ----------------------------- ------------ ----------------------
  P2         Room actual temperature       raw / 2 °C   `CONFIRMED`
  P4         Active room setpoint          raw / 2 °C   `CONFIRMED`
  P7         Operating mode                enum         `CONFIRMED`
  P10        Domestic hot-water setpoint   raw / 2 °C   `CONFIRMED`
  P37        Day room setpoint             raw / 2 °C   `CONFIRMED`
  P38        Night room setpoint           raw / 2 °C   `CONFIRMED`
  P39        Timed-mode end minute         BCD          `CONFIRMED`
  P40        Timed-mode end hour           BCD          `CONFIRMED`
  P41        Timed-mode end weekday        1--7         `CONFIRMED` function

# 15. Initial 2004 observations

Before direct verification, the following candidates had been
identified:

    P2  outside temperature candidate
    P17 unknown temperature
    P32 boiler temperature candidate

The 2026-09-11 experiment documented below confirmed P2 and P32.

# 16. Outside and boiler temperature

## Purpose

Verify the suspected outside-temperature and boiler-temperature fields
against values displayed directly by the RS10.

## Capture

    weitere-werte.bin

## Simultaneously observed RS10 values

    Domestic hot water: 56.5 °C
    Boiler:             50.5 °C
    Outside maximum:    18.5 °C
    Outside minimum:    12.0 °C
    Outside current:    17.0 °C

## 16.1 Outside temperature

Message:

    2004

Observed:

    P2 = 0x8A = 138

Conversion:

    138 / 2 - 52 = 17.0 °C

RS10 display:

    17.0 °C

The decoded value exactly matched the displayed value.

Conclusion:

    2004 P2 = Outside temperature
    temperature = P2 / 2 - 52

Status: `CONFIRMED`.

## 16.2 Boiler temperature

Message:

    2004

Observed at the beginning of the capture:

    P32 = 0x65 = 101

Conversion:

    101 / 2 = 50.5 °C

RS10 display:

    50.5 °C

During the capture P32 subsequently increased to:

    P32 = 0x66 -> 51.0 °C

Conclusion:

    2004 P32 = Boiler temperature
    temperature = P32 / 2

Status: `CONFIRMED`.

## 16.3 Domestic hot-water actual temperature

RS10 display:

    56.5 °C

A corresponding field could not yet be reliably identified in message
`2004`.

Message `4002` was not present in this capture.

Status: `UNKNOWN`.

## 16.4 Outside minimum and maximum

RS10 display:

    Outside maximum = 18.5 °C
    Outside minimum = 12.0 °C

No reliable corresponding fields were identified in this capture.

Status: `UNKNOWN`.

## 16.5 Additional 8001 observation

In the same capture, `8001` contained values numerically equal to 50.5
°C at multiple positions, including:

    P52 = 0x65
    P66 = 0x65

This correlation alone is insufficient to identify these fields. A
future capture at a substantially different boiler temperature should be
compared.

Status: `UNKNOWN`.

# 17. Current 2004 field map

  Position   Meaning                 Encoding               Status
  ---------- ----------------------- ---------------------- -------------
  P2         Outside temperature     raw / 2 - 52 °C        `CONFIRMED`
  P17        Unknown temperature     raw / 2 °C candidate   `UNKNOWN`
  P32        Boiler temperature      raw / 2 °C             `CONFIRMED`
  P33        Unknown; often `0x4C`   unknown                `UNKNOWN`

# 18. Experiments still required

## 18.1 Message 4002

Identify additional actual temperatures. Record simultaneously:

-   boiler temperature
-   domestic hot-water actual temperature
-   heating-flow temperature
-   outside temperature

## 18.2 Identify 2004 P17

Compare P17 against domestic hot-water, heating-flow and other displayed
temperatures during changing operating conditions.

## 18.3 Outside minimum/maximum

Find fields corresponding to the RS10 outside minimum and maximum
values, ideally after those values change.

## 18.4 Message 8001

Repeat captures at substantially different boiler and water temperatures
to determine whether apparently duplicated temperature values track
those sensors.

## 18.5 Remaining 2806 fields

Change additional RS10 settings one at a time, preferably A -\> B -\> A.

# 19. Experiment naming convention

Use descriptive filenames. For A/B/A tests:

    parameter-A1.bin
    parameter-B.bin
    parameter-A2.bin

Examples:

    tag-21-A1.bin
    tag-22-B.bin
    tag-21-A2.bin

# 20. Evidence policy

Use `CONFIRMED` only for direct experimental evidence, preferably
controlled A/B/A or multiple exact comparisons with an independently
displayed value.

Use `LIKELY` for strong correlation without sufficient controlled
verification.

Use `UNKNOWN` when no reliable semantic assignment exists.

Correlation during normal heating operation alone does not prove field
identity.

# 21. Experiment log

  ----------------------------------------------------------------------------------------
  Date              Experiment          Capture(s)                       Result
  ----------------- ------------------- -------------------------------- -----------------
  2026-09-11        Day setpoint        `test-21.bin`, `test-22.bin`,    P37 confirmed
                                        `test-22-2.bin`                  

  2026-09-11        Night setpoint      `test-Nacht-16.bin`,             P38 confirmed
                                        `test-Nacht-17.bin`,             
                                        `test-Nacht-16-2.bin`            

  2026-09-11        DHW setpoint        `test-Warmwasser-50.bin`,        P10 confirmed
                                        `test-Warmwasser-51.bin`,        
                                        `test-Warmwasser-50-2.bin`       

  2026-09-11        Room actual         `test-temp.bin` and other        P2 confirmed
                    temperature         captures                         

  2026-09-11        Active/correction   `p4-korrektur-sollwert.bin`      P4 behaviour
                    setpoint                                             identified

  2026-09-11        Basic operating     `modus-automatik.bin`,           P7 00/03/04
                    modes               `modus-heizen.bin`,              confirmed
                                        `modus-absenken.bin`             

  2026-09-11        Party               `modus-party-bis-23:29.bin`      P7=13 and timed
                                                                         end identified

  2026-09-11        Away                `modus-abwesend-bis-23:31.bin`   P7=14 confirmed

  2026-09-11        Party across        `modus-party-bis-00:35.bin`      P41 weekday
                    midnight                                             function
                                                                         confirmed

  2026-09-11        Outside and boiler  `weitere-werte.bin`              2004 P2 and P32
                    temperature                                          confirmed
  ----------------------------------------------------------------------------------------

# 22. Summary

The experiments distinguish several independent temperature concepts:

    2806 P2   measured room temperature
    2806 P4   currently effective room setpoint
    2806 P37  stored day setpoint
    2806 P38  stored night setpoint

They also establish:

    2806 P7   operating mode
    2806 P10  domestic hot-water setpoint
    2806 P39  timed-mode end minute
    2806 P40  timed-mode end hour
    2806 P41  timed-mode end weekday

Direct RS10 comparisons additionally confirm:

    2004 P2   outside temperature
    2004 P32  boiler temperature

Domestic hot-water actual temperature, outside minimum/maximum,
`2004 P17`, and the temperature fields of `4002` remain targets for
further investigation.
