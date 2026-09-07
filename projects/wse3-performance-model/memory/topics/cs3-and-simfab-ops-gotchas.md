# CS-3 and simfab operational gotchas

- `cs3-run` does not forward heredoc/stdin into nested SSH commands; write a remote script or pass a command string.
- Variables intended for `cs_python` in Singularity need `SINGULARITYENV_` prefixes; `cs3-tmux ensure` needs a tty in non-interactive use.
- simfab 0-byte receive / kernel-stall aborts can be host-service stalls (~90 s) rather than kernel bugs; validate by replaying real frames or keeping the host servicing the runtime.
