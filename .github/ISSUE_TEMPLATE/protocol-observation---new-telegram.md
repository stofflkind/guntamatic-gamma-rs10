---
name: Protocol observation / New telegram
about: Describe this issue template's purpose here.
title: ''
labels: ''
assignees: ''

---

---
name: Protocol observation / New telegram
about: Report a new Gamma/RS10 telegram, field mapping or controlled observation
title: "[PROTOCOL] "
labels: protocol
assignees: ''
---

## Observation

Describe what you observed.

## Hardware

- Gamma controller model:
- Room station model:
- Heating system / boiler:
- RS485 adapter or capture method:

Do not post device serial numbers or other private identifiers.

## Test or operating condition

What was happening when the telegram was captured?

Examples: changing room setpoint, DHW charging, switching operating mode,
Legionella cycle, startup, idle operation.

## Telegram

Please provide the logical telegram if available.

```text
82 ...

If possible, also provide:

    direction / participants:

    TYPE:

    Bit 9 / marking-bit information:

    CRC status:

    timestamp or relative timing:

Before / after

If this was a controlled experiment:

Before:

...

Action performed:

...

After:

...

Interpretation

What do you think the telegram or changed bytes represent?

Please distinguish between:

    CONFIRMED — demonstrated by a controlled experiment

    LIKELY — strong evidence, not yet conclusively demonstrated

    HYPOTHESIS — plausible interpretation requiring further testing

Additional information

Add screenshots, short log excerpts or links to related issues/discussions if useful.

Please avoid uploading large raw captures unless they are necessary for the analysis.
