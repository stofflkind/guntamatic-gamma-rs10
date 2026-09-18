# Guntamatic Gamma RS10 Protocol

**English** \| [Deutsch](README.de.md)

Unofficial reverse engineering and documentation of the RS485 protocol
used by the **Gamma RS10** room station with a **Fischer/Guntamatic
BIOSTAR 15** pellet heating system.

The project is based on passive bus captures, CRC validation, direct
comparison with values displayed by the RS10, controlled A/B/A
experiments, and raw FT232R bit-level captures.

> **Project status:** Work in progress. Frame structure, CRC, several
> cyclic values, weekly programs, parts of the parameter block, and
> important aspects of the ninth-bit bus-access layer have been decoded.
> Unknown fields and bus-control semantics are deliberately kept
> separate from confirmed results.

## Test system

-   Fischer/Guntamatic BIOSTAR 15 pellet boiler
-   Installed November 1999
-   Gamma RS10 room station
-   RS10 article number `9550901000`
-   RS10 physical bus address selector `3`
-   Central controller believed to be **Gamma 2B**; physical type label
    still to be confirmed
-   RS485, 9600 baud
-   Passive capture using an FTDI FT232R USB/RS485 adapter
-   Additional asynchronous FT232R bit-bang capture at about 307,200
    samples/s

Results may differ with other controller or firmware versions.

## Documentation

-   [`PROTOCOL.md`](PROTOCOL.md) --- detailed protocol documentation,
    evidence, bus state model, decoded fields and open questions
-   [`docs/experiments.md`](docs/experiments.md) --- controlled
    experiments and evidence
-   [`docs/ft232r-analyzer.md`](docs/ft232r-analyzer.md) --- passive
    FT232R raw protocol analyzer
-   [`tools/extract_4002_timeline.py`](tools/extract_4002_timeline.py)
    --- timestamp-aware extraction of CRC-valid DHW temperature frames

Evidence is classified conservatively:

  -----------------------------------------------------------------------
  Status                              Meaning
  ----------------------------------- -----------------------------------
  `CONFIRMED`                         Verified by controlled experiment
                                      or direct display comparison

  `LIKELY`                            Strong evidence, but controlled
                                      verification is incomplete

  `UNKNOWN`                           Not reliably identified
  -----------------------------------------------------------------------

The protocol documentation contains more detailed distinctions where
appropriate, including manual-confirmed and strongly-supported
interpretations.

## Physical protocol

Observed wire format:

``` text
RS485
9600 baud
start bit
8 data bits, LSB first
protocol-significant ninth bit
stop bit
```

Earlier captures were treated as ordinary 8N1. Parity-aware and raw
FT232R captures show that this is incomplete: the additional bit carries
protocol state.

Current observed model:

``` text
slot/scan announcement bytes    Bit 9 = 1
normal 0x82 ... 0x03 frames     Bit 9 = 0
observed 0x06 handshake byte    Bit 9 = 0
```

Frames begin with `0x82` and end with `0x03`. The checksum is
**CRC-16/KERMIT**, transmitted little-endian. See
[`PROTOCOL.md`](PROTOCOL.md) for the exact frame layout and CRC
coverage.

## Current participant interpretation

The two bytes after `0x82` are historically called source and
destination, but their exact physical semantics are not fully proven.

  Address   Current interpretation                        Status
  --------- --------------------------------------------- --------------------
  `0x23`    RS10 protocol participant                     strongly supported
  `0x10`    central Gamma controller participant          strongly supported
  `0x20`    logical/data target or receiver role          `UNKNOWN`
  `0xAA`    service/broadcast-like address                `UNKNOWN`
  `0xFF`    special/startup address in observed traffic   `UNKNOWN`

A passive two-wire capture cannot by itself prove which physical device
transmitted every byte. In particular, `0x20` is **not** currently
assigned to the boiler control PCB.

## Frame and request/data examples

Four cyclic request/data pairs are consistently observed:

``` text
23 -> 10 TYPE0101  -> about 27.7 ms -> 10 -> 20 TYPE8001
23 -> 10 TYPE0102  -> about 27.7 ms -> 10 -> 20 TYPE4002
23 -> 10 TYPE0105  -> about 27.7 ms -> 10 -> 20 TYPE1005
23 -> 10 TYPE0106  -> about 27.7 ms -> 10 -> 20 TYPE2806
```

Successful bus-access cycles also show repeatable ninth-bit
marker/handshake sequences. Their exact ownership and semantics remain
under investigation.

## Selected decoded values

  --------------------------------------------------------------------------
  Field             Meaning              Encoding          Status
  ----------------- -------------------- ----------------- -----------------
  `2806 P2`         room actual          raw / 2 °C        `CONFIRMED`
                    temperature                            

  `2806 P4`         active room setpoint raw / 2 °C        `CONFIRMED`

  `2806 P7`         operating mode       enum              `CONFIRMED`

  `2806 P10`        domestic-hot-water   raw / 2 °C        `CONFIRMED`
                    setpoint                               

  `2806 P37`        day room setpoint    raw / 2 °C        `CONFIRMED`

  `2806 P38`        night room setpoint  raw / 2 °C        `CONFIRMED`

  `2806 P39..P41`   timed-mode end data  mode-dependent    `CONFIRMED`

  `2004 P2`         outside temperature  raw / 2 - 52 °C   `CONFIRMED`

  `2004 P32`        Gamma-side           raw / 2 °C        `LIKELY`
                    boiler/flow                            
                    temperature                            

  `4002 P08`        domestic-hot-water   raw / 2 °C        `CONFIRMED`
                    actual temperature                     

  `8014 param#35`   heating-curve slope  raw / 20          `CONFIRMED`
                    (`Steilheit`)                          

  `8014 param#81`   Legionellen-WW       0=off, 1..7       field confirmed
                    weekday/off setting  weekday           

  `8014 param#30`   selected boiler      1..3              `CONFIRMED`
                    weekly program                         
  --------------------------------------------------------------------------

The complete decoding table is maintained in
[`PROTOCOL.md`](PROTOCOL.md).

## Operating modes

Confirmed `2806 P7` values include:

``` text
0x00  Automatic
0x03  Heating
0x04  Reduced
0x13  Party until specified time
0x14  Away until specified time
0x24  Vacation until specified date
```

The timed end fields `P39..P41` are mode-dependent. For example, Away
uses minute/hour/weekday, while Vacation uses day/month/year.

## Weekly programs and parameter transport

Entering RS10 programming levels produces short requests followed by
larger blocks. Confirmed mappings include:

``` text
010E / 800E   boiler weekly program 1
010F / 800F   boiler weekly program 2
0110 / 8010   boiler weekly program 3
0112 / 8012   domestic-hot-water weekly program
0114 / 8014   RS10 parameter/configuration block
```

The weekly program blocks contain seven days with up to three time
windows per day. Time fields use BCD encoding.

## Domestic-hot-water temperature and legionella observation

`4002 P08` is confirmed as the actual DHW/storage temperature:

``` text
temperature = P08 / 2 °C
```

A controlled observation with `Legionellen-WW = 4` (Thursday) on
2026-09-17 showed a distinct high-temperature phase approximately
between 21:00 and 22:00. The Gamma-side `2004 P32` value rose to roughly
80--82 °C, while the storage temperature rose more slowly and reached an
observed maximum of **69.5 °C at 22:41:19**.

This is an observed maximum for that cycle, **not** evidence for a fixed
69.5 °C legionella target.

During the high-temperature phase, unknown field `2004 P17` changed to
`0xA2`. This is a strong correlation only; its exact meaning remains
`UNKNOWN`.

## Capture normalization: important `0xFF` finding

The normal FTDI/RS485 capture path used on the test installation exposes
separator-like `0xFF` bytes between logical bytes. A blind removal of
every `0xFF` is unsafe because genuine payload bytes can also be `0xFF`.

`TYPE 4002` provided the decisive example: it contains a genuine logical
`0xFF` at P03. Blind `strip-ff` normalization destroys the frame and
causes CRC validation to fail.

The parser therefore uses **lossless, frame-aware `deinterleave-ff`
normalization** and preserves genuine payload values. The interleaving
is considered a property of the capture/interface path, not part of the
Gamma protocol.

## Tools

The repository includes:

-   semantic Gamma frame parser with CRC validation
-   FT232R raw bit-bang capture and ninth-bit decoding tools
-   timing analyzers for slot/handshake investigation
-   controlled experiment scripts
-   `extract_4002_timeline.py` for timestamped, CRC-valid DHW
    temperature reconstruction

The raw FT232R analyzer is passive: all FT232R bit-bang pins are
configured as inputs.

## Reverse-engineering method

Whenever possible, fields are identified by controlled A/B/A tests:

``` text
setting A -> capture
setting B -> capture
setting A -> capture
```

Only one user-visible parameter is intentionally changed. Dynamic sensor
values are compared directly with the RS10 display. Hypotheses are not
promoted to confirmed mappings without supporting evidence.

## Current research targets

1.  Determine transmitter ownership and exact semantics of `06`, `A3`,
    `90`, `FC`, `FF`, `7D` and startup `C0`.
2.  Refine the passive ninth-bit bus state model.
3.  Determine the exact meaning of address field B, especially `0x20`.
4.  Explain why identical `2806` payloads occur as both `10 -> 20` and
    `23 -> 20`.
5.  Confirm the central controller's physical type label; current
    evidence points to Gamma 2B.
6.  Determine the minimum bus behavior required to emulate an RS10.
7.  Continue decoding unknown fields in `2004`, `8014`, `4002`, `1005`
    and `2806`.

## Contributions welcome

Captures and controlled observations from other Gamma/RS10 installations
are especially valuable.

Useful contributions should include, where possible:

-   controller and room-station model
-   firmware/version information
-   bus-address/selector setting
-   exact parameter changed
-   before/after values
-   CRC-valid telegrams
-   whether the observation was reproduced

Comparisons with Gamma 2B, 23B, 233B or other RS10 installations could
help distinguish installation-specific behavior from general protocol
rules.

Please clearly distinguish measured results from hypotheses.

## Safety

The project is based primarily on **passive, read-only monitoring**.

Do not connect the RS10 12 V supply to a USB adapter power pin. Do not
transmit arbitrary frames to a heating controller unless their effects
and bus arbitration are understood. Heating systems are safety-relevant
equipment; experiments must not bypass or interfere with the boiler's
own safety controls.

Active experiments in this project are isolated and deliberately
conservative.

## Prior work

This project builds on earlier community reverse-engineering work
concerning Gamma heating-control communication, including
`bogeyman/gamma` protocol documentation and discussions on
mikrocontroller.net.

The `CONFIRMED` results in this repository are based on measurements and
controlled experiments on the installation described above.

## License

See [`LICENSE`](LICENSE).

## Disclaimer

This is an unofficial reverse-engineering project. It is not affiliated
with or endorsed by Guntamatic, Fischer, or the manufacturer of the
Gamma RS10.

The documentation may contain errors and may not apply to other
controller or firmware versions. Use all information, software and
hardware connections at your own risk.
