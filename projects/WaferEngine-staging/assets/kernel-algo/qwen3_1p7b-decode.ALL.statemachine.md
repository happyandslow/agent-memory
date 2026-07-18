# qwen3_1p7b-decode — task/fn state machines (all kernels)

> **Aggregate index** of the per-kernel task/fn state-machine set for `qwen3_1p7b-decode`. Each kernel below is an independent Mermaid `stateDiagram-v2` (not merged into one diagram), with links to its standalone detail doc (full per-state prose + `file:line` citations) and its rendered SVG under `assets/kernel-algo/`. Control-flow companion to the algo walkthroughs. Ref config `test_sim_2x2block_kv_varlen.json`.

**Edge legend (shared by every diagram):** `call:` = synchronous same-stack `fn` call · `async:` = microthread `.activate`/`@activate` callback (incl. cross-module comm_pe) · `gate:` = `@unblock` of a `@block`-ed task · `event:` = fabric recv park. `[task]` marks a real scheduling unit; unmarked nodes are `fn`s on a task's stack.

## Index

| Kernel | Detail doc | Rendered | In-page diagram |
|---|---|---|---|
| `decode.csl` — main decode compute PE | [qwen3_1p7b-decode.decode.statemachine.md](../../assets/kernel-algo/qwen3_1p7b-decode.decode.statemachine.md) | [svg](../../assets/kernel-algo/qwen3_1p7b-decode.decode.statemachine.svg) | [↓](#decode) |
| `decode_strip.csl` — strip/helper PE | [qwen3_1p7b-decode.decode_strip.statemachine.md](../../assets/kernel-algo/qwen3_1p7b-decode.decode_strip.statemachine.md) | [svg](../../assets/kernel-algo/qwen3_1p7b-decode.decode_strip.statemachine.svg) | [↓](#decode_strip) |
| `demux.csl` — host token-id ingress | [qwen3_1p7b-decode.demux.statemachine.md](../../assets/kernel-algo/qwen3_1p7b-decode.demux.statemachine.md) | [svg](../../assets/kernel-algo/qwen3_1p7b-decode.demux.statemachine.svg) | [↓](#demux) |
| `ht_head.csl` — embedding LUT (vocab-rotation ring) | [qwen3_1p7b-decode.ht_head.statemachine.md](../../assets/kernel-algo/qwen3_1p7b-decode.ht_head.statemachine.md) | [svg](../../assets/kernel-algo/qwen3_1p7b-decode.ht_head.statemachine.svg) | [↓](#ht_head) |
| `ht_tail.csl` — output head | [qwen3_1p7b-decode.ht_tail.statemachine.md](../../assets/kernel-algo/qwen3_1p7b-decode.ht_tail.statemachine.md) | [svg](../../assets/kernel-algo/qwen3_1p7b-decode.ht_tail.statemachine.svg) | [↓](#ht_tail) |
| `comm_pe.csl` — comm library (no main) | [qwen3_1p7b-decode.comm_pe.statemachine.md](../../assets/kernel-algo/qwen3_1p7b-decode.comm_pe.statemachine.md) | [svg](../../assets/kernel-algo/qwen3_1p7b-decode.comm_pe.statemachine.svg) | [↓](#comm_pe) |
| `mux.csl` — logits/token egress | [qwen3_1p7b-decode.mux.statemachine.md](../../assets/kernel-algo/qwen3_1p7b-decode.mux.statemachine.md) | [svg](../../assets/kernel-algo/qwen3_1p7b-decode.mux.statemachine.svg) | [↓](#mux) |
| `kv_ingress_adaptor.csl` — host->decode KV ingress adaptor | [qwen3_1p7b-decode.kv_ingress_adaptor.statemachine.md](../../assets/kernel-algo/qwen3_1p7b-decode.kv_ingress_adaptor.statemachine.md) | [svg](../../assets/kernel-algo/qwen3_1p7b-decode.kv_ingress_adaptor.statemachine.svg) | [↓](#kv_ingress_adaptor) |
| `kv_ingress_injector.csl` — host->decode KV injector | [qwen3_1p7b-decode.kv_ingress_injector.statemachine.md](../../assets/kernel-algo/qwen3_1p7b-decode.kv_ingress_injector.statemachine.md) | [svg](../../assets/kernel-algo/qwen3_1p7b-decode.kv_ingress_injector.statemachine.svg) | [↓](#kv_ingress_injector) |
| route-only files | — | — | [↓ note](#route-only) |

<a id="decode"></a>
## `decode.csl` — main decode compute PE

Single-token (m=1) decode over a slice of layers; two-pass safe softmax (max all-reduce, subtract global max, sum all-reduce); per-layer + per-iteration (iter_num) re-arm.

```mermaid
stateDiagram-v2
    classDef task fill:#fde68a,stroke:#b45309,color:#111
    classDef ext fill:#e5e7eb,stroke:#6b7280,color:#111

    [*] --> dispatch_init_task : async: comptime activate(dispatch_init_id) L1838

    state "kv_ingress_resume [task]" as kv_ingress_resume
    state "round_reingress [task]" as round_reingress

    state Dispatch {
        state "dispatch_init_task [task]" as dispatch_init_task
        state "StripRelay (decode_strip.csl)" as StripRelay
        dispatch_init_task --> StripRelay : call: real strip activate_sender(i_own) L1727
        dispatch_init_task --> StripRelay : call: real strip activate_receiver(i_own) L1733
        dispatch_init_task --> [*] : fake strip return L1678
    }
    dispatch_init_task --> init_task_t : async: block PE activate(init_task_id) L1670

    state Boot {
        state "init_task_t [task]" as init_task_t
        state "round_reset" as round_reset
        init_task_t --> round_reset : call: init_once then round_reset [ingress==0] L1737 L1745
    }
    init_task_t --> kv_ingress : call: init_once then kv_ingress [ingress!=0] L1737 L1742
    round_reset --> main : async: activate(main_id) L1746 L1752

    state KvIngress {
        state "kv_ingress" as kv_ingress
        state "kv_ingress_meta_phase" as kv_ingress_meta_phase
        state "kv_ingress_layer_phase" as kv_ingress_layer_phase
        state "kv_ingress_oq_empty [comm_pe empty-q handler]" as kv_ingress_oq_empty
        kv_ingress --> kv_ingress_meta_phase : call: west-shift metainfo tile L1646
        kv_ingress_meta_phase --> kv_ingress_layer_phase : call: per (layer,K then V) [retain_rt==0] L1650 L1651
        kv_ingress_layer_phase --> kv_ingress_layer_phase : call: layer++ K|V shift loop L1649
        kv_ingress --> kv_ingress_oq_empty : call: flush_then_resume queue_flush OQ7 flag0 L1654 commpe1366
    }
    kv_ingress_meta_phase --> kv_ingress_oq_empty : call: retain_rt!=0 skip layers then flush L1647 L1654
    kv_ingress_oq_empty --> kv_ingress_resume : async: flag0 activate(kv_ingress_resume_id) commpe1356
    kv_ingress_resume --> round_reset : call: round_reset() L1751

    state MainLoop {
        state "main [task]" as main
        state "decode_struct" as decode_struct
        state "round_barrier" as round_barrier
        main --> decode_struct : call: recv X, Y-bcast, snapshot X, decode_struct [X0>=STOP] L1807
        decode_struct --> main : call: return, inter_block_send_z, i++ next step L1811 L1815
        main --> round_barrier : call: loop done N steps or EOS break [ingress!=0] L1824
    }
    main --> [*] : ingress==0 single-shot end L1827
    round_barrier --> kv_ingress_oq_empty : call: kv_rebind_to_ingress_flush queue_flush OQ7 flag1 L1825 commpe1370
    kv_ingress_oq_empty --> round_reingress : async: flag1 activate(round_reingress_id) commpe1361
    round_reingress --> kv_ingress : call: kv_ingress() next round L1758

    state LayerLoop {
        state "decode_layer_body" as decode_layer_body
        state "rmsnorm_x" as rmsnorm_x
        state "qkv_proj (xq|xk|xv + QKV allreduce)" as qkv_proj
        state "qk_norm_q_k" as qk_norm_q_k
        state "apply_rope_q" as apply_rope_q
        state "apply_rope_k" as apply_rope_k
        state "process_kv (cursor gate)" as process_kv
        state "score_matvec_mult" as score_matvec_mult
        state "softmax_score" as softmax_score
        state "output_matvec_mult" as output_matvec_mult
        state "o_matvec_mult" as o_matvec_mult
        state "attn_residual_add" as attn_residual_add
        state "rmsnorm_z" as rmsnorm_z
        state "upgate_ffn (up|gate + ZZ allreduce)" as upgate_ffn
        state "ffn_gate_silu" as ffn_gate_silu
        state "ffn_swiglu_mul" as ffn_swiglu_mul
        state "down_matvec_mult" as down_matvec_mult
        state "ffn_residual_add" as ffn_residual_add

        decode_layer_body --> rmsnorm_x : call: L1426
        rmsnorm_x --> qkv_proj : call: L1428
        qkv_proj --> qk_norm_q_k : call: reconfig_axis(3) L1434 L1438
        qk_norm_q_k --> apply_rope_q : call: L1440
        apply_rope_q --> apply_rope_k : call: L1441
        apply_rope_k --> process_kv : call: L1444
        process_kv --> score_matvec_mult : call: owner py writes cache iter_num++ L1446
        score_matvec_mult --> softmax_score : call: reconfig_axis(0) L1448 L1450
        softmax_score --> output_matvec_mult : call: L1452
        output_matvec_mult --> o_matvec_mult : call: reconfig_axis(1) L1454 L1456
        o_matvec_mult --> attn_residual_add : call: L1458
        attn_residual_add --> rmsnorm_z : call: reconfig_axis(0) L1460 L1462
        rmsnorm_z --> upgate_ffn : call: L1464
        upgate_ffn --> ffn_gate_silu : call: ZZ allreduce+cast L1466 L1469
        ffn_gate_silu --> ffn_swiglu_mul : call: L1471
        ffn_swiglu_mul --> down_matvec_mult : call: reconfig_axis(1) L1473 L1475
        down_matvec_mult --> ffn_residual_add : call: L1477
    }
    decode_struct --> decode_layer_body : call: rope_step_advance, set_layer(l), l<layers L1493 L1496
    ffn_residual_add --> decode_struct : call: reconfig_axis(0), step++, persist bank, X=Z, next layer L1479 L1498

    class dispatch_init_task,init_task_t,main,kv_ingress_resume,round_reingress task
    class StripRelay,kv_ingress_oq_empty ext
```

**Links:** detail doc → [qwen3_1p7b-decode.decode.statemachine.md](../../assets/kernel-algo/qwen3_1p7b-decode.decode.statemachine.md) · rendered SVG → [qwen3_1p7b-decode.decode.statemachine.svg](../../assets/kernel-algo/qwen3_1p7b-decode.decode.statemachine.svg)

<a id="decode_strip"></a>
## `decode_strip.csl` — strip/helper PE

Edge/IO strip in the decode band (see source for exact role); its own small task machine.

```mermaid
stateDiagram-v2
    [*] --> SenderChain : call activate_sender from dispatch_init (decode L1727)
    [*] --> ReceiverChain : call activate_receiver from dispatch_init (decode L1733)

    state SenderChain {
        [*] --> activate_sender
        state "activate_sender — iter=0, fwd_extent=i_own*B, kick head" as activate_sender
        state "strip_sender_recv_t — pull OWN B*dim from sender block (q0 IQ)" as s_recv
        state "strip_sender_fwd_t — relay upstream own_0..i-1 through K-pipe CE" as s_fwd
        state "strip_sender_inject_t — inject OWN onto K-pipe tx (q7 OQ)" as s_inject

        activate_sender --> s_recv : activate(recv) L153
        s_recv --> s_fwd : async recv-done, activate(fwd) L79-80
        s_recv --> [*] : return iter>=MAX or (stop and KV=0) L70,73-74
        s_fwd --> s_inject : if fwd_extent>0 async fwd-done, activate(inject) L95-96
        s_fwd --> s_inject : else activate(inject) L98
        s_inject --> s_recv : async inject-done, activate(recv) loop L106
    }

    state ReceiverChain {
        [*] --> activate_receiver
        state "activate_receiver — iter=0, fwd_extent=(M-1-i_own)*B, kick head" as activate_receiver
        state "strip_recv_consume_t — consume OWN B*dim from K-pipe rx (q2 IQ)" as r_consume
        state "strip_recv_postfwd_t — relay downstream own_j+1..M-1 through K-pipe CE" as r_postfwd
        state "strip_recv_broadcast_t — broadcast OWN to block on intra_row_bcast (q0 OQ)" as r_broadcast

        activate_receiver --> r_consume : activate(consume) L159
        r_consume --> r_postfwd : async consume-done, activate(postfwd) L120-121
        r_consume --> [*] : return iter>=MAX or (stop and KV=0) L111,114-115
        r_postfwd --> r_broadcast : if fwd_extent>0 async fwd-done, activate(broadcast) L135-136
        r_postfwd --> r_broadcast : else activate(broadcast) L138
        r_broadcast --> r_consume : async bcast-done, activate(consume) loop L145
    }

    note right of SenderChain
        STOP-X (buf[0] below -60000) detected in s_fwd L88-90 sets strip_stop;
        the full 3-phase relay still runs this step so the K-pipe per-step
        wavelet count is preserved. KV_TRANSFER=1: head clears strip_stop and
        re-parks (continuous relay across rounds). KV_TRANSFER=0: head returns,
        ending the chain. Same STOP logic in r_postfwd L128-130.
    end note

    classDef entry fill:#e3f2fd,stroke:#1565c0,color:#0d47a1;
    class activate_sender entry
    class activate_receiver entry
```

**Links:** detail doc → [qwen3_1p7b-decode.decode_strip.statemachine.md](../../assets/kernel-algo/qwen3_1p7b-decode.decode_strip.statemachine.md) · rendered SVG → [qwen3_1p7b-decode.decode_strip.statemachine.svg](../../assets/kernel-algo/qwen3_1p7b-decode.decode_strip.statemachine.svg)

<a id="demux"></a>
## `demux.csl` — host token-id ingress

Peel/forward chain (decode variant, multi-round / per-iteration re-arm).

```mermaid
stateDiagram-v2
    [*] --> init : async activate(init) comptime L163

    state "init — async-recv 1 ready sentinel from HT_head col0, then arm main" as init

    init --> PerRound : async ready lands, activate(main) L106

    state PerRound {
        [*] --> main
        state "main — peel OWN B off shared src_q FIFO, branch on is_last_pe" as main
        state "forward_and_out — non-last PE: emit own east + forward remainder south" as forward_and_out
        state "send_out — last PE: emit own block east only" as send_out
        state "next_cycle — join both microthreads, re-arm per round if KV_TRANSFER" as next_cycle

        main --> forward_and_out : async peel OWN, activate(forward_and_out) — else L118
        main --> send_out : async peel OWN, activate(send_out) — if is_last_pe L113

        forward_and_out --> next_cycle : async forward south, unblock(next_cycle) L131
        forward_and_out --> next_cycle : async emit east, activate(next_cycle) L133
        send_out --> next_cycle : async emit east, activate(next_cycle) L124

        next_cycle --> main : if KV_TRANSFER block(next_cycle) re-arm + activate(main) L141-142
    }

    next_cycle --> [*] : if KV_TRANSFER==0 idle (single-shot bake)

    note right of next_cycle
        comptime block(next_cycle) at L159 on non-last PE.
        The south forward unblock(next_cycle) + the east emit
        activate(next_cycle) must BOTH land to fire it — the
        two-microthread join. On the last PE it is the single
        activate from send_out.
    end note

    classDef entry fill:#e3f2fd,stroke:#1565c0,color:#0d47a1;
    class init entry
```

**Links:** detail doc → [qwen3_1p7b-decode.demux.statemachine.md](../../assets/kernel-algo/qwen3_1p7b-decode.demux.statemachine.md) · rendered SVG → [qwen3_1p7b-decode.demux.statemachine.svg](../../assets/kernel-algo/qwen3_1p7b-decode.demux.statemachine.svg)

<a id="ht_head"></a>
## `ht_head.csl` — embedding LUT (vocab-rotation ring)

Per-token / per-iteration ingress re-arm.

```mermaid
stateDiagram-v2
    state "init (L243)" as init
    state "main (L293)" as main
    state "embed_gather_dispatch fn (L134)" as dispatch

    [*] --> init : async: comptime activate(init) [entry L373]
    init --> main : async: init route-paint done, activate(main) L282

    state PerRound {
        state PerStep {
            main --> dispatch : call: step>=1 and head_is_active, per token b L334
        }
    }

    main --> main : async: kv_stream_ingress re-arm, activate(main) L349

    note right of main
        per-step loop while ht_step<n_steps (L300),
        internal to main (no task transition):
        step 0 parks pre_embed_x; step>=1 drains token,
        STOP_TOK breaks; diag emits embed_buf east.
    end note
    note left of dispatch
        sync leaf: 2-phase W_E gather via UP_*/DOWN_*
        @fmovh shuttles (blocking DSDs, no callback);
        returns to main. Called bsz times per step.
    end note

    state Legend {
        state "async: @activate task activation" as L1
        state "call: direct synchronous fn call" as L2
    }
```

**Links:** detail doc → [qwen3_1p7b-decode.ht_head.statemachine.md](../../assets/kernel-algo/qwen3_1p7b-decode.ht_head.statemachine.md) · rendered SVG → [qwen3_1p7b-decode.ht_head.statemachine.svg](../../assets/kernel-algo/qwen3_1p7b-decode.ht_head.statemachine.svg)

<a id="ht_tail"></a>
## `ht_tail.csl` — output head

RMSNorm to lm_head GEMV to top-K to sampling + TSC sentinel; two-phase tail reduce; per-iteration re-arm.

```mermaid
stateDiagram-v2
    state "tail_init task (L1201)" as tail_init
    state "tail_main task (L1288)" as tail_main

    [*] --> tail_init : async comptime activate(tail_init) [entry L1453]
    tail_init --> tail_main : async activate(tail_main) L1282
    tail_main --> tail_main : async re-arm activate(tail_main) L1423 [KV_TRANSFER=1; else terminal]

    state tail_init {
        state "derive coords + Y/X chain ids (L1202-1213)" as ti_derive
        state "write_Y_routes_tail fn (L490)" as ti_wY
        state "paint static routes: north tok L1220, z_drain L1231/1233, south L1241, xready barrier L1252; seed PRNG L1275; enable TSC L1279" as ti_routes
        [*] --> ti_derive
        ti_derive --> ti_wY : call write_Y_routes_tail() L1215
        ti_wY --> ti_routes : return
        ti_routes --> [*]
    }

    state tail_main {
        state "per-round reset (L1290): tail_step=0, clear done_flag/pred_token; re-seed PRNG L1296" as tm_reset
        state "budget header (KV_TRANSFER=1, L1302): mov32 recv N off Z-drain, overwrite n_steps, re-forward south(mux)+north(HT_head)" as tm_hdr
        state "dump_round += 1 (L1418)" as tm_dumpround

        [*] --> tm_reset
        tm_reset --> tm_hdr : KV_TRANSFER=1 read budget
        tm_reset --> tm_step : KV_TRANSFER=0 (n_steps baked)
        tm_hdr --> tm_step : enter per-step loop

        state tm_step {
            state "TSC start (is_tsc_pe, tail_step==warmup): sample start L1317" as st_tsc_start
            state "drain Z: fmovh z_slice from z_recv L1320" as st_drainZ
            state "STOP-Z check L1327: z_slice[0] < STOP_THRESHOLD" as st_stopcheck
            state "TSC burst (is_tsc_pe): async mov32 8-u32 L1336" as st_stopburst
            state "dump_logits_step0 (dbg, step0, root row L1353)" as st_dump
            state "north emit L1389: sampled token to HT_head (skip last step)" as st_north
            state "south emit L1396: root east-most topk_val+arg+pred to mux OQ0" as st_south
            state "TSC end (is_tsc_pe, last iter): sample end + async mov32 burst L1413" as st_tsc_end

            [*] --> st_tsc_start : loop iter (tail_step)
            st_tsc_start --> st_drainZ : event Z arrives from last block
            st_drainZ --> st_stopcheck
            st_stopcheck --> st_stopburst : STOP-Z sentinel
            st_stopburst --> [*] : break loop L1338
            st_stopcheck --> st_rmsnorm : normal step, call tail_final_rmsnorm() L1342

            state st_rmsnorm {
                state "phase1 per-batch local sumsq (L432)" as rn_sumsq
                state "tail_reduce_bsz_f32 fn (L825)" as rn_wrap
                state "tail_reduce_2phase fn (L732), do_broadcast=1, Y allreduce" as rn_reduce
                state "phase3 normalize + cast + mul W_final_norm (L459)" as rn_norm
                [*] --> rn_sumsq
                rn_sumsq --> rn_wrap : call tail_reduce_bsz_f32() L454
                rn_wrap --> rn_reduce : call tail_reduce_2phase() L826
                rn_reduce --> rn_norm : return
                rn_norm --> [*]
            }

            st_rmsnorm --> st_lmhead : call tail_lm_head_matvec() L1344

            state st_lmhead {
                state "vecmat_computation_lm fn (L383)" as lm_vecmat
                state "gemv_lm_step fmachs (L378) via map, loop bsz x V_per_pe_x" as lm_step
                [*] --> lm_vecmat : call vecmat_computation_lm() L413
                lm_vecmat --> lm_step : map over left_vector L395
                lm_step --> lm_step : per-K fmachs accumulate
                lm_step --> [*] : per-batch done L388
            }

            st_lmhead --> st_logred : call tail_logits_reduce_bsz_vocab() L1346

            state st_logred {
                state "tail_reduce_2phase fn (L732), do_broadcast=0, len bsz x V_per_pe_x" as lr_reduce
                [*] --> lr_reduce : call tail_reduce_2phase() L727
                lr_reduce --> [*] : logits land on root_2nd_phase row
            }

            st_logred --> st_dump : root row + dbg_logit_dump + step0 L1352
            st_dump --> st_topk : proceed
            st_logred --> st_topk : root row (normal) L1359
            st_logred --> st_north : non-root skip top-K

            state st_topk {
                state "write_X_routes_tail fn (L602): repaint reduce colors Y to X" as tk_wX
                state "xready barrier L1364: root_2nd_phase_x sends go / others recv (event)" as tk_barrier
                state "tail_local_topk fn (L862): size-K min-heap + block-max prune, loop bsz" as tk_local
                state "tail_topk_mergereduce_x fn (L956): X 2-phase reduce, per-hop merge + bcast" as tk_merge
                state "topk_merge_local fn (L930): 2-pointer K-list merge, loop bsz" as tk_mergefn
                state "tail_sample_token fn (L1085): softmax, top-p, PRNG draw (root_2nd_phase_x only)" as tk_sample
                state "predtok X-bcast L1375 send / L1377 recv" as tk_predbcast
                state "write_Y_routes_tail fn (L490): restore Y routes" as tk_wY
                [*] --> tk_wX : call write_X_routes_tail() L1360
                tk_wX --> tk_barrier : return
                tk_barrier --> tk_local : call tail_local_topk() L1369
                tk_local --> tk_merge : call tail_topk_mergereduce_x() L1370
                tk_merge --> tk_mergefn : call topk_merge_local() per hop L962
                tk_mergefn --> tk_merge : return per hop
                tk_merge --> tk_sample : call tail_sample_token() if root_2nd_phase_x L1374
                tk_merge --> tk_predbcast : else recv bcast L1377
                tk_sample --> tk_predbcast : return
                tk_predbcast --> tk_wY : call write_Y_routes_tail() L1379
                tk_wY --> [*]
            }

            st_topk --> st_north : proceed
            st_north --> st_south
            st_south --> st_tsc_end : is_tsc_pe and tail_step==n_steps-1 L1405
            st_south --> st_tsc_start : while tail_step<n_steps, next step L1313
            st_south --> [*] : loop done (non-tsc last step)
            st_tsc_end --> [*] : loop done (tsc last step)
        }

        tm_step --> tm_dumpround : loop exit (n_steps reached or STOP break)
        tm_dumpround --> [*]
    }

    note right of tm_reset
        Per-round loop: tail_main re-activates itself (L1423) only
        when KV_TRANSFER=1, re-parking on the next round's budget
        header + Z. KV_TRANSFER=0 is single-shot (no re-arm).
    end note
    note right of st_drainZ
        Event-driven fabric parks (not activate/block):
        budget header L1303, z_recv L1320, xready L1367.
    end note
    note left of st_tsc_end
        Fire-and-forget async sends (no callback, not activation
        edges): TSC burst L1336 (STOP path) and L1413 (last iter).
    end note

    state Legend {
        state "async: microthread callback / activate (scheduling edge)" as L1
        state "call: direct synchronous fn call (same stack)" as L2
        state "event: blocking fabric recv park (not activate/block)" as L3
    }
```

**Links:** detail doc → [qwen3_1p7b-decode.ht_tail.statemachine.md](../../assets/kernel-algo/qwen3_1p7b-decode.ht_tail.statemachine.md) · rendered SVG → [qwen3_1p7b-decode.ht_tail.statemachine.svg](../../assets/kernel-algo/qwen3_1p7b-decode.ht_tail.statemachine.svg)

<a id="comm_pe"></a>
## `comm_pe.csl` — comm library (no main)

Per-collective sub-machines: ~8 all_reduce variants (Y/X P-1, band-scoped P-7, fmaxh max, QKV/ZZ fusion) + reconfig route machine + inter-region pipeline edges.

```mermaid
stateDiagram-v2
    %% qwen3_1p7b-decode comm_pe.csl — library, NO single main, NO tasks.
    %% One sub-machine per collective driver; the only async machine is KV-ingress rebind.

    %% ================= INIT (boot, called once from decode.csl init) =============
    state Init {
        state "init (L630)" as init
        state "precompute_route_words (L599)" as precompute_route_words
        [*] --> init : boot (decode init activates init_task)
        init --> precompute_route_words : call: L662
        init --> write_Y_routes : call: boot Y-active L663
        init --> write_intra_row_bcast_routes : call: L664
    }
    note right of init
        also set_route_2tx for INTER_A/INTER_B colors inline (L665-666),
        and caches this PE's IQ7/OQ7 ingress color binding (col-parity
        swap) for the rebind handler if kv_stream_ingress != 0 (L671-680)
    end note

    %% ================= RECONFIG route machine (the ONE route-switch) =============
    state Reconfig {
        state "reconfig_allreduce_axis (L1335)" as reconfig
        state "write_Y_routes (L558)" as write_Y_routes
        state "write_X_routes (L550)" as write_X_routes
        state "write_X_kv_head_routes (L568)" as write_X_kv_head_routes
        [*] --> reconfig
        reconfig --> write_Y_routes : call: axis==0 dim L1337
        reconfig --> write_X_routes : call: axis==1 head L1339
        reconfig --> write_X_kv_head_routes : call: axis==3 kv-head L1341
    }
    note right of reconfig
        C1 safety: repaints SHARED reduce/bcast colors with no barrier.
        Race-free ONLY because every all_reduce_* is synchronous + ends
        in a multi-tx broadcast (self-fencing) L1325-1334
    end note

    %% ================= TWO-PHASE ALL-REDUCE (P-block, Y/X axis) ==================
    state AllReduce_TwoPhase {
        state "all_reduce_bsz_f32 (L685)" as ar_f32
        state "all_reduce_bsz_dim (L1035)" as ar_dim
        state "all_reduce_bsz_dim_QKV_fusion (L1115)" as ar_qkv
        state "all_reduce_bsz_ffn_dim_ZZ_fusion (L1195)" as ar_zz
        state "all_reduce_bsz_gqa_group (L767)" as ar_gqa
        state "all_reduceMax_bsz_gqa_group (L848)" as ar_max
        state two_phase_body {
            state "1st-phase reduce (remainder chain to root_1st)" as p1
            state "2nd-phase reduce (quotient chain to root_2nd)" as p2
            state "broadcast (root_2nd mov32/mov16 fanout)" as p3
            [*] --> p1
            p1 --> p2 : sync: straight-line
            p2 --> p3 : sync: straight-line
            p3 --> [*] : sync: bcast done (self-fencing)
        }
        [*] --> ar_f32 : RMSNorm sumsq entry (fp32)
        [*] --> ar_dim : hidden X/Z reduce entry
        [*] --> ar_qkv : QKV-fusion reduce entry
        [*] --> ar_zz : FFN gate+up (ZZ) reduce entry
        [*] --> ar_gqa : softmax sum entry
        [*] --> ar_max : softmax max entry (fmaxh/mov16)
        ar_f32 --> two_phase_body : sync: inline phases
        ar_dim --> two_phase_body : sync: inline phases
        ar_qkv --> two_phase_body : sync: inline phases
        ar_zz --> two_phase_body : sync: inline phases
        ar_gqa --> two_phase_body : sync: inline phases
        ar_max --> two_phase_body : sync: max variant
    }

    %% ================= BAND-SCOPED ALL-REDUCE (kv-head, single-chain) ============
    state AllReduce_Band {
        state "all_reduce_bsz_gqa_group_kv_len_kv_head_scoped (L931)" as ar_score
        state "all_reduce_qk_kv_head_scoped (L987)" as ar_qk
        state band_body {
            state "band chain to kv_head_root (pes_per_kv_head gt 1)" as bp1
            state "band-scoped broadcast (kv_head_root mov32)" as bp2
            [*] --> bp1
            bp1 --> bp2 : sync: straight-line
            bp2 --> [*] : sync: bcast done
        }
        [*] --> ar_score : attn score reduce entry
        [*] --> ar_qk : QK-Norm sumsq entry
        ar_score --> band_body : sync: inline
        ar_qk --> band_body : sync: inline
    }
    note right of ar_qk
        no-op when pes_per_kv_head == 1 (single PE per
        kv-head already holds the full sum) L939,973,993,1026
    end note

    %% ================= INTER-REGION pipeline stages (sync leaves) ================
    state InterRegionPipeline {
        state "inter_block_recv_x_sync (L1281)" as recv_x
        state "intra_block_x_broadcast_y_bsz_dim (L1295)" as bcast_x
        state "inter_block_send_z (L1308)" as send_z
        [*] --> recv_x : chain X-recv entry (has_inter_recv)
        [*] --> bcast_x : Y-broadcast entry (intra_row_bcast_color)
        [*] --> send_z : chain Z-send entry (has_inter_send)
    }
    note right of send_z
        three independent sync leaves; the recv to compute to
        bcast to send ordering is decode.csl-sequenced, not here
    end note

    %% ================= KV-INGRESS REBIND (the only async machine) ================
    state KVIngressRebind {
        state "kv_ingress_flush_then_resume (L1364)" as flush_resume
        state "kv_rebind_to_ingress_flush (L1368)" as rebind_ingress
        state "kv_ingress_oq_empty (L1351)" as oq_empty
        [*] --> flush_resume : startup ingress done, flag=0
        [*] --> rebind_ingress : per-round re-arm, flag=1
        flush_resume --> oq_empty : async: queue_flush OQ7 empty L1366
        rebind_ingress --> oq_empty : async: queue_flush OQ7 empty L1370
        oq_empty --> ext_kv_resume : async: activate if flag==0 L1356
        oq_empty --> ext_round_reingress : async: activate if flag==1 L1361
    }

    %% ================= EXTERNAL continuations (in decode.csl) ====================
    state "ext: kv_ingress_resume_id (decode)" as ext_kv_resume
    state "ext: round_reingress_id (decode)" as ext_round_reingress

    %% ================= LEGEND ====================================================
    state Legend {
        state "call:  direct synchronous fn call" as Lc
        state "async: queue_flush drain to empty-queue handler OR activate(id)" as La
        state "ext:   continuation task bound in decode.csl" as Le
        state "comptime: queues initialize_queue; OQ7 empty handler kv_ingress_oq_empty set_empty_queue_handler L1381; NO tasks, NO block, NO microthreads" as Lcomp
    }
```

**Links:** detail doc → [qwen3_1p7b-decode.comm_pe.statemachine.md](../../assets/kernel-algo/qwen3_1p7b-decode.comm_pe.statemachine.md) · rendered SVG → [qwen3_1p7b-decode.comm_pe.statemachine.svg](../../assets/kernel-algo/qwen3_1p7b-decode.comm_pe.statemachine.svg)

<a id="mux"></a>
## `mux.csl` — logits/token egress

Serialize through a collector PE to host; per-token re-armed chain.

```mermaid
stateDiagram-v2
    [*] --> init : comptime activate(init_id)

    state "init() - read budget header N, reset step" as init
    state "main() - drain step blob from north" as main
    state "send() - forward blob east to host" as send
    state "next() - step++, early-stop or loop decision" as next
    state "tsc_recv() - drain 8-u32 TSC burst" as tsc_recv
    state "tsc_send() - forward TSC east, re-arm or done" as tsc_send

    init --> main : async: activate(main_id)

    state per_step_loop {
        main --> send : async: mov32 done, activate(send_id)
        send --> next : async: mov32 done, activate(next_id)
        next --> main : async: activate(main_id), step lt N and not STOP
    }

    next --> tsc_recv : async: activate(tsc_recv_id), STOP_TOK or step ge N
    tsc_recv --> tsc_send : async: mov32 done, activate(tsc_send_id)
    tsc_send --> init : async: mov32 done, activate(init_id), KV=1 re-arm
    tsc_send --> [*] : mov32 done, no callback, KV=0 done

    note right of init : only east-most PE (is_last_pe==1) armed, others inert. init parks on the 1-wavelet header recv when kv_stream_ingress is nonzero
    note right of next : per-step back-edge to main runs steps 0 to N-1
    note right of tsc_send : KV=1 re-arms init for the next round (per-request loop)
```

**Links:** detail doc → [qwen3_1p7b-decode.mux.statemachine.md](../../assets/kernel-algo/qwen3_1p7b-decode.mux.statemachine.md) · rendered SVG → [qwen3_1p7b-decode.mux.statemachine.svg](../../assets/kernel-algo/qwen3_1p7b-decode.mux.statemachine.svg)

<a id="kv_ingress_adaptor"></a>
## `kv_ingress_adaptor.csl` — host->decode KV ingress adaptor

Reshapes incoming KV for the varlen multi-round injection path; per-round re-arm.

```mermaid
stateDiagram-v2
    state "peel_meta0 — peel meta[0] of current row (task 8)" as peel_meta0
    state "relay_meta — latch n_segs_rt, re-emit meta[0] (task 9)" as relay_meta
    state "relay_metablk — relay remaining Pw-1 metas (task 11)" as relay_metablk
    state "relay_kv — relay one KV segment / branch (task 12)" as relay_kv
    state "advance_switch — emit SWITCH_ADV, next injector PE (task 13)" as advance_switch
    state "rearm — rewind row_idx, re-park on host stream (task 10)" as rearm

    [*] --> peel_meta0 : call comptime activate(peel) L126
    peel_meta0 --> relay_meta : async peel meta0 then activate(relay_meta) L64
    relay_meta --> relay_metablk : async re-emit meta0 then activate(relay_metablk) L71
    relay_metablk --> relay_kv : async relay metablk then activate(relay_kv) L75
    relay_kv --> relay_kv : async seg_idx<n_segs_rt more segments L95
    relay_kv --> advance_switch : call n_segs_rt==0 not last row L89
    relay_kv --> advance_switch : async row complete not last row L104
    relay_kv --> rearm : call n_segs_rt==0 last row L87
    relay_kv --> rearm : async row complete last row L101
    advance_switch --> peel_meta0 : async SWITCH_ADV then activate(peel) L109
    rearm --> peel_meta0 : call activate(peel) re-arm L116

    note right of relay_kv
      self-loop = per-segment fabin to fabout mov32 (KV never lands in PE mem)
      row loop advances row_idx 0..num_rows-1; each row picks advance_switch (mid) or rearm (last)
    end note
    note right of rearm
      per-round back-edge: input_q backpressures until next round's KV arrives
    end note
```

**Links:** detail doc → [qwen3_1p7b-decode.kv_ingress_adaptor.statemachine.md](../../assets/kernel-algo/qwen3_1p7b-decode.kv_ingress_adaptor.statemachine.md) · rendered SVG → [qwen3_1p7b-decode.kv_ingress_adaptor.statemachine.svg](../../assets/kernel-algo/qwen3_1p7b-decode.kv_ingress_adaptor.statemachine.svg)

<a id="kv_ingress_injector"></a>
## `kv_ingress_injector.csl` — host->decode KV injector

Injects adapted KV into the decode PEs cache per round; handshakes with the adaptor.

```mermaid
stateDiagram-v2
    state "peel_meta0 — peel meta[0] at pos0 (task 12)" as peel_meta0
    state "scatter_meta — latch n_segs_rt, re-emit meta[0] WEST (task 13)" as scatter_meta
    state "scatter_metablk — scatter Pw-1 metas WEST (task 14)" as scatter_metablk
    state "emit_scatter — take KV segments, scatter WEST (task 8)" as emit_scatter
    state "sync_src — TAIL source round_sync NORTH + re-arm (task 9)" as sync_src
    state "sync_wait — NON-TAIL park on round_sync (task 10)" as sync_wait
    state "sync_do — NON-TAIL reset switch + re-arm (task 11)" as sync_do

    [*] --> peel_meta0 : async comptime activate(peel) L143
    peel_meta0 --> scatter_meta : async peel meta0 then activate(scatter_meta) L81
    scatter_meta --> scatter_metablk : async re-emit meta0 then activate(scatter_metablk) L87
    scatter_metablk --> emit_scatter : async scatter metablk then activate(emit) L91
    emit_scatter --> emit_scatter : async seg_idx<n_segs_rt next KV seg L110
    emit_scatter --> sync_src : call n_segs_rt==0 and is_col_tail L101
    emit_scatter --> sync_src : async last KV seg and is_col_tail L115
    emit_scatter --> sync_wait : call n_segs_rt==0 non-tail L103
    emit_scatter --> sync_wait : async last KV seg non-tail L117
    sync_src --> peel_meta0 : call re-arm activate(peel) L123
    sync_wait --> sync_do : async park on round_sync activate(sync_do) L127
    sync_do --> peel_meta0 : call reset switch then activate(peel) L132

    note right of emit_scatter
      self-loop = one @mov32 fabin to fabout per KV segment
      (n_segs_rt = D_kv * plen; row never lands in PE mem)
    end note
    note right of sync_src
      side-effect L122 fire-and-forget mov32 sources round_sync NORTH (no callback, no edge)
    end note
    note left of sync_wait
      COLUMN-FENCE gate: park releases only when the TAIL sentinel
      threads up (RAMP copy); router auto-forwards the NORTH copy
    end note
```

**Links:** detail doc → [qwen3_1p7b-decode.kv_ingress_injector.statemachine.md](../../assets/kernel-algo/qwen3_1p7b-decode.kv_ingress_injector.statemachine.md) · rendered SVG → [qwen3_1p7b-decode.kv_ingress_injector.statemachine.svg](../../assets/kernel-algo/qwen3_1p7b-decode.kv_ingress_injector.statemachine.svg)

<a id="route-only"></a>
## Route-only files (no task/fn state machine)

- **`kv_fwd.csl`** — 11-line task-less pass-through relay (fabin->fabout), no task graph.
- **`route_util.csl`** — synchronous route-config helper `inline fn`s, called on the caller stack. No task graph.
- **`route_calc.csl`** — init-time per-PE route-direction calc returning `runtime_params_t`. Pure data-flow, no tasks.
