# Gamma RS10 / Guntamatic BIOSTAR -- Protocol Documentation

Reverse engineering of the RS485 communication between a **Gamma RS10**
room station and a **Fischer/Guntamatic BIOSTAR 15** pellet heating
system.

This document describes the protocol based on passive RS485 captures and
controlled experiments on a real installation. It is deliberately
conservative: fields are only marked confirmed when a controlled change
or direct display comparison supports them.

Last updated: **2026-09-18**

## 1. Test system

-   Boiler: Fischer/Guntamatic BIOSTAR 15
-   Installation: November 1999
-   Room station: Gamma RS10
-   RS10 article number: 9550901000
-   RS10 physical bus address selector: 3
-   Interface: RS485
-   Capture interface: FTDI FT232R USB UART / RS485 adapter

## 2. Status terminology

-   `CONFIRMED`: experimentally verified by a controlled parameter
    change or direct comparison with the RS10 display.
-   `LIKELY`: strong evidence, but not yet sufficiently controlled for a
    final assignment.
-   `UNKNOWN`: meaning currently unknown.

The results apply to the tested installation and may differ with other
firmware or controller versions.

### 2.1 Manual cross-check

On 2026-09-13 the reverse-engineered mappings were cross-checked against
the **Gamma RS10 Bedienungsanleitung und Anleitung zur Inbetriebnahme**
(56-page manual). The manual is used as an independent semantic
reference, while byte positions and encodings remain based on captured
RS485 traffic.

Confidence is therefore kept separate:

-   `BUS CONFIRMED`: experimentally verified on RS485.
-   `MANUAL CONFIRMED`: function/name/range explicitly described in the
    RS10 manual.
-   `LIKELY`: strong correspondence, but not yet changed in a controlled
    bus test.
-   `UNKNOWN`: not established.

Manual references below use the PDF page number as displayed by the
uploaded file.

## 3. Physical interface

The Gamma RS10 uses four connections:

-   `+UB`
-   `GND`
-   `A`
-   `B`

The room station is supplied with approximately 12 V DC. Communication
takes place over RS485.

Observed baud rate and character width:

``` text
9600 baud
8 data bits
1 stop bit
parity / ninth-bit state is protocol-significant
```

Earlier captures were treated as `9600 8N1`. Controlled parity captures
on 2026-09-14 show that this is incomplete: the Gamma bus uses the UART
parity bit as an additional protocol state. Scan/slot-announcement bytes
and normal frame bytes are transmitted with different parity-bit states.
See section **4.1 Parity / ninth-bit layer**.

For passive decoding, a conventional 8N1 capture can still recover byte
values on the tested FTDI path, but it loses the parity-state
information required for accurate active emulation.

### Electrical warning

For passive monitoring, connect only the required RS485 signals. Do
**not** connect the RS10 +12 V supply to a USB adapter's 5 V or other
power output.

## 4. Capture peculiarity: inserted `0xFF` bytes

With the FTDI/RS485 capture setup used here, separator `0xFF` bytes are
interleaved between logical protocol bytes. A normal logical sequence
such as:

``` text
82 10 20 09 05 ...
```

can therefore appear on the capture path as:

``` text
82 FF 10 FF 20 FF 09 FF 05 FF ...
```

Earlier tooling normalized this with a blind `replace(0xFF, nothing)`.
That is **not safe** because `0xFF` may also be a genuine Gamma payload
byte. Message `4002` provided the decisive example: it contains a real
`0xFF` at P03. Removing all FF bytes destroys that frame and causes its
CRC check to fail.

The parser now uses a frame-aware **deinterleave-ff** mode. It removes
only the capture-added separator positions while preserving genuine
logical `0xFF` data. In live mode this is done statefully so frames
split across serial read chunks are reconstructed correctly.

This interleaving is a property of the capture/interface path used on
this installation, **not part of the Gamma protocol**.

### 4.1 Parity / ninth-bit layer

Status: `OBSERVED`; interpretation as a mark/space-style ninth-bit
channel is strongly supported by controlled captures.

On 2026-09-14 the bus was captured twice with Linux parity checking
enabled:

``` text
INPCK + PARMRK
9600 8E1
9600 8O1
```

Linux `PARMRK` preserves bytes with parity/framing errors as
`FF 00 <byte>`. Comparing the same traffic under even and odd parity
therefore allows the transmitted parity bit to be inferred without
changing the Gamma data byte itself.

The decisive startup sequence at RS10 selector 3 was observed as
follows.

Under **even** parity:

``` text
!A3 .06 .A3 .82 !10 .AA !01 .00 .00 .0F .90 .03 ...
```

Under **odd** parity the classifications invert correspondingly for the
relevant bytes. Here `.` means parity accepted by the configured UART
mode and `!` means parity error.

For the two key bytes:

``` text
A3  data popcount even; scan occurrence matches odd parity  -> transmitted parity bit = 1
06  data popcount even; matches even parity                -> transmitted parity bit = 0
```

More importantly, the same byte value `A3` occurs with **different
parity states** depending on its role:

``` text
scan/slot A3       parity bit = 1
A3 after 06        parity bit = 0
```

Normal `82 ... 03` frames are consistent with a constant parity bit of
`0` for every byte. Bytes with an even number of one-bits therefore
appear valid under 8E1, while bytes with an odd number of one-bits
appear as parity errors under 8E1. This is consistent with **SPACE
parity** for normal frame traffic.

The current physical-layer model is therefore:

``` text
slot/scan announcement bytes       MARK-like parity bit = 1   [OBSERVED]
normal frame bytes 82 ... 03       SPACE-like parity bit = 0  [OBSERVED]
06 in RS10 startup handshake       SPACE-like parity bit = 0  [OBSERVED]
```

This explains why the older 8N1 capture path showed apparently inserted
`0xFF` values: the Linux/FTDI receive path was exposing parity
information indirectly. The `0xFF` pattern must therefore not be
interpreted as Gamma payload framing by itself.

Linux `CMSPAR` can request stick/mark/space parity on supported serial
devices. This was used in controlled one-shot transmit experiments, but
successful RS10 emulation has **not** yet been achieved.

### 4.2 Slot announcements and RS10 presence detection

Status: sequence `OBSERVED`; exact ownership/semantics of every byte
remains partly `LIKELY`/`UNKNOWN`.

With the physical RS10 disconnected, the controller continues cyclic
traffic and emits a repeating sequence of short slot-announcement bytes.
A representative sequence is:

``` text
90 x5
21 x5
22 x5
A3 x5
11 x5
12 x5
93 x5
14 x5
95 x5
96 x5
17 x5
18 x5
99 x5
9A x5
1B x5
9C x5
1D x5
1E x5
9F x5
```

The fivefold repetition is consistent with the repetition behavior seen
elsewhere on the Gamma bus.

A controlled comparison of the RS10 rear address selector showed:

``` text
selector 3 -> activity occurs in the A3 slot
selector 1 -> activity occurs in the 21 slot
```

This agrees with the RS10 manual's heating-circuit identifiers: on Gamma
participant 1, selector/heating-circuit identifier 1 corresponds to
mixer circuit 1, 2 to mixer circuit 2, and 3 to the boiler circuit. The
tested installation has only the boiler circuit, so selector 3 is the
normal working setting.

Immediately before the first successful communication after connecting
the physical RS10 at selector 3, the raw parity-aware capture contains
the characteristic sequence:

``` text
... A3(mark) 06(space) A3(space) 82 10 AA 01 00 ... 03 ...
```

The association of `06` with RS10 presence is strong, but transmitter
ownership cannot be proven from a single two-wire bus capture alone. It
is therefore documented as an **observed handshake byte**, not yet as a
fully confirmed RS10 command/ACK semantic.

Public Gamma reverse-engineering independently describes the network as
a single-master bus using slot announcements, with the room station
answering its assigned slot. This is consistent with the observations on
this installation, but the byte-level interpretation here remains based
on the local captures.

### 4.3 Controlled active presence experiments

Active experiments were performed only with the physical RS10
disconnected. No heating-setting telegram (`2806`) was transmitted
during these presence tests.

One-shot attempts included:

``` text
23 -> AA 0100                         no observed controller response
23 -> 10 0105                         no observed 1005 response
06 sent after detected A3 using 8N1   no observed 10->AA 0100
06 sent with SPACE/CMSPAR             no observed 10->AA 0100
06 sent as fixed 8E1                  no observed 10->AA 0100
```

The failed `06` experiments do **not** disprove the parity model. They
show only that reproducing the byte value and parity state from
Linux/Python userspace was insufficient to reproduce the complete
presence handshake.

The leading hypothesis is currently a response-timing problem and/or an
additional bus-level requirement that has not yet been identified.

### 4.4 Wire-level timing from FT232R raw capture

Status: `OBSERVED`.

The asynchronous FT232R bit-bang capture provides approximately 307,200
samples/s, i.e. about 32 samples per 9600-baud bit. Unlike the older
Linux/Python read-chunk timestamps, this permits sample-level timing
measurements.

Successful selector-3 handshakes repeatedly show:

``` text
A3/1 -> 06/0    about 688..718 samples = about 2.24..2.34 ms
90/1 -> 06/0    about 625..653 samples = about 2.03..2.13 ms in typical cycles
```

Representative successful cycles:

``` text
A3/1 -> 06/0 -> A3/0 -> 82 10 AA 01 00 01 86 81 03 -> 06/0

90/1 -> 06/0 -> 90/0 -> 82 23 10 01 05 10 19 8A 03 -> 06/0
             -> about 4.1 ms -> 82 10 20 10 05 ...
```

The older host-buffer timing limitation therefore no longer applies to
captures made with the raw FT232R bit-bang analyzer.

### 4.5 Successful `A3` and `90` bus-access cycles

Status: sequence `OBSERVED`; exact ownership/meaning remains `LIKELY`.

Across the 60-second selector-3 startup capture, every observed
**successful** `A3/1` cycle (immediate `06/0`, then `A3/0`) was followed
by:

``` text
A3/1 -> 06/0 -> A3/0 -> 82 10 AA 01 00 01 86 81 03 -> 06/0
```

Unsuccessful `A3/1` polling attempts repeat without the immediate `06`.

Likewise, every observed successful `90/1` cycle was followed by a frame
whose first address field is `0x23`:

``` text
90/1 -> 06/0 -> 90/0 -> 82 23 ...
```

Thus the strong protocol-level association is:

``` text
successful A3 cycle -> following address field A = 0x10
successful 90 cycle -> following address field A = 0x23
```

There is a crossed relation:

``` text
A3 & 0x7F = 0x23
90 & 0x7F = 0x10
```

This may encode the counterpart being polled or another bus-access
relationship, rather than the following sender's own address. This
interpretation is **not confirmed** and is not a general marker rule
(`FC & 0x7F = 0x7C`).

A passive two-wire capture still cannot electrically prove which
physical device transmitted each byte.

### 4.6 Additional Bit-9 marker associations

Status: `OBSERVED`.

``` text
FC/1 -> about 3.94..3.99 ms -> 82 10 20 09 05 ...   TYPE 0905
FF/1 -> about 3.94..3.99 ms -> 82 10 20 20 04 ...   TYPE 2004
```

`7D/1` also precedes frames by about 3.95 ms, but is not uniquely tied
to one message type. During startup it preceded both `10 -> FF TYPE0100`
traffic and some `10 -> 20 TYPE0905` frames.

The ninth-bit markers therefore form a systematic
bus-access/polling/arbitration layer, but a simple
one-marker-to-one-message-type rule is not supported.

### 4.7 Cyclic RS10 request/data pairs

Four short requests from address field `0x23` to `0x10` are consistently
followed about 27.6..27.8 ms later by corresponding larger data blocks:

``` text
23 -> 10 TYPE0101  ->  10 -> 20 TYPE8001
23 -> 10 TYPE0102  ->  10 -> 20 TYPE4002
23 -> 10 TYPE0105  ->  10 -> 20 TYPE1005
23 -> 10 TYPE0106  ->  10 -> 20 TYPE2806
```

At raw ninth-bit level these share the structure:

``` text
90/1 -> 06 -> 90/0 -> 23 -> 10 TYPE010x -> 06 -> 10 -> 20 TYPE<data>
```

This strongly supports `0x23` as the RS10 protocol participant and
`0x10` as the central Gamma controller participant.

### 4.8 Selector test and startup behavior

A controlled RS10 `BUS-ADR` change from `3` to `4` did **not** change
the observed `A3` scan byte to `A4`. With `BUS-ADR 4`, no successful
immediate marker-to-`06` handshake was observed and the RS10 eventually
displayed a bus-connection fault. After restoring `BUS-ADR 3`, normal
communication returned.

Therefore a simple `BUS-ADR n -> marker An` rule is disproved for this
installation.

During startup a one-off successful `C0/1 -> 06/0` event was also
observed. Its semantics remain `UNKNOWN`.

## 5. Frame structure

``` text
+--------+--------+-------------+--------+---------+--------+------+
| Start  | Source | Destination | Length | Payload | CRC16  | End  |
+--------+--------+-------------+--------+---------+--------+------+
| 0x82   | 1 byte | 1 byte      | 1 byte | n bytes | 2 byte | 0x03 |
+--------+--------+-------------+--------+---------+--------+------+
```

The length byte is called `LL`. The payload contains `LL + 1` bytes.

Complete frame length:

``` text
LL + 8 bytes
```

## 6. CRC

Frames use CRC-16/KERMIT:

``` text
width      = 16
polynomial = 0x1021
reflected  = yes
ref poly   = 0x8408
init       = 0x0000
xorout     = 0x0000
```

The CRC is transmitted little-endian: low byte, then high byte.

CRC input:

``` text
source + destination + length + payload
```

Parser notation:

``` python
frame[1:-3]
```

The initial `0x82`, CRC bytes and final `0x03` are excluded.

## 7. Message type

The message type is represented by the length byte plus the first
payload byte.

Examples observed:

``` text
0100 0101 0102 0105 0106 010E 010F 0110 0112 0114
0905 1005 2004 2806 4002 8001 800E 800F 8010 8012 8014
```

Example:

``` text
length = 0x28
payload[0] = 0x06
type = 2806
```

## 8. Address fields and current participant interpretation

The parser historically names the two bytes after `0x82` `source` and
`destination`. That remains useful shorthand, but their exact physical
semantics are not fully proven. In interpretive discussion they are
therefore treated as **address field A** and **address field B**.

  -----------------------------------------------------------------------
  Address                Current interpretation   Status
  ---------------------- ------------------------ -----------------------
  `0x23`                 RS10 protocol            `STRONGLY SUPPORTED`
                         participant              

  `0x10`                 central Gamma controller `STRONGLY SUPPORTED`
                         participant, likely      
                         Gamma 2B                 

  `0x20`                 logical/data target or   `UNKNOWN`
                         receiver role; no        
                         physical-device          
                         assignment established   

  `0xAA`                 service/broadcast-like   `UNKNOWN`
                         address                  

  `0xFF`                 special/startup address  `UNKNOWN`
                         in observed TYPE0100     
                         traffic                  
  -----------------------------------------------------------------------

In the 60-second selector-3 startup capture, only `0x10` and `0x23`
occurred in address field A. `0x20`, `0xAA` and `0xFF` occurred only in
address field B.

Observed combinations:

``` text
10 -> 20
10 -> AA
10 -> FF
23 -> 10
23 -> 20
23 -> AA
```

No valid frame with `0x20` in address field A was observed. Consequently
`0x20` must **not** currently be identified with the boiler control PCB.

Current physical architecture hypothesis:

``` text
RS10 <---- RS485 ----> Gamma 2B
                        |
                        +-- dedicated outside/boiler/storage sensor inputs
                        +-- burner relay / pump outputs

boiler control PCB ---- separate RS232 stream
```

The central controller is believed to be a **Gamma 2B** because the
installation has no mixer circuit and the Gamma 2B wiring model matches
that topology. This remains to be confirmed from the physical controller
type label.

## 9. Bus state model

Status: `WORKING MODEL`. This section describes observed protocol
behavior and the minimum state transitions currently supported by
passive captures. It does **not** assign electrical transmitter
ownership where a passive two-wire capture cannot prove it.

### 9.1 Participants and address fields

Current protocol-level interpretation:

``` text
0x23  RS10 participant                  [STRONGLY SUPPORTED]
0x10  central Gamma controller          [STRONGLY SUPPORTED]
0x20  logical/data target or receiver   [UNKNOWN]
0xAA  service/broadcast-like address    [UNKNOWN]
0xFF  special/startup address           [UNKNOWN]
```

Only `0x10` and `0x23` were observed in address field A in the 60-second
selector-3 startup capture.

### 9.2 Scan / polling state

When no successful access occurs, Bit-9=1 marker bytes are repeatedly
emitted. Observed scan groups include:

``` text
90, 21, 22, A3, 11, 12, 93, 14, 95, 96,
17, 18, 99, 9A, 1B, 9C, 1D, 1E, 9F
```

Individual markers are commonly retried five times. A marker without an
immediate `06/0` remains an unsuccessful scan/poll attempt.

Conceptually:

``` text
SCAN
  |
  +-- marker/1, no immediate 06 --> retry / continue scan
  |
  +-- marker/1, immediate 06 --> successful bus-access cycle
```

### 9.3 Successful `A3` cycle

Every observed successful `A3` cycle in the selector-3 capture has the
same form:

``` text
A3/1
  -> about 2.24..2.34 ms
06/0
A3/0
82 10 AA 01 00 01 86 81 03
06/0
```

State model:

``` text
SCAN_A3
   |
   +-- no 06 --> retry/continue
   |
   +-- 06 --> A3/0 --> 10->AA TYPE0100 --> 06 --> BUS CONTINUES
```

This is a stable protocol-level association between a successful `A3`
cycle and a following frame with address field A `0x10`.

### 9.4 Successful `90` cycle

Successful `90` cycles have the form:

``` text
90/1
  -> typically about 2.03..2.13 ms
06/0
90/0
82 23 ...
```

The following `0x23` frame may address `0xAA`, `0x10` or `0x20`.

State model:

``` text
SCAN_90
   |
   +-- no 06 --> retry/continue
   |
   +-- 06 --> 90/0 --> 23->... frame --> 06 --> optional response/data phase
```

This is a stable protocol-level association between successful `90`
access and address field A `0x23`.

### 9.5 RS10 request / Gamma data cycle

Four cyclic request/data pairs are currently known:

``` text
23->10 TYPE0101  -> about 27.7 ms -> 10->20 TYPE8001
23->10 TYPE0102  -> about 27.7 ms -> 10->20 TYPE4002
23->10 TYPE0105  -> about 27.7 ms -> 10->20 TYPE1005
23->10 TYPE0106  -> about 27.7 ms -> 10->20 TYPE2806
```

At raw Bit-9 level:

``` text
90/1
  -> 06
  -> 90/0
  -> 82 23 10 01 0x ...
  -> 06
  -> about 4 ms until start of the following 82 frame
  -> 82 10 20 <data type> ...
```

The approximately 27.7 ms figure is measured from the start of the short
request frame to the start of the corresponding data frame; the
approximately 4 ms interval is the raw gap after the request's trailing
`06` to the following `0x82`.

### 9.6 Other controller-side scheduled traffic

Additional Bit-9 markers precede controller-side cyclic frames:

``` text
FC/1 -> about 3.96 ms -> 10->20 TYPE0905
FF/1 -> about 3.96 ms -> 10->20 TYPE2004
```

`7D/1` also precedes `0x10` traffic but is not uniquely associated with
one type.

These are represented conservatively as scheduled bus-access states:

``` text
MARKER/1 --> fixed short delay --> 82 10 ... frame
```

The exact marker semantics remain unknown.

### 9.7 Startup / presence state

The observed startup behavior can currently be represented as:

``` text
RS10 ABSENT / NOT PARTICIPATING
          |
          | physical RS10 connected with BUS-ADR 3
          v
SCAN / DISCOVERY
          |
          | successful A3/1 -> 06
          v
A3 PARTICIPATION ESTABLISHED
          |
          | recurring bus activity
          | one-off C0/1 -> 06 observed in one startup
          v
90 PARTICIPATION
          |
          | successful 90/1 -> 06 -> 90/0 -> 23...
          v
NORMAL CYCLIC OPERATION
```

`C0` is not yet assigned a semantic role.

Changing RS10 `BUS-ADR` from 3 to 4 prevented successful participation
and eventually produced a bus-connection fault on the RS10. Restoring
address 3 restored normal operation.

The RS10 display startup sequence is not used as an exact timing
reference because its visible transition time varies and need not
coincide with a particular bus event.

### 9.8 Open questions

The state model intentionally leaves the following unresolved:

-   which physical device electrically transmits each handshake byte;
-   whether `06` is an ACK, grant, presence response or another
    bus-control symbol;
-   exact semantics of `A3`, `90`, `FC`, `FF`, `7D` and `C0`;
-   why the low-seven-bit relation of `A3` and `90` appears crossed;
-   exact meaning of address field B, especially `0x20`;
-   why identical `2806` payloads can occur as both `10->20` and
    `23->20`;
-   which subset of these states is the minimum required for an RS10
    emulator.

The model should be updated only when additional passive evidence or
controlled experiments distinguish these alternatives.

## 10. Message repetition

Messages are frequently repeated. Five identical repetitions are
commonly observed. Software should suppress consecutive duplicates when
presenting state changes, but raw captures should preserve them.

## 11. Message `0x2806` -- RS10 state

This is one of the best understood cyclic RS10 telegrams.

Positions are numbered beginning with the first payload byte:

``` text
P1 = payload byte 1
```

  Position   Meaning                       Encoding         Status
  ---------- ----------------------------- ---------------- -------------
  P2         Room actual temperature       value / 2 °C     `CONFIRMED`
  P4         Active room setpoint          value / 2 °C     `CONFIRMED`
  P7         Operating mode                enum             `CONFIRMED`
  P10        Domestic hot-water setpoint   value / 2 °C     `CONFIRMED`
  P37        Day room setpoint             value / 2 °C     `CONFIRMED`
  P38        Night room setpoint           value / 2 °C     `CONFIRMED`
  P39--P41   Timed-mode end data           mode-dependent   `CONFIRMED`

### 11.1 Room actual temperature

``` text
temperature = P2 / 2
```

Examples:

``` text
0x2B -> 21.5 °C
0x2C -> 22.0 °C
0x2D -> 22.5 °C
```

#### 11.1.1 Room-temperature compensation (`KORREKTUR`)

The RS10 manual identifies the house-level menu item shown as
`KORREKTUR` as **Raumtemperatur-Kompensation**. It has a factory setting
of `0.0 K` and an adjustment range of `±2.5 K`. The manual explicitly
states that this function influences the current room actual temperature
in order to compensate a measurement offset between the RS10
installation point and the preferred room location (manual PDF pages 32
and 38).

This matches the controlled RS485 experiment:

``` text
KORREKTUR 0.0 -> -0.5 K
controller-side P2: 0x2C = 22.0 °C
RS10-side P2:       0x2B = 21.5 °C
```

After restoring `KORREKTUR` to `0.0 K`, `P2` returned to
`0x2C = 22.0 °C`.

Therefore:

-   `2806 P2` remains the room actual temperature (`raw / 2 °C`)
    \[`BUS CONFIRMED`\].
-   The house-menu `KORREKTUR` is a room-temperature measurement
    compensation \[`MANUAL CONFIRMED`, effect also observed on bus\].
-   No independent RS485 field containing the configured compensation
    value has yet been identified \[`UNKNOWN`\].

### 11.2 Active room setpoint

``` text
temperature = P4 / 2
```

P4 represents the currently effective room setpoint, not simply the
stored day setpoint.

### 11.3 Operating mode

  P7       Mode
  -------- ------------------------------------------
  `0x00`   Automatic
  `0x03`   Heating
  `0x04`   Reduced
  `0x13`   Party until specified time
  `0x14`   Away (`Abwesend`) until specified time
  `0x24`   Vacation (`Urlaub`) until specified date

### 11.4 Domestic hot-water setpoint

Controlled A/B/A experiment:

``` text
50 °C -> 51 °C -> 50 °C
0x64  -> 0x66  -> 0x64
```

Encoding:

``` text
temperature = P10 / 2
```

#### 11.4.1 P11 -- manual Warmwasser-Nachladung state/command

A controlled manual DHW recharge experiment on 2026-09-13 identified P11
as a direction-sensitive state/command field associated with manual
**Warmwasser-Nachladung**.

Observed sequence when switching recharge on:

``` text
RS10 0x23 -> 0x20 : P11 = 0x01
controller 0x10 -> 0x20 : P11 = 0x02   about 5 s later
RS10 0x23 -> 0x20 : P11 = 0x02
```

Observed sequence when switching recharge off:

``` text
RS10 0x23 -> 0x20 : P11 = 0x00
controller 0x10 -> 0x20 : P11 = 0x00   about 5 s later
```

Current interpretation:

``` text
0x00 = no manual DHW recharge
0x01 = request/command from RS10              [LIKELY]
0x02 = controller accepted / active state     [LIKELY]
```

The field association with manual DHW recharge is strongly supported by
the controlled transition. The exact semantic distinction between `0x01`
and `0x02` should be confirmed by a second independent test.

Status: `LIKELY_DIRECTION_SENSITIVE`.

### 11.5 Day and night room setpoints

``` text
P37 / 2 = day setpoint °C
P38 / 2 = night setpoint °C
```

Controlled examples:

``` text
21 °C -> 22 °C -> 21 °C : 0x2A -> 0x2C -> 0x2A
16 °C -> 15 °C -> 16 °C : 0x20 -> 0x1E -> 0x20
```

### 11.6 Timed mode end -- mode-dependent encoding

`P39..P41` are reused according to `P7` operating mode. Controlled tests
on 2026-09-15 confirmed two distinct layouts.

For `P7 = 0x14` (**Abwesend / Away until time**):

``` text
P39 = end minute, BCD
P40 = end hour, BCD
P41 = end weekday, 1=Monday ... 7=Sunday
```

Controlled examples:

``` text
Wednesday 09:16 -> P39=0x16 P40=0x09 P41=0x03
Tuesday   23:53 -> P39=0x53 P40=0x23 P41=0x02
```

Together with earlier observations (`Friday=0x05`, `Saturday=0x06`),
this strongly confirms Monday=1 through Sunday=7. In the same controlled
test, `P7=0x14` and the effective room setpoint `P4=0x20`, i.e. 16.0 °C.

For `P7 = 0x24` (**Urlaub / Vacation until date**):

``` text
P39 = end day, BCD
P40 = end month, BCD
P41 = two-digit end year, BCD
```

Controlled observations:

``` text
Urlaub until 15.10.2026 -> P39=0x15 P40=0x10 P41=0x26
Urlaub until 16.10.2026 -> P39=0x16 P40=0x10 P41=0x26
Urlaub until 16.11.2026 -> P39=0x16 P40=0x11 P41=0x26
Automatik               -> P39=0x00 P40=0x00 P41=0x00
```

The day and month assignments are `BUS CONFIRMED` by independent
controlled changes. `P41=0x26` is consistent with the automatically
selected current year 2026; the RS10 UI does not allow the year to be
changed independently, so the year assignment is strongly supported but
not independently varied.

The Urlaub experiment also changed `P7` from `0x00` (Automatic) to
`0x24` and the effective room setpoint `P4` from `0x2C` (22.0 °C) to
`0x14` (10.0 °C). Returning to Automatic restored `P7=0x00`, `P4=0x2C`,
and cleared P39..P41.

## 12. Message `0x2004`

  Position   Meaning                              Encoding            Status
  ---------- ------------------------------------ ------------------- -------------
  P2         Outside temperature                  value / 2 - 52 °C   `CONFIRMED`
  P17        Unknown raw/status-like field        unknown             `UNKNOWN`
  P18        Unknown status-like field            unknown             `UNKNOWN`
  P32        Gamma-side boiler/flow temperature   value / 2 °C        `LIKELY`
  P33        Unknown, often `0x4C`                unknown             `UNKNOWN`

### 12.1 Outside temperature

``` text
temperature = P2 / 2 - 52
```

Direct example:

``` text
P2 = 0x8A = 138
138 / 2 - 52 = 17.0 °C
```

This matched the RS10 display exactly.

### 12.2 P17 and P18

Overnight captures showed P17 values such as:

``` text
0x00, 0x4E, 0x52, 0x53, 0x54, 0x55, 0x56, 0x88
```

The abrupt transitions do not look like a normal continuously varying
temperature sensor. P18 was observed mainly as `0x00` or `0x10`.

Both remain `UNKNOWN`.

### 12.3 P32 -- Gamma-side boiler/flow temperature

P32 behaves like a real temperature, changing smoothly in 0.5 °C steps.
During one overnight capture it ranged from about 27.5 °C to 71.5 °C.

It is **not identical** to the burner board's separate RS232 `TI` value.
The current best interpretation is therefore:

``` text
Gamma-side Kessel-/Vorlauftemperatur Ist
value = P32 / 2 °C
```

Status: `LIKELY`.

### 12.4 P33

P33 has repeatedly been observed as `0x4C`. Meaning unknown.

## 13. Message `0x0905` -- date and time

Observed positions:

  Position   Meaning
  ---------- ----------------------------------
  P1         subtype `0x05`
  P2         flag/status
  P3         second
  P4         minute
  P5         hour
  P6         day
  P7         packed month/weekday information
  P8         two-digit year
  P9         weekday
  P10        month

Date/time values use a BCD-like representation.

Status: partially decoded.

## 14. Weekly program transport

Entering a programming level on the RS10 produces a request from RS10 to
the controller and a full 128-byte program block in response. When
leaving the programming level, the RS10 sends a full block back.

This matches the RS10 display behavior: entering and exiting the program
level briefly shows **"Warten"**.

Four weekly-program transports are now identified by controlled UI
experiments:

``` text
010E request -> 800E Kessel PROG 1
010F request -> 800F Kessel PROG 2
0110 request -> 8010 Kessel PROG 3
0112 request -> 8012 domestic-hot-water weekly program
```

The Kessel-program mapping was verified by changing only the selected
**Kessel PROG** in the RS10 parameter menu and then opening the normal
Kessel weekly-program editor. With PROG 2 selected the RS10 requested
`010F` and received `800F`; with PROG 3 selected it requested `0110` and
received `8010`.

The 128-byte program block contains:

``` text
7 days × 15 bytes = 105 bytes
23 trailing bytes, observed as zero
```

Each day contains:

``` text
3 time windows × 5 bytes
```

## 15. `010E`/`800E`, `010F`/`800F`, `0110`/`8010` -- Kessel weekly programs 1--3

Status: `CONFIRMED`.

The three blocks `800E`, `800F` and `8010` store Kessel weekly programs
1, 2 and 3 respectively. Each stores three configurable boiler/heating
periods per weekday.

``` text
800E = Kessel PROG 1
800F = Kessel PROG 2
8010 = Kessel PROG 3
```

All three use the same 7-day × 3-window structure.

Each 5-byte period is:

``` text
[start_minute_BCD,
 start_hour_BCD,
 setpoint_temperature_times_2,
 end_minute_BCD,
 end_hour_BCD]
```

In compact form:

``` text
MM HH TT MM HH
```

where `TT / 2 = setpoint °C`.

### 15.1 Controlled minute experiment

Baseline Monday:

``` text
00 04 2c 55 23
```

corresponding to:

``` text
04:00–23:55 @ 22 °C
```

Changing only the start time to 04:05 produced:

``` text
05 04 2c 55 23
```

Changing only the start time to 04:15 produced:

``` text
15 04 2c 55 23
```

This confirms BCD encoding of the minutes and hours.

### 15.2 Temperature field

The third byte is the configured temperature multiplied by two.

Observed installation settings:

``` text
Mo–Do: 22 °C -> 0x2C
Fr–So: 23 °C -> 0x2E
```

Thus:

``` text
0x2C = 44 / 2 = 22.0 °C
0x2E = 46 / 2 = 23.0 °C
```

### 15.3 Examples from the installation

``` text
Mo–Do: 00 04 2c 55 23 = 04:00–23:55 @ 22 °C
Fr:    00 04 2e 55 23 = 04:00–23:55 @ 23 °C
Sa–So: 00 05 2e 55 23 = 05:00–23:55 @ 23 °C
```

Unused second and third periods were observed as:

``` text
00 00 2a 00 00
```

The time fields are empty (`00:00–00:00`), while the temperature byte
remains `0x2A = 21 °C`. Therefore an unused boiler-program slot is
identified from the zero start/end time fields, not from the temperature
byte.

### 15.4 Relationship to global TAG-SOLL

A controlled A/B/A experiment changed global `TAG-SOLL` from 21 °C to 22
°C and back. The temperature bytes in all three Kessel program blocks
shifted by exactly +2 raw units and then returned by -2 raw units,
including retained temperature bytes in unused slots. Time fields did
not change.

Examples:

``` text
0x2A -> 0x2C -> 0x2A   = 21 -> 22 -> 21 °C
0x2C -> 0x2E -> 0x2C   = 22 -> 23 -> 22 °C
0x2E -> 0x30 -> 0x2E   = 23 -> 24 -> 23 °C
```

This confirms that the third byte is an actual stored temperature value
(`raw / 2 °C`), while also showing that these Kessel-program
temperatures are coupled to the global day setpoint on this
RS10/controller combination.

### 15.5 Program selection experiment

The long-Haus parameter menu contains `Kessel PROG 1/2/3`. Controlled
selection tests showed:

``` text
selected PROG 1 -> normal editor requests 010E -> receives 800E
selected PROG 2 -> normal editor requests 010F -> receives 800F
selected PROG 3 -> normal editor requests 0110 -> receives 8010
```

Status of all three mappings: `CONFIRMED`.

## 16. `0112` / `8012` -- domestic-hot-water weekly program

Status: time structure `CONFIRMED`; third-byte semantic `LIKELY`.

The `8012` block stores three domestic-hot-water periods per weekday.

Each 5-byte period is observed as:

``` text
[start_minute_BCD,
 start_hour_BCD,
 dhw_setpoint_raw,
 end_minute_BCD,
 end_hour_BCD]
```

The third byte was previously treated as a fixed marker because it was
always `0x64`. The RS10 manual resolves this ambiguity: each Warmwasser
heating cycle contains a **WW-Soll** value in addition to start and end
times (manual PDF pages 19 and 21). In the tested installation the
global/observed warm-water setpoint is 50.0 °C, and:

``` text
0x64 = 100 decimal
100 / 2 = 50.0 °C
```

The most plausible interpretation is therefore:

``` text
WW cycle setpoint = third byte / 2 °C
```

This semantic assignment is `LIKELY` until a controlled change of one
individual Warmwasser programme cycle produces the corresponding byte
change.

### 16.1 Baseline program

``` text
Mon: 00 02 64 00 04 | 00 00 64 00 00 | 00 00 64 00 00
Tue: 00 02 64 00 04 | 00 00 64 00 00 | 00 00 64 00 00
Wed: 00 02 64 00 04 | 00 00 64 00 00 | 00 00 64 00 00
Thu: 00 02 64 00 04 | 00 00 64 00 00 | 00 00 64 00 00
Fri: 00 02 64 00 04 | 00 00 64 00 00 | 00 00 64 00 00
Sat: 00 05 64 00 07 | 00 00 64 00 00 | 00 00 64 00 00
Sun: 00 05 64 00 07 | 00 00 64 00 00 | 00 00 64 00 00
```

This decodes to:

``` text
Mon–Fri: 02:00–04:00
Sat–Sun: 05:00–07:00
```

### 16.2 Controlled minute experiment

A deliberately programmed Monday interval of **00:15--02:10** produced:

``` text
15 00 64 10 02
```

This confirms exact BCD encoding of the time fields:

``` text
start minute      = 0x15
start hour        = 0x00
WW setpoint raw   = 0x64 -> 50.0 °C [LIKELY semantic]
end minute        = 0x10
end hour          = 0x02
```

### 16.3 Empty interval

Exactly:

``` text
00 00 64 00 00
```

### 16.4 Ordering behavior

In one controlled test, a newly added earlier interval was stored before
the later existing interval. This suggests that the RS10 sorts populated
DHW intervals chronologically when saving.

Status of sorting behavior: `LIKELY` based on one controlled
observation.

## 17. `0114` / `8014` -- RS10 parameter/configuration block

Status: `PARTIALLY DECODED`.

A long press of the RS10 house button opens a parameter area after
displaying **"WARTEN"**. Entering this area produces:

``` text
0114 request from RS10 -> controller
8014 response from controller -> bus
```

Leaving the parameter area causes the RS10 to send a full `8014` block
back. This identifies `0114/8014` as the transport for this RS10
parameter/configuration area.

The tested menu contains at least:

``` text
Steilheit
TAG-SOLL
Nacht-SOLL
Reduziert ECO
Warmwasser
Legionellen-WW
Warmwasser PROG
Kessel PROG
Korrektur
```

`TAG-SOLL` and `Nacht-SOLL` are **not** stored in the two currently
identified `8014` fields below; their confirmed values are carried in
`2806 P37/P38`.

### 17.1 Position numbering for `8014`

To avoid an off-by-one ambiguity, the following `8014` positions are
called **parameter bytes** and are counted **after** the subtype byte
`0x14`:

``` text
content[0] = subtype 0x14
parameter byte 1  = content[1]
...
parameter byte 30 = content[30] = document-wide payload P31
parameter byte 92 = content[92] = document-wide payload P93
```

### 17.2 Parameter byte 8 -- Reduziert

Controlled `ECO -> AbS -> ECO` testing changed exactly parameter byte 8:

``` text
0x00 = ECO
0x01 = AbS
```

Document-wide payload position: `P9`.

Status: `CONFIRMED`. The display label `AbS` is retained without
assigning a more specific semantic expansion.

### 17.3 Parameter byte 30 -- selected Kessel program

Controlled selection tests produced:

``` text
0x01 = Kessel PROG 1
0x02 = Kessel PROG 2
0x03 = Kessel PROG 3
```

Document-wide payload position: `P31`.

The independent weekly-editor requests `010E`, `010F` and `0110` matched
the selected program.

Status: `CONFIRMED`.

### 17.4 Parameter byte 35 -- Steilheit

Controlled A/B/A tests identified parameter byte 35 as `Steilheit`. The
decisive step-size experiment produced:

``` text
1.00 -> 1.05 -> 1.00
0x14 -> 0x15 -> 0x14
```

A separate `1.00 -> 1.10 -> 1.00` experiment produced
`0x14 -> 0x16 -> 0x14`.

Encoding:

``` text
Steilheit = raw / 20
```

Document-wide payload position: `P36`.

Status: `CONFIRMED`.

### 17.5 Parameter byte 81 -- Legionellen-WW

The RS10 menu offers `AUS` and numeric selections `1` through `7`. A
controlled sequence captured:

``` text
AUS -> 1 -> 2 -> AUS
0x00 -> 0x01 -> 0x02 -> 0x00
```

Therefore parameter byte 81 is the `Legionellen-WW` setting.

The weekday semantics of the numeric values have since been confirmed
verbally by two Guntamatic technicians independently: `1..7` means
Monday through Sunday. An additional overnight comparison after setting
Legionellenschutz to `4` (Thursday) showed `0x04` in the corresponding
parameter field on 2026-09-17.

``` text
0x00 = AUS
0x01 = Monday
0x02 = Tuesday
0x03 = Wednesday
0x04 = Thursday
0x05 = Friday
0x06 = Saturday
0x07 = Sunday
```

Bus evidence currently includes controlled `0x00`, `0x01`, `0x02`
transitions and an observed `0x04` value matching the configured
Thursday setting. The field assignment is `CONFIRMED`; the complete
weekday mapping is strongly supported by the technician confirmations,
while `0x03` and `0x05..0x07` have not yet been individually varied in a
controlled bus test.

Document-wide payload position: `P82`.

### 17.6 Parameter byte 92 -- selected Warmwasser program

Controlled observations produced:

``` text
0x02 = Warmwasser PROG 2   [CONFIRMED]
0x03 = Warmwasser PROG 3   [CONFIRMED]
0x01 = Warmwasser PROG 1   [LIKELY; not yet directly tested]
```

Document-wide payload position: `P93`.

The field assignment is `CONFIRMED`; only value `0x01` remains inferred.

### 17.7 `Korrektur` / Raumtemperatur-Kompensation

The official RS10 manual identifies this menu item as
**Raumtemperatur-Kompensation**, factory value `0.0 K`, range `±2.5 K`.
It is specifically intended to correct the RS10 room actual temperature
for differences between the measuring point and the preferred occupied
area.

The controlled `0.0 -> -0.5 K` bus experiment showed the corresponding
effect in `2806 P2`. No byte in the observed `8014` block changed with
the setting.

Status:

-   function/meaning: `MANUAL CONFIRMED`
-   effect on `2806 P2`: experimentally observed
-   separate storage/transport field: `UNKNOWN`

## 18. Official RS10 manual ↔ RS485 mapping

This section records functions explicitly documented by the RS10 manual
and maps them to fields already observed on the tested RS485
installation. A manual entry does not by itself prove a byte position;
byte positions still require bus evidence.

  ----------------------------------------------------------------------------------------------
  RS10 manual function          Manual range /         RS485 mapping      Confidence
                                behavior                                  
  ----------------------------- ---------------------- ------------------ ----------------------
  Raum-Isttemperatur            RS10 measures          `2806 P2`, raw/2   BUS + MANUAL CONFIRMED
                                representative room    °C                 
                                temperature                               

  Raumtemperatur-Kompensation   0.0 K factory; ±2.5 K  affects reported   MANUAL CONFIRMED; bus
  (`KORREKTUR`)                                        `2806 P2`; storage effect observed
                                                       field unknown      

  Aktueller Raum-Sollwert       direct +/- correction  `2806 P4`, raw/2   BUS CONFIRMED; manual
                                in 0.5 K steps         °C                 semantics match

  Tages-Raumsollwert            5...30 °C; factory 21  `2806 P37`, raw/2  BUS + MANUAL CONFIRMED
  Kesselkreis                   °C                     °C                 

  Absenk-Raumsollwert           5...30 °C; factory 16  `2806 P38`, raw/2  BUS + MANUAL CONFIRMED
  Kesselkreis                   °C                     °C                 

  Heizkennliniensteilheit       0.20...3.50            `8014 param#35`,   BUS CONFIRMED; manual
  Kesselkreis                                          raw/20             range matches

  Funktion im reduzierten       `ECO`, `AbS`           `8014 param#8`:    BUS + MANUAL CONFIRMED
  Betrieb                                              0/1                

  Warmwasser-Sollwert           20...80 °C; factory 50 `2806 P10`, raw/2  BUS + MANUAL CONFIRMED
                                °C                     °C                 

  Legionellenschutz             `AUS`, `1…7`;          `8014 param#81`:   field BUS CONFIRMED;
                                technician-confirmed   0=AUS; 1=Mon ...   0/1/2 controlled, 4
                                weekday semantics:     7=Sun              observed; complete
                                1=Mon ... 7=Sun                           weekday semantics
                                                                          technician-confirmed

  Schaltzeitenprogramm          programme 1...3        `8014 param#92`;   field BUS CONFIRMED
  Warmwasserkreis                                      `0112/8012` editor 
                                                       block              

  Schaltzeitenprogramm          programme 1...3        `8014 param#30`;   BUS + MANUAL CONFIRMED
  Kesselkreis                                          `010E/800E`,       
                                                       `010F/800F`,       
                                                       `0110/8010`        

  Kessel programme cycle        start, end, room       `800E/F/10`        BUS + MANUAL CONFIRMED
                                setpoint; up to 3/day  five-byte slots    

  Warmwasser programme cycle    start, end, WW         `8012` five-byte   times BUS CONFIRMED;
                                setpoint; up to 3/day  slots; byte 3      setpoint semantic
                                                       likely WW setpoint LIKELY
                                                       raw/2              

  Outside temperature           current, 24 h min, 24  current value      current BUS + MANUAL
                                h max shown in info    mapped to          CONFIRMED
                                level                  `2004 P2`          

  Boiler temperature            shown in direct        `2004 P32` matches display match
                                information level      RS10-displayed     CONFIRMED; physical
                                                       Kesseltemperatur   sensor point still
                                                       in direct test     cautious

  Warmwasser-Isttemperatur      shown in direct        `4002 P08`, raw/2  BUS + DISPLAY
                                information level      °C                 CONFIRMED
  ----------------------------------------------------------------------------------------------

The manual also documents that the direct information level can display
**Außentemperatur**, **Kesseltemperatur** and
**Warmwasser-Isttemperatur**. The identification of `4002 P08` now
provides the cyclic bus source for the latter on the tested
installation.

### 18.1 Manual-only service parameters not yet mapped to bytes

The RS10 service level contains many additional parameters for which no
RS485 byte assignment has yet been established on this installation.
These include:

``` text
Raumfaktor
Thermostatfunktion
Einschaltoptimierung
Ausschaltoptimierung
Raumminimaltemperatur
Zugriffsberechtigung / Busrechte
Betriebsartenzugriff
Kesselfühlerbetriebsart
Klimazone
Kesselabsenkung
Außentemperatursperre
Kesselanfahrentlastung
Außenfühlerzuordnung
Exponent
Adaption
Speicher-Schaltdifferenz
Zweistufige Speicherladung
Witterungsgeführter Speicherparallelbetrieb
Speicher-Parallelvorschiebung
Kesselkreispumpen-Ausgang
Kesselkreispumpen-Nachlauf
Speicher-Ladepumpennachlauf
Warmwasser-Nachladung
```

These names and ranges are useful labels for future unknown
parameter-block bytes, but they must **not** be assigned to bytes
without a controlled RS485 experiment.

## 19. Message `0x8001`

`8001` is a large parameter/status block.

It remained completely static during an approximately 11-hour overnight
capture and also did not change between direct RS10 warm-water display
observations of 57.0 °C and 56.5 °C.

It is therefore unlikely to contain a straightforward live
domestic-hot-water actual temperature field, unless that value is
encoded indirectly or updated only under conditions not yet observed.

Status: `UNKNOWN`.

## 20. Message `0x1005`

`1005` changes during normal operation. Much of the variability appears
related to time/date-like fields. No reliable semantic assignment has
yet been established.

Status: `UNKNOWN`.

## 21. Message `0x4002`

`4002` is a cyclic controller data block. It was initially missed in
current and historical captures because the old capture workaround
blindly deleted every `0xFF`. The `4002` payload contains a **genuine
`0xFF` at P03**, so blind removal shortened the frame and invalidated
its CRC.

After lossless FF deinterleaving, `4002` is recovered as a CRC-valid
frame. A representative live frame on 2026-09-13 was:

``` text
82 10 20 40 02 00 FF 00 00 00 1C 6F ... CRC ... 03
```

Using payload numbering where `content[0] = P1 = 0x02`:

``` text
4002 P08 = domestic-hot-water actual temperature
value = raw / 2 °C
```

Direct simultaneous confirmation on 2026-09-13:

``` text
P08 = 0x6F = 111
111 / 2 = 55.5 °C
RS10 information display: Warmwasser = 55.5 °C
```

The historical 2016 capture additionally shows a physically plausible
heating and cooling curve in P08.

Direction observed for the data frame:

``` text
0x10 -> 0x20
```

Status of `4002 P08`: **CONFIRMED**.

### 21.1 Legionella-protection cycle observed on 2026-09-17

A continuous raw RS485 capture was evaluated offline with CRC validation.
The RS10/controller was configured for `Legionellen-WW = 4` (Thursday).
This provides an observed execution trace for the weekday setting documented
in section 17.5.

The high-temperature operating phase is visible in `2004 P32` and in the
previously unknown/status-like `P17` field:

``` text
before 21:00     P32 approximately 38..43 °C; P17 commonly 0x4E
21:01            P17 changes to 0xA2
21:03..21:10     P32 rises rapidly to approximately 82.5 °C
21:10..22:00     P32 mostly approximately 76.5..82.5 °C; P17 = 0xA2
22:01            P17 changes to 0x00; high-temperature phase ends
after 22:01      P32 falls rapidly
```

This timing is consistent with the technician-provided operational
information that legionella protection runs on the configured weekday
between **21:00 and 22:00**.

`P17 = 0xA2` is therefore strongly correlated with this observed
high-temperature operating phase, but its exact semantic meaning remains
`UNKNOWN`. It must not yet be labelled as a dedicated "legionella active"
flag.

The same raw capture was reconstructed for `TYPE 4002` using lossless FF
deinterleaving. CRC-valid `P08` measurements show the storage/DHW response:

``` text
20:46              57.0 °C
around 21:37       56.5..57.0 °C
around 21:45       60.0 °C
22:14              67.0 °C
22:41:19           69.5 °C   observed maximum
23:29              68.5 °C
```

The storage temperature continued to rise after the approximately
21:00--22:00 high-temperature controller phase and reached the observed
maximum of **69.5 °C at 22:41:19**. This delayed maximum is consistent with
thermal lag of the storage system.

The value 69.5 °C is an **observed maximum for this specific cycle**, not a
confirmed fixed legionella target temperature.

### 21.2 Production FF-normalization finding on 2026-09-18

The production collector previously selected the normalization candidate
with the highest number of CRC-valid frames. In some captures this selected
`strip-ff`. That mode is lossy because genuine logical `0xFF` payload bytes
exist, with `4002 P03` providing a confirmed example. Consequently valid
`4002` frames could disappear from live parsing even though their bytes were
present in the raw stream.

The live collector now prefers normalization in this order when the
corresponding candidate produces valid frames:

``` text
1. deinterleave-ff
2. none
3. strip-ff (legacy fallback)
```

After this change, live CRC-valid `4002` frames and
`Warmwasser-Ist` values reappeared. This confirms that separator-aware,
lossless deinterleaving is required for this capture path.

For offline analysis, `tools/extract_4002_timeline.py` reconstructs
timestamped CRC-valid `TYPE 4002` frames from the raw logger stream and
reports `P08` temperatures and their observed maximum.

Other `4002` fields remain under investigation.

## 22. Short cyclic messages

Observed:

``` text
0100
0101
0102
0105
0106
```

Possible roles include polling, acknowledgement, synchronization or bus
coordination. These are hypotheses only.

The program/parameter-level requests `010E`, `010F`, `0110`, `0112` and
`0114` are **not** part of this unknown group; those are now identified.

## 23. Domestic-hot-water actual temperature

The domestic-hot-water actual temperature is now identified:

``` text
4002 P08 = Warmwasser-Ist
scale     = raw / 2 °C
status    = CONFIRMED
```

The decisive live comparison on 2026-09-13 produced `P08=0x6F`, which
decodes to 55.5 °C, while the RS10 simultaneously displayed **Warmwasser
55.5 °C**.

The reason earlier direct-display experiments failed to locate the value
was not a special query mechanism. The old FF normalization destroyed
`4002` before CRC validation. This also explains why the RS10 can
display the value immediately: it is available in cyclic traffic.

## 24. Historical capture statistics

A historical 2016 capture contained:

``` text
raw decoded bytes:       22,506,000
normalized bytes:        11,584,615
removed 0xFF bytes:      10,921,385
CRC-valid frames:           311,570
```

Selected counts:

``` text
2004    78,880
0905    78,634
0100    31,371
2806    28,723
0105    15,684
1005    15,543
0106    15,684
0102    15,684
0101    15,684
8001    15,683
```

The capture covered approximately 26 hours, indicating a recurring
communication cycle of roughly six seconds.

## Capture normalization on this installation

The FT232R capture path used on this installation interleaves `0xFF`
separator bytes between logical bus bytes. A blind `strip-ff`
normalization is **not safe** because `0xFF` can also be a genuine Gamma
payload value. Message `4002` is a confirmed example: its payload
contains a genuine `0xFF`, and deleting all `0xFF` bytes destroys the
frame before CRC validation.

For the production logger on this installation, normalization is
therefore fixed to the stateful, lossless `deinterleave-ff` path. The
former heuristic of selecting the mode that yields the highest number of
CRC-valid frames must not be used: in live testing, `strip-ff` produced
9 CRC-valid probe frames versus 8 for `deinterleave-ff`, yet it still
discarded the valid `4002` telegram carrying the domestic-hot-water
actual temperature. A higher CRC-valid frame count is therefore not
sufficient evidence that a normalization mode is semantically correct.

### Raw FT232R bit-bang capture

A second, independent passive capture path was validated on 2026-09-15
using the same FT232R adapter in asynchronous bit-bang mode with all
D0..D7 pins configured as inputs (`mask=0x00`). Only D1/RXD toggled,
consistent with the output of the on-board ST3485E RS485 receiver. No
RS485 transmit-enable or data line is driven by this method.

With the libftdi bit-bang baud setting at 9600, the measured raw input
stream is approximately 307,200 samples/s, corresponding to about 32
samples per 9600-baud bit. A 10-second validation capture produced
3,067,904 samples (306,780 samples/s, about 99.9% of nominal).

Offline decoding uses the observed UART structure:

``` text
start bit | 8 data bits, LSB first | bit 9 | stop bit
```

The ninth bit is retained as a protocol-significant **Bit 9 / marking
bit** rather than being discarded as ordinary UART parity. The raw
decoder reconstructs logical Gamma bytes, then scans `0x82 ... 0x03`
candidates and accepts frames only when CRC-16/KERMIT validates. This
independently reconstructs the same Gamma telegram types seen through
the normal UART capture path.

A controlled Urlaub capture on 2026-09-15 yielded 40 CRC-valid Gamma
frames from the FT232R raw samples, including four `2806` frames. Both
`10 -> 20` and `23 -> 20` variants carried the same semantic payload
while having their own valid CRC. The decoded fields included:

``` text
P7  = 0x24       Urlaub / Vacation
P4  = 0x14       10.0 °C active room setpoint
P39 = 0x15       day 15
P40 = 0x10       month 10
P41 = 0x26       year 2026 (strongly supported; not independently variable)
```

The semantic parser therefore decoded the raw-capture-derived frame as
`mode=vacation(0x24)` and `vacation-until=15.10.2026`. This provides an
independent end-to-end validation of the raw FT232R capture and decoding
chain.

## 25. Overnight 2026 capture observations

An approximately 11-hour capture on 2026-09-12/13 contained about
130,000 valid normalized RS485 frames.

Observed regular types included:

``` text
0905
2004
0100
2806
0105
0106
0102
0101
8001
1005
```

`4002` was initially reported as absent because blind `0xFF` removal
destroyed these frames. With lossless FF deinterleaving, CRC-valid
`4002` frames are recovered from the historical capture.

The capture was particularly useful for showing that `2004 P32` is a
smooth temperature-like value but does not equal the burner board's
RS232 `TI` value.

## 26. Current decoding summary

``` text
2806 P2   room actual temperature                 [CONFIRMED]
RS10 KORREKTUR / room compensation                [manual confirmed; affects P2, storage field unknown]
2806 P4   active room setpoint                    [CONFIRMED]
2806 P7   operating mode                          [CONFIRMED]
2806 P10  domestic hot-water setpoint             [CONFIRMED]
2806 P11  manual DHW recharge state/command       [LIKELY, direction-sensitive]
2806 P37  day room setpoint                       [CONFIRMED]
2806 P38  night room setpoint                     [CONFIRMED]
2806 P39-P41 timed-mode end data                   [CONFIRMED, mode-dependent]
             P7=0x14 Abwesend: minute/hour/weekday [CONFIRMED]
             P7=0x24 Urlaub: day/month/year         [day/month CONFIRMED; year strongly supported]

2004 P2   outside temperature                     [CONFIRMED]
2004 P17  unknown raw/status field                [UNKNOWN]
2004 P18  unknown status-like field               [UNKNOWN]
2004 P32  Gamma-side boiler/flow temperature      [LIKELY]

4002 P08  domestic hot-water actual temperature   [CONFIRMED, raw/2 °C]

010E      request Kessel PROG 1                   [CONFIRMED]
800E      Kessel weekly program 1                 [CONFIRMED]
010F      request Kessel PROG 2                   [CONFIRMED]
800F      Kessel weekly program 2                 [CONFIRMED]
0110      request Kessel PROG 3                   [CONFIRMED]
8010      Kessel weekly program 3                 [CONFIRMED]
800E/F/10 slot start/end                          [BCD, CONFIRMED]
800E/F/10 slot temperature                        [value/2 °C, CONFIRMED]
Kessel program temperature coupling to TAG-SOLL   [CONFIRMED observed behavior]

0112      request DHW weekly program              [CONFIRMED]
8012      DHW weekly program                      [CONFIRMED]
8012 slot start/end                               [BCD, CONFIRMED]
8012 slot byte 3                                 [likely WW setpoint raw/2; 0x64=50.0°C]

0114      request RS10 parameter block            [CONFIRMED]
8014      RS10 parameter/configuration block      [PARTIALLY DECODED]
8014 param#8  Reduziert: 0=ECO, 1=AbS             [CONFIRMED]
8014 param#30 selected Kessel program 1/2/3       [CONFIRMED]
8014 param#35 Steilheit = raw/20                  [CONFIRMED]
8014 param#81 Legionellen-WW                      [field CONFIRMED; 0=AUS, 1=Mon..7=Sun; 0/1/2 controlled, 4 observed]
8014 param#92 selected DHW program                [field CONFIRMED; values 2/3 CONFIRMED, 1 LIKELY]

0905      controller date/time                    [partially decoded]
```

## 27. Next targets

1.  Determine transmitter ownership and exact semantics of `06`, `A3`,
    `90`, `FC`, `FF`, `7D` and the one-off startup `C0` marker.
2.  Build a passive bus state model from the measured ninth-bit timing.
3.  Determine the exact meaning of address field B, especially `0x20`,
    and explain why identical `2806` payloads occur as both `10 -> 20`
    and `23 -> 20`.
4.  Confirm the central controller's physical type label (current
    evidence: Gamma 2B).
5.  Prototype minimum RS10 presence/slot behavior only after the state
    model is sufficiently understood.
6.  Continue decoding `2004`, `8014`, `4002`, `1005` and `2806` unknown
    fields.

## 28. Reverse-engineering methodology

New fields should preferably be identified using controlled A/B/A tests:

``` text
setting A
capture
setting B
capture
setting A
capture
```

Only one user-visible parameter should be intentionally changed. Direct
comparison with independently displayed values is also useful for
dynamic sensor readings.

The production integration and parser should remain
**passive/read-only**. Active experiments must be isolated, one-shot,
and performed with the physical RS10 disconnected unless bus
arbitration/coexistence has first been understood. Presence/slot
participation must be reproduced before any further heating-setting
writes are attempted.

## 29. Credits and prior work

This project builds on earlier community reverse-engineering work
concerning Gamma heating-control communication, including the
bogeyman/gamma GitHub Wiki and discussions on mikrocontroller.net.

Fields marked `CONFIRMED` here are based on controlled or direct-display
experiments on the installation described above.

## 30. Disclaimer

This is an unofficial reverse-engineering project and is not affiliated
with or endorsed by Guntamatic, Fischer or the manufacturer of the Gamma
RS10.

The documentation may contain errors and may not apply to other
controller or firmware versions. Use hardware connections and software
based on this information at your own risk.
