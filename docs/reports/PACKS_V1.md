# Benchmark packs v1

Generated from the pack manifests by `tools/p2_pipeline.py pack-report`. All values are exact certificate facts or deterministic baselines; no model has been run.


## `shadowtwins-ranked-v1` (ranked split, ranked)

* Instances: 30 (T1 single relocation: 10, T2 paired relocations: 10, T3 coordinated search: 10)
* `pack_hash`: `sha256:cadce9b7f82e71508295929e17483de31022f519c9b61319b8e83d3680201c36`
* `policy_hash`: `sha256:372ada53017c81e58dfddf367b9e536bd62e48d805ee888e6ca2a466ce9b95b5`
* Versions: rules `st-rules-1.0.0`, parser `st-parser-1.0.0`, evaluator `st-eval-1.0.0`, solver `st-solver-1.0.0`, protocol `st-protocol-1.0.0`, generator `st-gen-1.0.0`, token_panel `st-tokpanel-1.0.0`, local_search `st-ls-1.0.0`, policy `st-policy-1.0.0`, pack_format `st-pack-1`
* Independent verification: 30/30 certificates reproduced by `stverify`
* Prompt tokens (panel `st-tokpanel-1.0.0`, ceiling 800): max 699; per tokenizer max openai-o200k 612, openai-cl100k 612, llama-3.1 612, qwen-2.5 654, deepseek-v3 617, mistral-nemo 657, phi-3.5 699

| Tier | no-op | random legal (exp.) | random candidate (exp.) | local search | optimum |
|---|---|---|---|---|---|
| T1 | 0.0 | 18.6 | 10.9 | 100.0 | 100.0 |
| T2 | 0.0 | 27.8 | 7.8 | 73.0 | 100.0 |
| T3 | 0.0 | 25.5 | 5.1 | 54.7 | 100.0 |
| **pack (tier-equal)** | 0.0 | 24.0 | 8.0 | 75.9 | 100.0 |

Shadow rejection rate 0.206 / 0.408 / 0.515 / 0.768 / 0.898; optimum density 0.00121 / 0.0165 / 0.027 / 0.096 / 0.189; v* 5 / 6 / 9 / 12 / 19; partial-credit levels 1 / 1 / 2 / 2 / 7 (min / q1 / median / q3 / max).

| Instance | Tier | v* | legal | optimal | min moves | shadow rej. | traps | LS score | tokens |
|---|---|---|---|---|---|---|---|---|---|
| st-rank-b1-3000009 | T1 | 6 | 36 | 2 | 1 | 0.44 | 5 | 100 | 659 |
| st-rank-b1-3000010 | T1 | 6 | 64 | 7 | 1 | 0.22 | 8 | 100 | 663 |
| st-rank-b1-3000012 | T1 | 6 | 28 | 1 | 1 | 0.33 | 1 | 100 | 641 |
| st-rank-b1-3000019 | T1 | 6 | 45 | 1 | 1 | 0.21 | 1 | 100 | 633 |
| st-rank-b1-3000032 | T1 | 6 | 37 | 1 | 1 | 0.42 | 5 | 100 | 661 |
| st-rank-b1-3000039 | T1 | 10 | 51 | 1 | 1 | 0.43 | 7 | 100 | 697 |
| st-rank-b1-3000050 | T1 | 8 | 20 | 3 | 1 | 0.60 | 5 | 100 | 657 |
| st-rank-b1-3000056 | T1 | 6 | 29 | 1 | 1 | 0.41 | 15 | 100 | 639 |
| st-rank-b1-3000063 | T1 | 6 | 50 | 7 | 1 | 0.21 | 2 | 100 | 663 |
| st-rank-b1-3000082 | T1 | 12 | 57 | 5 | 1 | 0.28 | 13 | 100 | 679 |
| st-rank-b2-3100022 | T2 | 8 | 90 | 2 | 2 | 0.68 | 11 | 50 | 629 |
| st-rank-b2-3100056 | T2 | 19 | 262 | 40 | 2 | 0.77 | 22 | 100 | 697 |
| st-rank-b2-3100058 | T2 | 5 | 669 | 9 | 2 | 0.52 | 102 | 80 | 681 |
| st-rank-b2-3100066 | T2 | 12 | 414 | 63 | 2 | 0.44 | 5 | 0 | 669 |
| st-rank-b2-3100071 | T2 | 9 | 354 | 34 | 2 | 0.83 | 458 | 100 | 699 |
| st-rank-b2-3100082 | T2 | 7 | 339 | 7 | 2 | 0.34 | 6 | 100 | 649 |
| st-rank-b2-3100085 | T2 | 13 | 263 | 6 | 2 | 0.64 | 8 | 100 | 667 |
| st-rank-b2-3100088 | T2 | 6 | 577 | 1 | 2 | 0.51 | 6 | 0 | 671 |
| st-rank-b2-3100090 | T2 | 14 | 95 | 18 | 2 | 0.68 | 18 | 100 | 629 |
| st-rank-b2-3100094 | T2 | 7 | 549 | 9 | 2 | 0.49 | 15 | 100 | 671 |
| st-rank-b3-3200006 | T3 | 9 | 876 | 35 | 3 | 0.84 | 1233 | 89 | 679 |
| st-rank-b3-3200008 | T3 | 15 | 872 | 62 | 2 | 0.45 | 75 | 33 | 647 |
| st-rank-b3-3200017 | T3 | 15 | 1246 | 21 | 2 | 0.83 | 611 | 13 | 687 |
| st-rank-b3-3200022 | T3 | 10 | 3037 | 50 | 3 | 0.65 | 381 | 100 | 699 |
| st-rank-b3-3200027 | T3 | 8 | 825 | 1 | 3 | 0.84 | 739 | 50 | 671 |
| st-rank-b3-3200035 | T3 | 11 | 1014 | 25 | 3 | 0.90 | 1355 | 55 | 689 |
| st-rank-b3-3200036 | T3 | 10 | 507 | 67 | 2 | 0.88 | 1210 | 0 | 677 |
| st-rank-b3-3200052 | T3 | 13 | 294 | 2 | 3 | 0.83 | 38 | 46 | 647 |
| st-rank-b3-3200077 | T3 | 18 | 1304 | 2 | 3 | 0.41 | 2 | 94 | 667 |
| st-rank-b3-3200098 | T3 | 6 | 233 | 1 | 2 | 0.74 | 73 | 67 | 613 |

Selection (candidates consumed in seed order per tier): T1: examined 83, accepted 10; T2: examined 95, accepted 10; T3: examined 99, accepted 10

## `shadowtwins-practice-v1` (practice split, unranked)

* Instances: 9 (T1 single relocation: 3, T2 paired relocations: 3, T3 coordinated search: 3)
* `pack_hash`: `sha256:f9d604a6655ded2b429139263f1419608aa4c19daa2b7cc2223dab3159c805b3`
* `policy_hash`: `sha256:372ada53017c81e58dfddf367b9e536bd62e48d805ee888e6ca2a466ce9b95b5`
* Versions: rules `st-rules-1.0.0`, parser `st-parser-1.0.0`, evaluator `st-eval-1.0.0`, solver `st-solver-1.0.0`, protocol `st-protocol-1.0.0`, generator `st-gen-1.0.0`, token_panel `st-tokpanel-1.0.0`, local_search `st-ls-1.0.0`, policy `st-policy-1.0.0`, pack_format `st-pack-1`
* Independent verification: 9/9 certificates reproduced by `stverify`
* Prompt tokens (panel `st-tokpanel-1.0.0`, ceiling 800): max 671; per tokenizer max openai-o200k 586, openai-cl100k 586, llama-3.1 586, qwen-2.5 626, deepseek-v3 591, mistral-nemo 629, phi-3.5 671

| Tier | no-op | random legal (exp.) | random candidate (exp.) | local search | optimum |
|---|---|---|---|---|---|
| T1 | 0.0 | 33.5 | 22.0 | 100.0 | 100.0 |
| T2 | 0.0 | 16.7 | 7.3 | 100.0 | 100.0 |
| T3 | 0.0 | 34.8 | 4.4 | 69.4 | 100.0 |
| **pack (tier-equal)** | 0.0 | 28.3 | 11.3 | 89.8 | 100.0 |

Shadow rejection rate 0.295 / 0.368 / 0.56 / 0.715 / 0.93; optimum density 0.0036 / 0.0116 / 0.0465 / 0.167 / 0.238; v* 3 / 8 / 8 / 10 / 12; partial-credit levels 1 / 1 / 2 / 2 / 5 (min / q1 / median / q3 / max).

| Instance | Tier | v* | legal | optimal | min moves | shadow rej. | traps | LS score | tokens |
|---|---|---|---|---|---|---|---|---|---|
| st-prac-b1-2000012 | T1 | 8 | 36 | 6 | 1 | 0.37 | 1 | 100 | 633 |
| st-prac-b1-2000019 | T1 | 3 | 42 | 10 | 1 | 0.34 | 10 | 100 | 667 |
| st-prac-b1-2000051 | T1 | 9 | 43 | 2 | 1 | 0.30 | 2 | 100 | 651 |
| st-prac-b2-2100005 | T2 | 10 | 262 | 2 | 2 | 0.56 | 3 | 100 | 649 |
| st-prac-b2-2100007 | T2 | 12 | 518 | 6 | 2 | 0.52 | 147 | 100 | 669 |
| st-prac-b2-2100009 | T2 | 8 | 426 | 10 | 2 | 0.58 | 30 | 100 | 653 |
| st-prac-b3-2200003 | T3 | 12 | 269 | 15 | 2 | 0.71 | 11 | 50 | 637 |
| st-prac-b3-2200017 | T3 | 6 | 326 | 60 | 2 | 0.79 | 794 | 83 | 631 |
| st-prac-b3-2200018 | T3 | 8 | 278 | 1 | 3 | 0.93 | 656 | 75 | 671 |

Selection (candidates consumed in seed order per tier): T1: examined 52, accepted 3; T2: examined 10, accepted 3; T3: examined 19, accepted 3

## `shadowtwins-dev-v1` (development split, unranked)

* Instances: 30 (T1 single relocation: 10, T2 paired relocations: 10, T3 coordinated search: 10)
* `pack_hash`: `sha256:9670ac7492c6c9931daa8c28aa2a80011c69f388dd1fb65de57ea8d840289374`
* `policy_hash`: `sha256:372ada53017c81e58dfddf367b9e536bd62e48d805ee888e6ca2a466ce9b95b5`
* Versions: rules `st-rules-1.0.0`, parser `st-parser-1.0.0`, evaluator `st-eval-1.0.0`, solver `st-solver-1.0.0`, protocol `st-protocol-1.0.0`, generator `st-gen-1.0.0`, token_panel `st-tokpanel-1.0.0`, local_search `st-ls-1.0.0`, policy `st-policy-1.0.0`, pack_format `st-pack-1`
* Independent verification: 30/30 certificates reproduced by `stverify`
* Prompt tokens (panel `st-tokpanel-1.0.0`, ceiling 800): max 699; per tokenizer max openai-o200k 612, openai-cl100k 612, llama-3.1 612, qwen-2.5 654, deepseek-v3 617, mistral-nemo 657, phi-3.5 699

| Tier | no-op | random legal (exp.) | random candidate (exp.) | local search | optimum |
|---|---|---|---|---|---|
| T1 | 0.0 | 30.6 | 15.8 | 100.0 | 100.0 |
| T2 | 0.0 | 27.4 | 8.0 | 79.3 | 100.0 |
| T3 | 0.0 | 36.9 | 7.5 | 63.4 | 100.0 |
| **pack (tier-equal)** | 0.0 | 31.6 | 10.4 | 80.9 | 100.0 |

Shadow rejection rate 0.219 / 0.395 / 0.53 / 0.746 / 0.939; optimum density 0.0018 / 0.0127 / 0.0399 / 0.0823 / 0.231; v* 2 / 6 / 9 / 11 / 23; partial-credit levels 1 / 2 / 2 / 3 / 6 (min / q1 / median / q3 / max).

| Instance | Tier | v* | legal | optimal | min moves | shadow rej. | traps | LS score | tokens |
|---|---|---|---|---|---|---|---|---|---|
| st-dev-b1-1000000 | T1 | 7 | 20 | 1 | 1 | 0.49 | 15 | 100 | 637 |
| st-dev-b1-1000010 | T1 | 9 | 23 | 5 | 1 | 0.53 | 1 | 100 | 631 |
| st-dev-b1-1000032 | T1 | 9 | 45 | 2 | 1 | 0.45 | 2 | 100 | 671 |
| st-dev-b1-1000036 | T1 | 12 | 57 | 1 | 1 | 0.22 | 2 | 100 | 669 |
| st-dev-b1-1000046 | T1 | 8 | 26 | 1 | 1 | 0.53 | 1 | 100 | 649 |
| st-dev-b1-1000050 | T1 | 2 | 39 | 9 | 1 | 0.36 | 1 | 100 | 659 |
| st-dev-b1-1000061 | T1 | 8 | 16 | 2 | 1 | 0.56 | 1 | 100 | 647 |
| st-dev-b1-1000076 | T1 | 6 | 53 | 9 | 1 | 0.35 | 14 | 100 | 663 |
| st-dev-b1-1000089 | T1 | 8 | 37 | 5 | 1 | 0.23 | 6 | 100 | 667 |
| st-dev-b1-1000096 | T1 | 9 | 26 | 1 | 1 | 0.40 | 1 | 100 | 629 |
| st-dev-b2-1100006 | T2 | 6 | 1017 | 10 | 2 | 0.41 | 253 | 50 | 689 |
| st-dev-b2-1100009 | T2 | 13 | 275 | 21 | 2 | 0.75 | 549 | 100 | 677 |
| st-dev-b2-1100019 | T2 | 7 | 620 | 42 | 2 | 0.52 | 49 | 100 | 687 |
| st-dev-b2-1100029 | T2 | 8 | 189 | 20 | 2 | 0.89 | 40 | 100 | 673 |
| st-dev-b2-1100037 | T2 | 4 | 76 | 4 | 2 | 0.73 | 4 | 100 | 623 |
| st-dev-b2-1100038 | T2 | 17 | 243 | 3 | 2 | 0.47 | 1 | 100 | 677 |
| st-dev-b2-1100044 | T2 | 10 | 659 | 2 | 2 | 0.35 | 9 | 0 | 677 |
| st-dev-b2-1100065 | T2 | 10 | 157 | 2 | 2 | 0.71 | 2 | 60 | 649 |
| st-dev-b2-1100068 | T2 | 12 | 419 | 3 | 2 | 0.23 | 1 | 83 | 667 |
| st-dev-b2-1100069 | T2 | 11 | 64 | 1 | 2 | 0.76 | 9 | 100 | 627 |
| st-dev-b3-1200018 | T3 | 6 | 837 | 21 | 2 | 0.94 | 167 | 50 | 691 |
| st-dev-b3-1200033 | T3 | 9 | 2623 | 216 | 2 | 0.22 | 388 | 0 | 661 |
| st-dev-b3-1200062 | T3 | 6 | 2952 | 88 | 2 | 0.78 | 2786 | 83 | 699 |
| st-dev-b3-1200106 | T3 | 4 | 381 | 34 | 2 | 0.76 | 614 | 50 | 631 |
| st-dev-b3-1200107 | T3 | 4 | 1663 | 3 | 3 | 0.75 | 92 | 50 | 663 |
| st-dev-b3-1200126 | T3 | 6 | 286 | 5 | 3 | 0.53 | 9 | 100 | 651 |
| st-dev-b3-1200130 | T3 | 10 | 1445 | 15 | 3 | 0.64 | 637 | 60 | 687 |
| st-dev-b3-1200160 | T3 | 23 | 617 | 6 | 3 | 0.81 | 42 | 100 | 677 |
| st-dev-b3-1200164 | T3 | 12 | 751 | 30 | 2 | 0.50 | 61 | 83 | 647 |
| st-dev-b3-1200168 | T3 | 14 | 654 | 35 | 2 | 0.68 | 291 | 57 | 657 |

Selection (candidates consumed in seed order per tier): T1: examined 97, accepted 10; T2: examined 70, accepted 10; T3: examined 169, accepted 10
