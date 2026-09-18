# Parser tests

The tests verify protocol primitives and the experimentally confirmed field mappings.

Run from the repository root:

```bash
python -m pytest -q
```

Test coverage includes:

- CRC-16/KERMIT check value
- Gamma frame construction/extraction
- `2806` confirmed fields
- all currently confirmed RS10 operating modes
- timed Party/Away end fields
- `2004` outside and boiler temperatures
- BCD decoding
- `0xFF` capture normalization
- frame deduplication and semantic `--changes`
- split-frame handling in the live extractor
- invalid CRC rejection

The tests intentionally use synthetic frames with valid CRC values rather than committing large raw captures to the repository.
