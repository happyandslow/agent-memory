# Transcript Indexes

Store compact transcript indexes, event records, and pointers here. Do not commit full raw Claude/Hermes transcript stores by default.

Suggested layout:

```text
transcripts/
  YYYY-MM-DD/
    <short-session-name>.md
    index-<host>.md
    events-<host>.jsonl
```

Group transcript pointers and session logs by date directory. Do not commit full raw transcript stores by default.

Each index entry should answer:

- date/time;
- agent/tool;
- short topic;
- outcome;
- where to find source/raw transcript locally if needed;
- memory files updated.
