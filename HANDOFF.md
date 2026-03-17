# CTI Pipeline — HANDOFF (Updated 2026-03-17 17:00)

## Open PRs
- **PR #15**: fix/p0-pipeline-fidelity → CTI (20 commits) — deterministic pipeline
- **PR #16**: feature/llm-validation → CTI (12 commits) — LLM validation + combined mode
- **experiment/llm-precision** — experiment branch with test framework

## Final Performance (8 sources, 4 threat actors)

```
Metric              Original   Offline    Combined    Sr Analyst
TTP Recall               5%      65%         55%         100%
TTP Precision            1%      11%         20%         100%
Rel Recall               0%      20%         84%         100%
Hallucinations         N/A      N/A          0%          N/A
Time/file             ~8min     ~13s        ~54s       30-60min
LLM Required            Yes       No     Optional        N/A
```

## Tested On
- BlackCat/ALPHV (5 reports: Sophos, Symantec, Talos, Unit42, Varonis)
- Berserk Bear/Dragonfly (CISA AA20-296A)
- LockBit 3.0 (CISA AA23-075A)
- APT41/Double Dragon (supply chain)

## LLM Experiment Results (0% hallucination confirmed)
```
Experiment                TTP-P   Rel-R   Halluc   Time/f
Baseline (no LLM)          11%     20%     N/A      13s
Denial medium (>0.25)      23%     24%      0%     12.4s
Rel discovery only         15%     87%      0%      9.6s
Combined (2+4)             20%     84%      0%      54s
```

## MITRE AIP Connection
SSH tunnel: `ssh -R 8443:models.k8s.aip.mitre.org:443 caldera@192.168.1.185 -N`
Model: Devstral (24B)

## Next Steps
- OpenCTI integration for enrichment beyond adversary emulation
- Infrastructure/IaC extraction branch (OS, services, endpoints from CTI)
- GitLab tunnel setup (port 8444)
- File consolidation (remove old cti_relationships.py)
